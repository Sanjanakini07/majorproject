"""Notes (PDF or pasted text), events, who may add them, and the assistant finding them."""
import json

import pytest

from app import db, library, rag

from .conftest import login


def make_pdf(text: str) -> bytes:
    """A tiny one-page PDF containing real, extractable text."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, xref)
    return out


@pytest.fixture(autouse=True)
def subjects(client):
    library.seed_subjects()


def add_teacher(client, content):
    login(client, "admin@nmamit.in")
    body = {"email": "t@nmamit.in", "role": "teacher", "content": content, "attendance": False, "marks": False}
    assert client.post("/api/admin/staff", json=body).status_code == 201


def test_subjects_follow_the_official_syllabus():
    subs = db.list_subjects()
    assert sorted({s["semester"] for s in subs}) == list(range(1, 9))
    by_code = {s["code"]: s for s in subs}
    assert by_code["MA1002-1"]["semester"] == 1 and by_code["MA1002-1"]["name"] == "Calculus and Differential Equations"
    assert by_code["IS3101-1"]["name"] == "Operating Systems Fundamentals" and by_code["IS3101-1"]["semester"] == 5
    assert by_code["IS3102-1"]["semester"] == 6
    assert "Deep Learning (Professional Elective, Group 2)" in {s["name"] for s in subs}
    count = len(subs)
    library.seed_subjects()
    assert len(db.list_subjects()) == count   # seeding twice adds nothing


def test_pdf_text_is_extracted():
    assert "Round robin scheduling" in library.pdf_text(make_pdf("Round robin scheduling"))


def test_admin_adds_text_and_pdf_notes_and_students_only_view(client, index):
    login(client, "admin@nmamit.in")
    text = client.post("/api/notes", data={"subject": "IS3101-1", "title": "Unit 1", "text": "A process is a program in execution."})
    assert text.status_code == 201 and text.json()["readable"]
    pdf = client.post("/api/notes", data={"subject": "IS3101-1", "title": "Unit 2 PDF"},
                      files={"file": ("unit2.pdf", make_pdf("Deadlock needs four conditions"), "application/pdf")})
    assert pdf.status_code == 201 and pdf.json()["readable"]

    login(client, "student@nmamit.in")
    notes = client.get("/api/notes?subject=IS3101-1").json()
    assert [n["title"] for n in notes] == ["Unit 2 PDF", "Unit 1"]
    assert notes[1]["text"] == "A process is a program in execution."
    file = client.get(f"/api/notes/{notes[0]['id']}/file")
    assert file.status_code == 200 and file.content.startswith(b"%PDF-") and file.headers["content-type"] == "application/pdf"
    assert "attachment" in client.get(f"/api/notes/{notes[0]['id']}/file?download=true").headers["content-disposition"]
    assert [s["notes"] for s in client.get("/api/subjects").json() if s["code"] == "IS3101-1"] == [2]

    # Students cannot add or delete.
    assert client.post("/api/notes", data={"subject": "IS3101-1", "title": "x", "text": "y"}).status_code == 403
    assert client.delete(f"/api/notes/{notes[0]['id']}").status_code == 403


def test_assistant_finds_notes_and_links_to_them(client, index, monkeypatch):
    login(client, "admin@nmamit.in")
    client.post("/api/notes", data={"subject": "CS2102-1", "title": "Normal forms", "text": "Third normal form removes transitive dependency."})
    note = db.list_notes("CS2102-1")[0]
    assert note["module_id"] in index.modules          # indexed for the assistant
    assert all(m["source"] != "note" for m in client.get("/api/admin/modules").json())   # not mixed into Knowledge

    login(client, "student@nmamit.in")
    monkeypatch.setattr(rag, "answer", lambda q, hits, personal="": hits[0]["title"])
    res = client.post("/api/ask", json={"question": "what is third normal form transitive"})
    events = [json.loads(line) for line in res.text.splitlines() if line.strip()]
    done = events[-1]
    assert done["stage"] == "done"
    assert done["links"] == [{"title": "Normal forms", "label": "Notes", "url": "/notes?sem=4&subject=CS2102-1"}]


def test_deleting_notes_also_removes_them_from_the_assistant(client, index):
    login(client, "admin@nmamit.in")
    client.post("/api/notes", data={"subject": "IS3001-1", "title": "TCP", "text": "TCP is connection oriented."})
    note = db.list_notes("IS3001-1")[0]
    assert client.delete(f"/api/notes/{note['id']}").status_code == 204
    assert note["module_id"] not in index.modules and db.get_module(note["module_id"]) is None
    assert client.get(f"/api/notes/{note['id']}/file").status_code == 404


def test_note_validation(client):
    login(client, "admin@nmamit.in")
    assert client.post("/api/notes", data={"subject": "NOPE", "title": "t", "text": "x"}).status_code == 404
    assert client.post("/api/notes", data={"subject": "IS3001-1", "title": "t"}).status_code == 422       # nothing to add
    assert client.post("/api/notes", data={"subject": "IS3001-1", "title": "  ", "text": "x"}).status_code == 422
    fake = client.post("/api/notes", data={"subject": "IS3001-1", "title": "t"},
                       files={"file": ("a.pdf", b"not really a pdf", "application/pdf")})
    assert fake.status_code == 400 and "Only PDF" in fake.json()["detail"]
    broken = client.post("/api/notes", data={"subject": "IS3001-1", "title": "t"},
                         files={"file": ("a.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    assert broken.status_code == 400


def test_pdf_without_text_is_saved_but_flagged(client, monkeypatch):
    monkeypatch.setattr(library, "pdf_text", lambda data: "")
    login(client, "admin@nmamit.in")
    res = client.post("/api/notes", data={"subject": "IS3001-1", "title": "Scanned"},
                      files={"file": ("s.pdf", make_pdf("x"), "application/pdf")})
    assert res.status_code == 201 and res.json()["readable"] is False
    assert db.list_notes("IS3001-1")[0]["module_id"] is None


def test_teacher_needs_content_permission(client, index):
    add_teacher(client, content=False)
    login(client, "t@nmamit.in")
    assert client.post("/api/notes", data={"subject": "IS3101-1", "title": "t", "text": "x"}).status_code == 403
    assert client.post("/api/events", data={"title": "t", "event_date": "2030-01-01"}).status_code == 403
    assert client.get("/api/notes?subject=IS3101-1").status_code == 200

    add_teacher(client, content=True)
    login(client, "t@nmamit.in")
    assert client.post("/api/notes", data={"subject": "IS3101-1", "title": "t", "text": "x"}).status_code == 201
    assert client.post("/api/events", data={"title": "t", "event_date": "2030-01-01"}).status_code == 201


def test_events_with_text_and_pdf(client, index):
    login(client, "admin@nmamit.in")
    ok = client.post("/api/events", data={
        "title": "Tech Fest", "event_date": "2030-03-14", "start_time": "10:30", "venue": "Main auditorium",
        "description": "Bring your ID card."}, files={"file": ("poster.pdf", make_pdf("Hackathon starts at nine"), "application/pdf")})
    assert ok.status_code == 201
    ev = db.list_events()[0]
    module = index.modules[ev["module_id"]]
    assert "Thursday 14 March 2030, 10:30 AM" in module["content"] and "Main auditorium" in module["content"]
    assert "Hackathon starts at nine" in module["content"]

    login(client, "student@nmamit.in")
    listed = client.get("/api/events").json()
    assert listed[0]["title"] == "Tech Fest" and listed[0]["has_file"] == 1
    assert client.get(f"/api/events/{listed[0]['id']}/file").content.startswith(b"%PDF-")
    assert client.delete(f"/api/events/{listed[0]['id']}").status_code == 403

    login(client, "admin@nmamit.in")
    assert client.delete(f"/api/events/{listed[0]['id']}").status_code == 204
    assert ev["module_id"] not in index.modules and client.get("/api/events").json() == []


def test_event_validation(client):
    login(client, "admin@nmamit.in")
    assert client.post("/api/events", data={"title": "x", "event_date": "soon"}).status_code == 422
    assert client.post("/api/events", data={"title": "x", "event_date": "2030-01-01", "start_time": "25:99"}).status_code == 422
    assert client.post("/api/events", data={"title": " ", "event_date": "2030-01-01"}).status_code == 422


def test_pages_need_sign_in(client):
    assert client.get("/notes", follow_redirects=False).status_code == 307
    login(client, "student@nmamit.in")
    assert client.get("/notes").status_code == 200 and client.get("/events").status_code == 200
    assert client.get("/api/notes?subject=IS3101-1").status_code == 200
    login(client, "student@nmamit.in", face_ok=False)
    assert client.get("/api/events").status_code == 403
