"""SQLite storage: knowledge modules, enrolled faces, staff roles, marks, attendance, notes and events.

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

-- Only face signatures are stored, never photos. One row per person; the blob
-- holds one 128-number signature (512 bytes) per photo taken at enrolment.
CREATE TABLE IF NOT EXISTS faces (
    email      TEXT PRIMARY KEY,
    embedding  BLOB NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);

-- Admins and teachers. Anyone not listed here (and not in ADMIN_EMAILS) is a student.
-- A teacher can only edit what an admin has switched on.
CREATE TABLE IF NOT EXISTS roles (
    email          TEXT PRIMARY KEY,
    name           TEXT,
    role           TEXT NOT NULL,              -- admin | teacher
    can_content    INTEGER NOT NULL DEFAULT 0,
    can_attendance INTEGER NOT NULL DEFAULT 0,
    can_marks      INTEGER NOT NULL DEFAULT 0,
    updated_by     TEXT,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    email      TEXT PRIMARY KEY,
    name       TEXT,
    branch     TEXT,
    semester   INTEGER NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);

-- id is "email|semester|subject code", so every table has one text key.
CREATE TABLE IF NOT EXISTS marks (
    id         TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    semester   INTEGER NOT NULL,
    code       TEXT NOT NULL,
    subject    TEXT NOT NULL,
    internal   INTEGER NOT NULL,               -- out of 50
    external   INTEGER NOT NULL,               -- out of 50
    updated_by TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS marks_email ON marks (email);

CREATE TABLE IF NOT EXISTS attendance (
    id         TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    semester   INTEGER NOT NULL,
    code       TEXT NOT NULL,
    subject    TEXT NOT NULL,
    attended   INTEGER NOT NULL,
    total      INTEGER NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS attendance_email ON attendance (email);

-- Notes library: semesters 1-8, a few subjects each, and files or pasted text under each subject.
CREATE TABLE IF NOT EXISTS subjects (
    code     TEXT PRIMARY KEY,
    semester INTEGER NOT NULL,
    name     TEXT NOT NULL
);

-- A note is a PDF (data) or pasted text. `content` is the text the AI reads (pasted, or taken from the PDF).
-- module_id points at the knowledge entry that makes the note searchable by the assistant.
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    title       TEXT NOT NULL,
    kind        TEXT NOT NULL,                 -- pdf | text
    content     TEXT NOT NULL DEFAULT '',
    filename    TEXT,
    data        BLOB,
    module_id   INTEGER,
    uploaded_by TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notes_code ON notes (code);

-- Small settings kept with the data, for example "the sample data has been added".
CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    event_date  TEXT NOT NULL,                 -- YYYY-MM-DD
    start_time  TEXT NOT NULL DEFAULT '',      -- HH:MM
    venue       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    filename    TEXT,
    data        BLOB,
    module_id   INTEGER,
    created_by  TEXT,
    created_at  TEXT NOT NULL
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


def get_meta(key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
    return row["v"] if row else None


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (key, value))


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


def get_module_by_title(title: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM modules WHERE title = ? ORDER BY id LIMIT 1", (title,)).fetchone()
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

FACE_SIZE = 128 * 4   # bytes in one signature (128 float32 numbers)
MIN_TEMPLATES = 5     # a row with fewer signatures is an old single-photo one: treated as not enrolled


def list_faces() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT f.email, f.updated_at, p.name FROM faces f LEFT JOIN profiles p ON p.email = f.email "
            "WHERE length(f.embedding) >= ? ORDER BY f.email",
            (FACE_SIZE * MIN_TEMPLATES,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_face(email: str) -> bytes | None:
    """The enrolled signatures, or None if this person has not completed enrolment."""
    with connect() as conn:
        row = conn.execute("SELECT embedding FROM faces WHERE email = ?", (email,)).fetchone()
    if not row or len(row["embedding"]) < FACE_SIZE * MIN_TEMPLATES:
        return None
    return row["embedding"]


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


# --- Roles ------------------------------------------------------------------

def get_role(email: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM roles WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def list_roles() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM roles ORDER BY role, email").fetchall()
    return [dict(r) for r in rows]


def save_role(email: str, name: str | None, role: str, perms: dict, user: str) -> dict:
    with connect() as conn:
        conn.execute(
            "INSERT INTO roles (email, name, role, can_content, can_attendance, can_marks, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET "
            "name = COALESCE(excluded.name, roles.name), role = excluded.role, can_content = excluded.can_content, "
            "can_attendance = excluded.can_attendance, can_marks = excluded.can_marks, "
            "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (email, name, role, int(perms["content"]), int(perms["attendance"]), int(perms["marks"]), user, now()),
        )
    return get_role(email)


def delete_role(email: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM roles WHERE email = ?", (email,))
    return cur.rowcount > 0


# --- Students: profiles, marks, attendance --------------------------------------

def get_profile(email: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def list_profiles(query: str = "", limit: int = 200) -> list[dict]:
    like = f"%{query.strip().lower()}%"
    with connect() as conn:
        rows = conn.execute(
            "SELECT email, name, branch, semester FROM profiles "
            "WHERE lower(email) LIKE ? OR lower(COALESCE(name, '')) LIKE ? ORDER BY email LIMIT ?",
            (like, like, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def save_student(profile: dict, marks: list[dict], attendance: list[dict], user: str) -> None:
    """Create a student's profile with their first marks and attendance, in one go."""
    stamp = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO profiles (email, name, branch, semester, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(email) DO NOTHING",
            (profile["email"], profile["name"], profile["branch"], profile["semester"], user, stamp),
        )
        for m in marks:
            conn.execute(
                "INSERT INTO marks (id, email, semester, code, subject, internal, external, updated_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                (f"{m['email']}|{m['semester']}|{m['code']}", m["email"], m["semester"], m["code"], m["subject"],
                 m["internal"], m["external"], user, stamp),
            )
        for a in attendance:
            conn.execute(
                "INSERT INTO attendance (id, email, semester, code, subject, attended, total, updated_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                (f"{a['email']}|{a['semester']}|{a['code']}", a["email"], a["semester"], a["code"], a["subject"],
                 a["attended"], a["total"], user, stamp),
            )


