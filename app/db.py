"""SQLite storage: knowledge modules and enrolled faces.

SQLite is the source of truth. The vector database (see rag.py) is an index
built from the modules table and can always be rebuilt from it.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

DB_PATH = config.DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'manual',  -- manual | csv | image
    updated_by TEXT,
    updated_at TEXT NOT NULL
);

-- Only the 128-number face signature is stored, never the photo itself.
CREATE TABLE IF NOT EXISTS faces (
    email      TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# --- Modules ----------------------------------------------------------------

def list_modules() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM modules ORDER BY updated_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def count_modules() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]


def get_module(module_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
    return dict(row) if row else None


def create_module(title: str, content: str, source: str, user: str) -> dict:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO modules (title, content, source, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)",
            (title, content, source, user, now()),
        )
        module_id = cur.lastrowid
    return get_module(module_id)


def update_module(module_id: int, title: str, content: str, user: str) -> dict | None:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE modules SET title = ?, content = ?, updated_by = ?, updated_at = ? WHERE id = ?",
            (title, content, user, now(), module_id),
        )
        if cur.rowcount == 0:
            return None
    return get_module(module_id)


def delete_module(module_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM modules WHERE id = ?", (module_id,))
    return cur.rowcount > 0


# --- Faces ------------------------------------------------------------------

def list_faces() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT email, updated_by, updated_at FROM faces ORDER BY email").fetchall()
    return [dict(r) for r in rows]


def get_face(email: str) -> bytes | None:
    with connect() as conn:
        row = conn.execute("SELECT embedding FROM faces WHERE email = ?", (email,)).fetchone()
    return row["embedding"] if row else None


def save_face(email: str, embedding: bytes, user: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO faces (email, embedding, updated_by, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET embedding = excluded.embedding, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (email, embedding, user, now()),
        )


def delete_face(email: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM faces WHERE email = ?", (email,))
    return cur.rowcount > 0
