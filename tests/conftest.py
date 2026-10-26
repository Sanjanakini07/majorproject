import base64
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Settings must be in place before the app is imported.
_tmp = tempfile.mkdtemp(prefix="nva-test-")
os.environ.update(
    {
        "DATA_DIR": _tmp,
        "SECRET_KEY": "test-secret",
        "ADMIN_EMAILS": "admin@nmamit.in",
        "FIREBASE_API_KEY": "test-api-key",
        "FIREBASE_PROJECT_ID": "test-project",
        "GROQ_API_KEY": "",
        "FACE_MAX_FAILURES": "10",
        "FACE_MATCH_THRESHOLD": "0.363",
        "TURSO_DATABASE_URL": "",  # tests must never sync with the real backend
        "TURSO_AUTH_TOKEN": "",
    }
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from itsdangerous import TimestampSigner  # noqa: E402

from app import db, rag  # noqa: E402
from app.main import app  # noqa: E402


class FakeIndex:
    """Stands in for ChromaDB so tests don't download the embedding model."""

    def __init__(self):
        self.modules = {}

    def index_module(self, module):
        self.modules[module["id"]] = module

    def remove_module(self, module_id):
        self.modules.pop(module_id, None)

    def rebuild(self, modules):
        self.modules = {m["id"]: m for m in modules}
        return len(self.modules)

    def search(self, question, k=4):
        words = set(question.lower().split())
        return [
            {"title": m["title"], "text": m["content"], "distance": 0.1}
            for m in self.modules.values()
            if words & set(m["content"].lower().split())
        ][:k]


@pytest.fixture
def index(monkeypatch):
    fake = FakeIndex()
    for name in ("index_module", "remove_module", "rebuild", "search"):
        monkeypatch.setattr(rag, name, getattr(fake, name))
    return fake


@pytest.fixture
def client(index):
    db.init()
    with db.connect() as conn:
        for table in ("modules", "faces", "roles", "profiles", "marks", "attendance"):
            conn.execute(f"DELETE FROM {table}")
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def login(client, email, face_ok=True, name="Test User"):
    """Put a signed session cookie on the client, as if Google sign-in had happened."""
    client.cookies.clear()  # a response may have set its own session cookie
    data = base64.b64encode(json.dumps({"email": email, "name": name, "face_ok": face_ok}).encode())
    client.cookies.set("nva_session", TimestampSigner("test-secret").sign(data).decode())