def rename_profile(email: str, name: str, user: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE profiles SET name = ?, updated_by = ?, updated_at = ? WHERE email = ?",
                     (name, user, now(), email))


def unname_seeded_profiles() -> None:
    """Profiles made by the sample data, that no real student has claimed yet, are named by their USN."""
    with connect() as conn:
        conn.execute("UPDATE profiles SET name = upper(substr(email, 1, instr(email, '@') - 1)) "
                     "WHERE updated_by = 'demo seed' AND name != upper(substr(email, 1, instr(email, '@') - 1))")


def list_marks(email: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM marks WHERE email = ? ORDER BY semester, code", (email,)).fetchall()
    return [dict(r) for r in rows]


def update_mark(email: str, semester: int, code: str, internal: int, external: int, user: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE marks SET internal = ?, external = ?, updated_by = ?, updated_at = ? WHERE id = ?",
            (internal, external, user, now(), f"{email}|{semester}|{code}"),
        )
    return cur.rowcount > 0


def list_attendance(email: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM attendance WHERE email = ? ORDER BY semester, code", (email,)).fetchall()
    return [dict(r) for r in rows]


def update_attendance(email: str, semester: int, code: str, attended: int, total: int, user: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE attendance SET attended = ?, total = ?, updated_by = ?, updated_at = ? WHERE id = ?",
            (attended, total, user, now(), f"{email}|{semester}|{code}"),
        )
    return cur.rowcount > 0


# --- Notes and events -------------------------------------------------------------

def add_subjects(rows: list[tuple[str, int, str]]) -> None:
    with connect() as conn:
        conn.executemany("INSERT OR IGNORE INTO subjects (code, semester, name) VALUES (?, ?, ?)", rows)


def list_subjects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.code, s.semester, s.name, COUNT(n.id) AS notes FROM subjects s "
            "LEFT JOIN notes n ON n.code = s.code GROUP BY s.code ORDER BY s.semester, s.code"
        ).fetchall()
    return [dict(r) for r in rows]


def get_subject(code: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM subjects WHERE code = ?", (code,)).fetchone()
    return dict(row) if row else None


_NOTE_LIST = "id, code, title, kind, filename, content != '' AS readable, uploaded_by, created_at, module_id"


def list_notes(code: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {_NOTE_LIST}, CASE WHEN kind = 'text' THEN content END AS text "
            "FROM notes WHERE code = ? ORDER BY id DESC", (code,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_note(note_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return dict(row) if row else None


def add_note(code: str, title: str, kind: str, content: str, filename: str | None, data: bytes | None, user: str) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO notes (code, title, kind, content, filename, data, uploaded_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (code, title, kind, content, filename, data, user, now()),
        ).lastrowid


def note_modules(semesters: list[int]) -> list[dict]:
    """The knowledge entries behind every note of these semesters (what the assistant reads)."""
    if not semesters:
        return []
    marks = ",".join("?" * len(semesters))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT m.*, n.code AS note_code FROM notes n JOIN subjects s ON s.code = n.code JOIN modules m ON m.id = n.module_id "
            f"WHERE s.semester IN ({marks}) ORDER BY s.semester, s.code, n.id", semesters).fetchall()
    return [dict(r) for r in rows]


def note_modules_for(codes: list[str]) -> list[dict]:
    """The knowledge entries behind the notes of these subjects, in the order given."""
    out = []
    with connect() as conn:
        for code in codes:
            rows = conn.execute("SELECT m.*, n.code AS note_code FROM notes n JOIN modules m ON m.id = n.module_id "
                                "WHERE n.code = ? ORDER BY n.id", (code,)).fetchall()
            out += [dict(r) for r in rows]
    return out


def delete_note(note_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0


def list_events() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, event_date, start_time, venue, description, filename, data IS NOT NULL AS has_file, "
            "created_by, created_at, module_id FROM events ORDER BY event_date, start_time, id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_event(event_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return dict(row) if row else None


def add_event(title: str, event_date: str, start_time: str, venue: str, description: str,
              filename: str | None, data: bytes | None, user: str) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO events (title, event_date, start_time, venue, description, filename, data, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, event_date, start_time, venue, description, filename, data, user, now()),
        ).lastrowid


def set_module(table: str, row_id: int, module_id: int | None) -> None:
    assert table in ("notes", "events")
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET module_id = ? WHERE id = ?", (module_id, row_id))


def delete_event(event_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM events WHERE id = ?", (event_id,)).rowcount > 0


def links_for_modules(module_ids: list[int]) -> list[dict]:
    """Which notes and events the given knowledge entries belong to (for links under an answer)."""
    if not module_ids:
        return []
    marks = ",".join("?" * len(module_ids))
    with connect() as conn:
        notes = conn.execute(
            f"SELECT n.id, n.title, n.kind, n.code, s.semester FROM notes n LEFT JOIN subjects s ON s.code = n.code "
            f"WHERE n.module_id IN ({marks})", module_ids).fetchall()
        events = conn.execute(f"SELECT id, title FROM events WHERE module_id IN ({marks})", module_ids).fetchall()
    out = [{**dict(r), "kind": "note"} for r in notes] + [{**dict(r), "kind": "event"} for r in events]
    return out
