import json
from pathlib import Path

from app import rag

from .conftest import login

SAMPLES = Path(__file__).resolve().parent.parent / "sample_data"


def stream(res):
    return [json.loads(line) for line in res.text.splitlines() if line.strip()]


def test_module_create_update_delete_updates_index(client, index):
    login(client, "admin@nmamit.in")
    created = client.post("/api/admin/modules", json={"title": " Library ", "content": "Opens at 8:30 AM"}).json()
    assert created["title"] == "Library" and created["updated_by"] == "admin@nmamit.in"
    assert index.modules[created["id"]]["content"] == "Opens at 8:30 AM"

    updated = client.put(f"/api/admin/modules/{created['id']}", json={"title": "Library", "content": "Opens at 9 AM"})
    assert updated.status_code == 200
    assert index.modules[created["id"]]["content"] == "Opens at 9 AM"

    assert client.delete(f"/api/admin/modules/{created['id']}").status_code == 204
    assert created["id"] not in index.modules
    assert client.get("/api/admin/modules").json() == []
    assert client.delete(f"/api/admin/modules/{created['id']}").status_code == 404


def test_blank_module_is_rejected(client):
    login(client, "admin@nmamit.in")
    assert client.post("/api/admin/modules", json={"title": "  ", "content": "x"}).status_code == 422


def test_csv_import(client, index):
    login(client, "admin@nmamit.in")
    for name, expected in (("sample_knowledge.csv", 3), ("sample_timetable.csv", 3)):
        path = SAMPLES / name
        res = client.post("/api/admin/modules/import-csv", files={"file": (name, path.read_bytes(), "text/csv")})
        assert res.status_code == 201, res.text
        assert res.json() == {"added": expected}
    titles = [m["title"] for m in client.get("/api/admin/modules").json()]
    assert "Library timings (sample)" in titles
    assert "sample_timetable - row 1" in titles
    assert len(index.modules) == 6


def test_ask_streams_progress_and_answer(client, index, monkeypatch):
    login(client, "admin@nmamit.in")
    client.post("/api/admin/modules", json={"title": "Library", "content": "The library opens at 8:30 AM"})
    monkeypatch.setattr(rag, "answer", lambda q, hits, personal="": f"Answer from {hits[0]['title']}")

    login(client, "student@nmamit.in")
    events = stream(client.post("/api/ask", json={"question": "when does the library open"}))
    assert [e["stage"] for e in events] == ["searching", "thinking", "done"]
    assert events[-1]["answer"] == "Answer from Library"
    assert events[-1]["sources"] == ["Library"]


def test_ask_with_no_matching_knowledge_says_so(client):
    login(client, "student@nmamit.in")
    events = stream(client.post("/api/ask", json={"question": "zzz"}))
    assert "don't have any information" in events[-1]["answer"]


def test_ask_reports_ai_failure_without_details(client, index):
    login(client, "admin@nmamit.in")
    client.post("/api/admin/modules", json={"title": "Fees", "content": "fees are due in November"})
    events = stream(client.post("/api/ask", json={"question": "when are fees due"}))  # no GROQ_API_KEY
    assert events[-1]["stage"] == "error"
    assert "GROQ" not in events[-1]["message"]


def test_question_length_is_limited(client):
    login(client, "student@nmamit.in")
    assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 422
