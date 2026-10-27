"""The offline app: sync with the backend, and Face ID style sign-in."""
import base64
import sqlite3

import numpy as np
import pytest
import requests
from fastapi.testclient import TestClient

from app import db, face
from offline_app import sync
from offline_app.main import app as offline_app


class FakeTurso:
    """Stands in for Turso: runs the same SQL on an in-memory SQLite database."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def __call__(self, statements):
        out = [[dict(r) for r in self.conn.execute(sql, args).fetchall()] for sql, args in statements]
        self.conn.commit()
        return out

    def rows(self, table):
        return {r[0]: dict(r) for r in self.conn.execute(f"SELECT * FROM {table}")}

    def put_module(self, uid, content, updated_at, deleted=0):
        self.conn.execute(
            "INSERT OR REPLACE INTO nva_modules VALUES (?, 'Library', ?, 'manual', 'other laptop', ?, ?, "
            "strftime('%Y-%m-%dT%H:%M:%f', 'now'))",
            (uid, content, updated_at, deleted),
        )
        self.conn.commit()


@pytest.fixture
def turso(monkeypatch, index):
    fake = FakeTurso()
    monkeypatch.setattr(sync, "remote", fake)
    monkeypatch.setattr(sync, "enabled", lambda: True)
    monkeypatch.setattr(sync, "_schema_ready", False)
    db.init()
    sync.init()
    with db.connect() as conn:
        for table in ("modules", "faces", "roles", "profiles", "marks", "attendance", "module_uids", "outbox"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sync_meta WHERE k = 'pulled_until'")
    return fake


def synced():
    sync.sync_once()
    assert sync.status["state"] == "synced", sync.status
    return sync.current_status()["pending"]


def local_modules():
    return {m["id"]: m for m in db.list_modules()}


def test_local_changes_are_pushed(turso):
    module = db.create_module("Library", "Opens at 9", "manual", "admin@nmamit.in")
    vec = np.ones(128, dtype=np.float32)
    db.save_face("nnm23is001@nmamit.in", face.to_bytes(vec), "college photos")
    assert synced() == 0

    (uid, row), = turso.rows("nva_modules").items()
    assert uid.endswith(f"-{module['id']}") and row["content"] == "Opens at 9" and row["deleted"] == 0
    pushed = turso.rows("nva_faces")["nnm23is001@nmamit.in"]["embedding"]
    assert np.array_equal(face.from_bytes(base64.b64decode(pushed)), vec)

    db.delete_face("nnm23is001@nmamit.in")
    db.delete_module(module["id"])
    synced()
    assert turso.rows("nva_modules")[uid]["deleted"] == 1
    assert turso.rows("nva_faces")["nnm23is001@nmamit.in"]["deleted"] == 1


def test_backend_changes_are_pulled_and_indexed(turso, index):
    turso([(sql, []) for sql in sync.REMOTE_SCHEMA])
    turso.put_module("other-7", "Opens at 8", "2026-01-01T10:00:00+00:00")
    synced()
    (local_id, module), = local_modules().items()
    assert module["content"] == "Opens at 8" and index.modules[local_id]["content"] == "Opens at 8"

    turso.put_module("other-7", "Opens at 10", "2026-01-02T10:00:00+00:00")
    assert synced() == 0  # what came from the backend is not sent back
    assert local_modules()[local_id]["content"] == "Opens at 10"

    turso.put_module("other-7", None, "2026-01-03T10:00:00+00:00", deleted=1)
    synced()
    assert local_modules() == {} and local_id not in index.modules


def test_newer_side_wins(turso):
    turso([(sql, []) for sql in sync.REMOTE_SCHEMA])
    turso.put_module("other-1", "old remote", "2026-01-01T10:00:00+00:00")
    synced()
    (local_id, _), = local_modules().items()

    # A newer local edit beats the older backend copy, in both directions.
    db.update_module(local_id, "Library", "new local", "admin@nmamit.in")
    synced()
    assert turso.rows("nva_modules")["other-1"]["content"] == "new local"
    assert local_modules()[local_id]["content"] == "new local"

    # An offline laptop pushing an old edit later does not overwrite the newer one.
    with db.connect() as conn:
        conn.execute("UPDATE modules SET content = 'stale', updated_at = '2025-01-01T00:00:00+00:00' WHERE id = ?", (local_id,))
    synced()
    assert turso.rows("nva_modules")["other-1"]["content"] == "new local"
    assert local_modules()[local_id]["content"] == "new local"


def test_offline_keeps_changes_for_later(turso, monkeypatch):
    def no_internet(_statements):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(sync, "remote", no_internet)
    db.create_module("Canteen", "Open till 6", "manual", "admin@nmamit.in")
    sync.sync_once()
    assert sync.status["state"] == "offline"
    assert sync.current_status()["pending"] == 1

    monkeypatch.setattr(sync, "remote", turso)
    assert synced() == 0
    assert [r["content"] for r in turso.rows("nva_modules").values()] == ["Open till 6"]


def test_turso_http_request_and_reply(monkeypatch):
    sent = {}

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [
                {"type": "ok", "response": {"type": "execute", "result": {
                    "cols": [{"name": "n"}, {"name": "s"}, {"name": "z"}],
                    "rows": [[{"type": "integer", "value": "3"}, {"type": "text", "value": "hi"}, {"type": "null"}]],
                }}},
                {"type": "ok", "response": {"type": "close"}},
            ]}

    def post(url, json, headers, timeout):
        sent.update(url=url, body=json, auth=headers["Authorization"])
        return Reply()

    monkeypatch.setattr(sync.config, "TURSO_DATABASE_URL", "libsql://db.turso.io")
    monkeypatch.setattr(sync.config, "TURSO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(sync.requests, "post", post)
    assert sync.remote([("SELECT ?, ?, ?", [3, "hi", None])]) == [[{"n": 3, "s": "hi", "z": None}]]
    assert sent["url"] == "https://db.turso.io/v2/pipeline" and sent["auth"] == "Bearer tok"
    assert sent["body"]["requests"][0]["stmt"]["args"] == [
        {"type": "integer", "value": "3"}, {"type": "text", "value": "hi"}, {"type": "null"}]


def test_students_marks_and_roles_sync_too(turso):
    from app import academics

    academics.ensure_student("nnm23is001@nmamit.in", "NNM23IS001")
    db.save_role("teacher@nmamit.in", "Prof", "teacher", {"content": True, "attendance": False, "marks": True}, "admin")
    assert synced() == 0
    assert len(turso.rows("nva_marks")) == sum(len(academics.SUBJECTS[sem]) for sem in range(1, 6))
    assert len(turso.rows("nva_attendance")) == len(academics.SUBJECTS[6])
    assert list(turso.rows("nva_profiles")) == ["nnm23is001@nmamit.in"]
    assert turso.rows("nva_roles")["teacher@nmamit.in"]["can_marks"] == "1"

    # A teacher on another laptop corrects a mark; it comes down here and is not sent back.
    key = "nnm23is001@nmamit.in|1|MA1002-1"
    turso.conn.execute("UPDATE nva_marks SET internal = '50', updated_at = '2999-01-01T00:00:00+00:00', "
                       "synced_at = strftime('%Y-%m-%dT%H:%M:%f', 'now') WHERE id = ?", (key,))
    turso.conn.commit()
    assert synced() == 0
    assert [m for m in db.list_marks("nnm23is001@nmamit.in") if m["code"] == "MA1002-1"][0]["internal"] == 50


def test_faces_with_several_photos_sync_and_damaged_ones_are_skipped(turso):
    vecs = np.stack([np.ones(128, dtype=np.float32) * i for i in range(1, 7)])
    db.save_face("a@nmamit.in", face.to_bytes(vecs), "a@nmamit.in")
    assert synced() == 0
    pushed = turso.rows("nva_faces")["a@nmamit.in"]["embedding"]
    assert len(base64.b64decode(pushed)) == 6 * db.FACE_SIZE

    turso.conn.execute("INSERT INTO nva_faces VALUES ('bad@nmamit.in', ?, 'x', '2026-01-01T00:00:00+00:00', 0, "
                       "strftime('%Y-%m-%dT%H:%M:%f', 'now'))", (base64.b64encode(b"123").decode(),))
    turso.conn.commit()
    synced()
    assert db.get_face("bad@nmamit.in") is None and db.get_face("a@nmamit.in") is not None


# --- Face sign-in -----------------------------------------------------------------

def unit(*xy):
    v = np.zeros(128, dtype=np.float32)
    v[: len(xy)] = xy
    return v / np.linalg.norm(v)


OWNER = [f"me{i}".encode() for i in range(6)]


@pytest.fixture
def offline_client(monkeypatch, index):
    faces = {name: unit(1, 0.12 * i) for i, name in enumerate(OWNER)}
    faces.update({b"stranger": unit(0, 0, 1)})
    monkeypatch.setattr(face, "embedding", lambda data: faces[data])
    from app.auth import face_lockout

    face_lockout._fails.clear()
    with TestClient(offline_app, base_url="http://testserver") as c:
        with db.connect() as conn:
            for table in ("faces", "profiles", "marks", "attendance", "roles"):
                conn.execute(f"DELETE FROM {table}")
        yield c


def sign_in(client, roll, *photos):
    files = [("files", ("face.jpg", p, "image/jpeg")) for p in photos]
    return client.post("/api/login", data={"roll": roll}, files=files)


def status(client, roll):
    return client.post("/api/login/status", data={"roll": roll})


def test_first_sign_in_enrols_then_each_sign_in_is_a_fresh_scan(offline_client):
    assert status(offline_client, "NNM23IS001").json() == {"enrolled": False}

    res = sign_in(offline_client, "NNM23IS001", *OWNER)
    assert res.status_code == 200 and res.json() == {"enrolled_now": True}
    me = offline_client.get("/api/me").json()
    assert me["name"] == "NNM23IS001" and me["role"] == "student"
    assert len(offline_client.get("/api/marks").json()["semesters"]) == 5   # sample marks on sign-up

    offline_client.get("/logout")
    assert status(offline_client, "nnm23is001@nmamit.in").json() == {"enrolled": True}
    assert sign_in(offline_client, "NNM23IS001", b"stranger", b"stranger", b"stranger").status_code == 403
    assert offline_client.get("/api/me").status_code == 401
    res = sign_in(offline_client, "nnm23is001@nmamit.in", b"me2", b"me3", b"me4")
    assert res.status_code == 200 and res.json() == {"enrolled_now": False}


def test_sign_in_rejections(offline_client):
    assert sign_in(offline_client, "../etc", *OWNER).status_code == 400
    assert status(offline_client, "../etc").status_code == 400
    assert sign_in(offline_client, "NNM23IS001", b"me0", b"me1").status_code == 400    # too few photos to enrol
    assert offline_client.get("/api/me").status_code == 401
    assert offline_client.post("/api/ask", json={"question": "hi"}).status_code == 401
    assert offline_client.get("/marks", follow_redirects=False).status_code == 307


def test_offline_admin_pages_follow_roles(offline_client):
    sign_in(offline_client, "NNM23IS001", *OWNER)
    assert offline_client.get("/admin", follow_redirects=False).status_code == 307
    assert offline_client.get("/api/admin/staff").status_code == 403
    assert offline_client.get("/marks").status_code == 200
