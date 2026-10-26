"""Offline-first sync between this laptop's SQLite database and the Turso backend.

SQLite triggers write every change to modules, faces and first_faces into an
outbox table, so the admin code in app/ works unchanged. When there is
internet, sync_once():
  1. push: sends the outbox to Turso
  2. pull: applies the rows Turso received since the last pull
Both directions keep the row with the newer updated_at. Deletes stay on Turso
as rows with deleted = 1, so other laptops learn about them.

A knowledge module's local id differs per laptop, so on Turso it is known by a
uid ("<device>-<id>"); module_uids maps between the two.
"""
import base64
import logging
import threading
import uuid

import requests

from app import db, rag

from . import config

log = logging.getLogger(__name__)

FACE_BYTES = 128 * 4  # 128 float32 numbers

LOCAL_SCHEMA = """
-- The photo a student takes at their first sign-in, used next to the college photo.
CREATE TABLE IF NOT EXISTS first_faces (
    email      TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id  INTEGER PRIMARY KEY AUTOINCREMENT,
    tbl TEXT NOT NULL,
    key TEXT NOT NULL,
    op  TEXT NOT NULL,  -- upsert | delete
    at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS module_uids (uid TEXT PRIMARY KEY, local_id INTEGER NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS sync_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""

LOCAL_KEY = {"modules": "id", "faces": "email", "first_faces": "email"}
REMOTE = {"modules": "nva_modules", "faces": "nva_faces", "first_faces": "nva_first_faces"}
REMOTE_KEY = {"modules": "uid", "faces": "email", "first_faces": "email"}
COLUMNS = {
    "modules": ("title", "content", "source", "updated_by"),
    "faces": ("embedding", "updated_by"),
    "first_faces": ("embedding", "updated_by"),
}
# The nva_ prefix keeps these apart from other projects' tables in the same Turso database.
# synced_at is Turso's own clock, so a laptop that was offline for days still gets pulled from.
REMOTE_SCHEMA = [
    f"CREATE TABLE IF NOT EXISTS {REMOTE[t]} ({REMOTE_KEY[t]} TEXT PRIMARY KEY, "
    + "".join(f"{c} TEXT, " for c in COLUMNS[t])
    + "updated_at TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, synced_at TEXT NOT NULL)"
    for t in REMOTE
]
SERVER_NOW = "strftime('%Y-%m-%dT%H:%M:%f', 'now')"


def _triggers(table: str, key: str) -> str:
    now = "strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')"  # the same format as app.db.now()
    log_row = "INSERT INTO outbox (tbl, key, op, at) VALUES"
    return f"""
CREATE TRIGGER IF NOT EXISTS {table}_ins AFTER INSERT ON {table} BEGIN
  {log_row} ('{table}', NEW.{key}, 'upsert', NEW.updated_at); END;
CREATE TRIGGER IF NOT EXISTS {table}_upd AFTER UPDATE ON {table} BEGIN
  {log_row} ('{table}', NEW.{key}, 'upsert', NEW.updated_at); END;
CREATE TRIGGER IF NOT EXISTS {table}_del AFTER DELETE ON {table} BEGIN
  {log_row} ('{table}', OLD.{key}, 'delete', {now}); END;
"""


class SyncError(Exception):
    pass


def enabled() -> bool:
    return bool(config.TURSO_DATABASE_URL and config.TURSO_AUTH_TOKEN)


status = {"state": "waiting" if enabled() else "off", "last_sync": None, "message": ""}
_lock = threading.Lock()
_wake = threading.Event()
_schema_ready = False


def _meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT v FROM sync_meta WHERE k = ?", (key,)).fetchone()
    return row["v"] if row else None


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO sync_meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (key, value))


def init() -> None:
    """Create the sync tables and triggers. Call after app.db.init()."""
    with db.connect() as conn:
        conn.executescript(LOCAL_SCHEMA + "".join(_triggers(t, k) for t, k in LOCAL_KEY.items()))
        if not _meta(conn, "device_id"):
            _set_meta(conn, "device_id", uuid.uuid4().hex[:12])
            # Rows made before sync was set up (for example by the online app) go out on the first sync.
            for table, key in LOCAL_KEY.items():
                conn.execute(f"INSERT INTO outbox (tbl, key, op, at) SELECT '{table}', {key}, 'upsert', updated_at FROM {table}")


# --- Turso over HTTP (https://docs.turso.tech/sdk/http/reference) ---------------

def _arg(value) -> dict:
    if value is None:
        return {"type": "null"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    return {"type": "text", "value": str(value)}


def _parse(value: dict):
    if value["type"] == "null":
        return None
    if value["type"] == "integer":
        return int(value["value"])
    return value.get("value")


def remote(statements: list[tuple[str, list]]) -> list[list[dict]]:
    """Run SQL statements on Turso in one request. Returns each statement's rows as dicts."""
    url = config.TURSO_DATABASE_URL.replace("libsql://", "https://", 1).rstrip("/") + "/v2/pipeline"
    requests_ = [{"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in args]}} for sql, args in statements]
    res = requests.post(
        url,
        json={"requests": requests_ + [{"type": "close"}]},
        headers={"Authorization": f"Bearer {config.TURSO_AUTH_TOKEN}"},
        timeout=30,
    )
    res.raise_for_status()
    out = []
    for result in res.json()["results"][: len(statements)]:
        if result["type"] != "ok":
            raise SyncError(result["error"]["message"])
        rows = result["response"]["result"]
        cols = [c["name"] for c in rows["cols"]]
        out.append([dict(zip(cols, map(_parse, row))) for row in rows["rows"]])
    return out


# --- Push ----------------------------------------------------------------------

def _uid(conn, local_id: int) -> str:
    row = conn.execute("SELECT uid FROM module_uids WHERE local_id = ?", (local_id,)).fetchone()
    if row:
        return row["uid"]
    uid = f"{_meta(conn, 'device_id')}-{local_id}"
    conn.execute("INSERT INTO module_uids (uid, local_id) VALUES (?, ?)", (uid, local_id))
    return uid


def _upsert_sql(tbl: str, deleted: bool) -> str:
    table, key = REMOTE[tbl], REMOTE_KEY[tbl]
    names = [key, *(() if deleted else COLUMNS[tbl]), "updated_at", "deleted"]
    sets = ", ".join(f"{c} = excluded.{c}" for c in [*names[1:], "synced_at"])
    return (
        f"INSERT INTO {table} ({', '.join(names)}, synced_at) VALUES ({', '.join('?' * len(names))}, {SERVER_NOW}) "
        f"ON CONFLICT({key}) DO UPDATE SET {sets} WHERE excluded.updated_at >= {table}.updated_at"
    )


def _push_statement(conn, entry) -> tuple[str, list] | None:
    tbl, local_key = entry["tbl"], entry["key"]
    if tbl == "modules":
        local_key = int(local_key)
        key = _uid(conn, local_key)
    else:
        key = local_key
    if entry["op"] == "delete":
        return _upsert_sql(tbl, True), [key, entry["at"], 1]
    row = conn.execute(f"SELECT * FROM {tbl} WHERE {LOCAL_KEY[tbl]} = ?", (local_key,)).fetchone()
    if row is None:
        return None  # deleted since; that delete is further down the outbox
    values = [base64.b64encode(row[c]).decode() if isinstance(row[c], bytes) else row[c] for c in COLUMNS[tbl]]
    return _upsert_sql(tbl, False), [key, *values, row["updated_at"], 0]


def push() -> int:
    """Send the outbox to Turso. Returns how many rows were sent."""
    with db.connect() as conn:
        entries = conn.execute("SELECT * FROM outbox ORDER BY id LIMIT 2000").fetchall()
        latest = {(e["tbl"], e["key"]): e for e in entries}  # only the last change per row matters
        statements = [s for e in latest.values() if (s := _push_statement(conn, e))]
    # No database lock is held while waiting for the network.
    for i in range(0, len(statements), 200):
        remote(statements[i : i + 200])
    if entries:
        with db.connect() as conn:
            conn.execute("DELETE FROM outbox WHERE id <= ?", (entries[-1]["id"],))
    return len(latest)


# --- Pull ----------------------------------------------------------------------

def _apply_module(conn, row: dict, changed: list, removed: list) -> None:
    local = conn.execute(
        "SELECT m.id, m.updated_at FROM module_uids u JOIN modules m ON m.id = u.local_id WHERE u.uid = ?",
        (row["uid"],),
    ).fetchone()
    if local and local["updated_at"] >= row["updated_at"]:
        return
    if row["deleted"]:
        if local:
            conn.execute("DELETE FROM modules WHERE id = ?", (local["id"],))
            removed.append(local["id"])
        return
    values = (row["title"], row["content"], row["source"], row["updated_by"], row["updated_at"])
    if local:
        conn.execute(
            "UPDATE modules SET title = ?, content = ?, source = ?, updated_by = ?, updated_at = ? WHERE id = ?",
            (*values, local["id"]),
        )
        changed.append(local["id"])
        return
    new_id = conn.execute(
        "INSERT INTO modules (title, content, source, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)", values
    ).lastrowid
    conn.execute(
        "INSERT INTO module_uids (uid, local_id) VALUES (?, ?) ON CONFLICT(uid) DO UPDATE SET local_id = excluded.local_id",
        (row["uid"], new_id),
    )
    changed.append(new_id)


def _apply_face(conn, tbl: str, row: dict) -> None:
    local = conn.execute(f"SELECT updated_at FROM {tbl} WHERE email = ?", (row["email"],)).fetchone()
    if local and local["updated_at"] >= row["updated_at"]:
        return
    if row["deleted"]:
        conn.execute(f"DELETE FROM {tbl} WHERE email = ?", (row["email"],))
        return
    embedding = base64.b64decode(row["embedding"] or "")
    if len(embedding) != FACE_BYTES:
        log.warning("Skipping a damaged face signature for %s from Turso", row["email"])
        return
    conn.execute(
        f"INSERT INTO {tbl} (email, embedding, updated_by, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(email) DO UPDATE SET embedding = excluded.embedding, "
        "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
        (row["email"], embedding, row["updated_by"], row["updated_at"]),
    )


def pull() -> bool:
    """Apply what Turso received since the last pull. Returns False if it waited for a push first."""
    with db.connect() as conn:
        since = _meta(conn, "pulled_until") or ""
    results = remote([(f"SELECT * FROM {REMOTE[t]} WHERE synced_at >= ? ORDER BY synced_at", [since]) for t in REMOTE])

    changed, removed = [], []
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")  # no local edit can slip in between the check and the apply
        if conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]:
            return False  # a local edit came in after the push: send it first, pull next round
        newest = since
        for tbl, rows in zip(REMOTE, results):
            for row in rows:
                newest = max(newest, row["synced_at"])
                if tbl == "modules":
                    _apply_module(conn, row, changed, removed)
                else:
                    _apply_face(conn, tbl, row)
        conn.execute("DELETE FROM outbox")  # the triggers logged what came from Turso; don't send it back
        _set_meta(conn, "pulled_until", newest)

    for module_id in removed:
        rag.remove_module(module_id)
    for module_id in changed:
        rag.index_module(db.get_module(module_id))
    return True


# --- Running it ------------------------------------------------------------------

def sync_once() -> None:
    global _schema_ready
    if not enabled():
        return
    with _lock:
        status["state"] = "syncing"
        try:
            if not _schema_ready:
                remote([(sql, []) for sql in REMOTE_SCHEMA])
                _schema_ready = True
            push()
            pull()
        except requests.HTTPError as e:
            status.update(state="error", message=f"The backend refused the sync ({e.response.status_code}). Check TURSO_AUTH_TOKEN.")
        except requests.RequestException:
            status.update(state="offline", message="No internet. Changes are kept on this laptop and sync later.")
        except Exception as e:
            log.exception("Sync failed")
            status.update(state="error", message=f"Sync failed: {e}")
        else:
            status.update(state="synced", last_sync=db.now(), message="")


def current_status() -> dict:
    with db.connect() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    return {**status, "pending": pending}


def _loop() -> None:
    while True:
        sync_once()
        _wake.wait(config.SYNC_SECONDS)
        _wake.clear()


def start() -> None:
    init()
    if enabled():
        threading.Thread(target=_loop, name="sync", daemon=True).start()


def sync_soon() -> None:
    _wake.set()
