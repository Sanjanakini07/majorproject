"""Face enrolment, roles and permissions, and the marks and attendance pages' data."""
import numpy as np
import pytest

from app import academics, db, face
from app.auth import face_lockout

from .conftest import login


def unit(*xy):
    v = np.zeros(128, dtype=np.float32)
    v[: len(xy)] = xy
    return v / np.linalg.norm(v)


# Six "photos" of one person turning their head, and a stranger.
OWNER = {f"me{i}".encode(): unit(1, 0.12 * i) for i in range(6)}
FACES = {**OWNER, b"stranger": unit(0, 0, 1), b"other": unit(0, 0, 0, 1)}


@pytest.fixture(autouse=True)
def fake_faces(monkeypatch):
    monkeypatch.setattr(face, "embedding", lambda data: FACES[data])
    face_lockout._fails.clear()


def photos(*names):
    return [("files", (f"{n}.jpg", n if isinstance(n, bytes) else n.encode(), "image/jpeg")) for n in names]


def enroll(client, email="nnm23is001@nmamit.in", names=tuple(OWNER)):
    login(client, email, face_ok=False)
    return client.post("/api/face/enroll", files=photos(*names))


# --- Face enrolment and sign-in ----------------------------------------------------

def test_first_sign_in_enrols_six_photos_and_creates_the_student(client):
    res = enroll(client)
    assert res.status_code == 200, res.text
    assert len(db.get_face("nnm23is001@nmamit.in")) == 6 * db.FACE_SIZE
    me = client.get("/api/me").json()
    assert me["face_ok"] and me["face_enrolled"] and me["role"] == "student"
    assert me["permissions"] == {"content": False, "attendance": False, "marks": False}

    marks = client.get("/api/marks").json()
    assert [s["semester"] for s in marks["semesters"]] == [1, 2, 3, 4, 5]
    assert all(len(s["subjects"]) == 6 for s in marks["semesters"])
    assert marks["student"]["branch"] == "IS"
    assert client.get("/api/attendance").json()["subjects"]


def test_enrolment_needs_enough_clear_photos_of_one_person(client):
    assert enroll(client, names=(b"me0", b"me1", b"me2")).status_code == 400   # too few
    mixed = (b"me0", b"me1", b"me2", b"me3", b"stranger", b"other")
    res = enroll(client, names=mixed)
    assert res.status_code == 400 and "same person" in res.json()["detail"]
    assert db.get_face("nnm23is001@nmamit.in") is None


def test_enrolled_face_cannot_be_replaced_without_an_admin_reset(client):
    assert enroll(client).status_code == 200
    assert client.post("/api/face/enroll", files=photos(*OWNER)).status_code == 409


def test_every_sign_in_takes_fresh_photos_and_most_must_match(client):
    enroll(client)
    login(client, "nnm23is001@nmamit.in", face_ok=False)

    assert client.post("/api/face/verify", files=photos(b"me1", b"me3", b"me5")).status_code == 200
    login(client, "nnm23is001@nmamit.in", face_ok=False)
    assert client.post("/api/face/verify", files=photos(b"me1", b"stranger", b"me4")).status_code == 200   # 2 of 3

    login(client, "nnm23is001@nmamit.in", face_ok=False)
    res = client.post("/api/face/verify", files=photos(b"stranger", b"other", b"me1"))
    assert res.status_code == 403 and "9 tries left" in res.json()["detail"]
    assert not client.get("/api/me").json()["face_ok"]


def test_ten_wrong_scans_lock_the_account(client):
    enroll(client)
    login(client, "nnm23is001@nmamit.in", face_ok=False)
    for left in range(9, -1, -1):
        res = client.post("/api/face/verify", files=photos(b"stranger"))
        assert res.status_code == 403 and f"{left} {'try' if left == 1 else 'tries'} left" in res.json()["detail"]
    assert client.post("/api/face/verify", files=photos(*OWNER)).status_code == 429


def test_admin_reset_lets_someone_enrol_again(client):
    enroll(client)
    login(client, "admin@nmamit.in")
    assert [f["email"] for f in client.get("/api/admin/faces").json()] == ["nnm23is001@nmamit.in"]
    assert client.delete("/api/admin/faces/nnm23is001@nmamit.in").status_code == 204
    assert enroll(client).status_code == 200


def test_old_single_photo_faces_count_as_not_enrolled(client):
    db.save_face("old@nmamit.in", face.to_bytes(unit(1)), "college photos")
    assert db.get_face("old@nmamit.in") is None
    assert db.list_faces() == []


# --- Roles and permissions ---------------------------------------------------------

def add_teacher(client, email="teacher@nmamit.in", **perms):
    login(client, "admin@nmamit.in")
    body = {"email": email, "role": "teacher", "content": False, "attendance": False, "marks": False, **perms}
    res = client.post("/api/admin/staff", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_students_only_view_and_only_their_own(client):
    enroll(client, "nnm23is001@nmamit.in")
    enroll(client, "nnm23is002@nmamit.in")
    assert client.get("/api/marks?email=nnm23is001@nmamit.in").status_code == 403
    assert client.get("/api/marks?email=nnm23is002@nmamit.in").status_code == 200   # themselves
    assert client.get("/api/students").status_code == 403
    assert client.get("/api/admin/modules").status_code == 403
    assert client.get("/api/admin/staff").status_code == 403
    body = {"email": "nnm23is002@nmamit.in", "semester": 1, "code": "21MA101", "internal": 50, "external": 50}
    assert client.put("/api/marks", json=body).status_code == 403
    att = {"email": "nnm23is002@nmamit.in", "semester": 6, "code": "21IS601", "attended": 40, "total": 40}
    assert client.put("/api/attendance", json=att).status_code == 403
    assert client.post("/api/admin/modules", json={"title": "t", "content": "c"}).status_code == 403


def test_teacher_edits_only_what_an_admin_allowed(client):
    enroll(client, "nnm23is001@nmamit.in")
    add_teacher(client, marks=True)

    login(client, "teacher@nmamit.in")
    me = client.get("/api/me").json()
    assert me["role"] == "teacher" and me["permissions"] == {"content": False, "attendance": False, "marks": True}
    assert client.get("/admin").status_code == 200
    assert client.get("/api/students").json()[0]["email"] == "nnm23is001@nmamit.in"
    assert client.get("/api/marks?email=nnm23is001@nmamit.in").status_code == 200

    mark = {"email": "nnm23is001@nmamit.in", "semester": 1, "code": "21MA101", "internal": 41, "external": 44}
    assert client.put("/api/marks", json=mark).status_code == 200
    subjects = client.get("/api/marks?email=nnm23is001@nmamit.in").json()["semesters"][0]["subjects"]
    updated = next(s for s in subjects if s["code"] == "21MA101")
    assert (updated["internal"], updated["external"], updated["total"]) == (41, 44, 85)

    att = {"email": "nnm23is001@nmamit.in", "semester": 6, "code": "21IS601", "attended": 30, "total": 40}
    assert client.put("/api/attendance", json=att).status_code == 403          # not allowed
    assert client.post("/api/admin/modules", json={"title": "t", "content": "c"}).status_code == 403
    assert client.get("/api/admin/modules").status_code == 200                 # can read
    assert client.get("/api/admin/staff").status_code == 403                   # admins only
    assert client.delete("/api/admin/faces/nnm23is001@nmamit.in").status_code == 403


def test_admin_changes_access_and_it_applies_straight_away(client):
    enroll(client, "nnm23is001@nmamit.in")
    add_teacher(client)
    att = {"email": "nnm23is001@nmamit.in", "semester": 6, "code": "21IS601", "attended": 30, "total": 40}
    login(client, "teacher@nmamit.in")
    assert client.put("/api/attendance", json=att).status_code == 403

    add_teacher(client, attendance=True, content=True)
    login(client, "teacher@nmamit.in")                      # the same session would do; this just re-sets the cookie
    assert client.put("/api/attendance", json=att).status_code == 200
    assert client.post("/api/admin/modules", json={"title": "Canteen", "content": "Open till 6"}).status_code == 201

    add_teacher(client)                                    # switch everything off again
    login(client, "teacher@nmamit.in")
    assert client.put("/api/attendance", json=att).status_code == 403

    login(client, "admin@nmamit.in")
    assert client.delete("/api/admin/staff/teacher@nmamit.in").status_code == 204
    login(client, "teacher@nmamit.in")
    assert client.get("/api/me").json()["role"] == "student"


def test_attendance_cannot_exceed_classes_held(client):
    enroll(client, "nnm23is001@nmamit.in")
    login(client, "admin@nmamit.in")
    att = {"email": "nnm23is001@nmamit.in", "semester": 6, "code": "21IS601", "attended": 41, "total": 40}
    assert client.put("/api/attendance", json=att).status_code == 422
    bad_mark = {"email": "nnm23is001@nmamit.in", "semester": 1, "code": "21MA101", "internal": 51, "external": 0}
    assert client.put("/api/marks", json=bad_mark).status_code == 422
    unknown = {**bad_mark, "internal": 10, "code": "NOPE"}
    assert client.put("/api/marks", json=unknown).status_code == 404


def test_staff_rules(client):
    login(client, "admin@nmamit.in")
    bad = client.post("/api/admin/staff", json={"email": "x@gmail.com", "role": "teacher"})
    assert bad.status_code == 400
    assert client.post("/api/admin/staff", json={"email": "x@nmamit.in", "role": "owner"}).status_code == 422
    # The admin from the server settings can't be changed or removed, and nobody removes themselves.
    assert client.post("/api/admin/staff", json={"email": "admin@nmamit.in", "role": "teacher"}).status_code == 409
    assert client.delete("/api/admin/staff/admin@nmamit.in").status_code == 409
    listed = client.get("/api/admin/staff").json()
    assert listed[0]["email"] == "admin@nmamit.in" and listed[0]["fixed"]

    add_teacher(client, "second.admin@nmamit.in", content=True)
    client.post("/api/admin/staff", json={"email": "second.admin@nmamit.in", "role": "admin"})
    login(client, "second.admin@nmamit.in")
    assert client.get("/api/me").json()["permissions"] == {"content": True, "attendance": True, "marks": True}
    assert client.delete("/api/admin/staff/second.admin@nmamit.in").status_code == 409   # themselves
    demote = client.post("/api/admin/staff", json={"email": "second.admin@nmamit.in", "role": "teacher"})
    assert demote.status_code == 409


def test_pages_follow_the_role(client):
    login(client, "student@nmamit.in")
    assert client.get("/marks").status_code == 200
    assert client.get("/attendance").status_code == 200
    assert client.get("/admin", follow_redirects=False).status_code == 307
    login(client, "student@nmamit.in", face_ok=False)
    assert client.get("/marks", follow_redirects=False).status_code == 307


# --- Sample data -------------------------------------------------------------------

def test_sample_marks_are_random_but_stable_and_believable():
    marks, attendance = academics.sample_records("nnm23is186@nmamit.in")
    again, _ = academics.sample_records("nnm23is186@nmamit.in")
    other, _ = academics.sample_records("nnm23is187@nmamit.in")
    assert marks == again and marks != other
    assert len(marks) == 5 * 6 and len(attendance) == 6
    assert all(0 <= m["internal"] <= 50 and 0 <= m["external"] <= 50 for m in marks)
    assert all(m["internal"] + m["external"] >= 40 for m in marks)
    assert all(0 < a["attended"] <= a["total"] for a in attendance)
    assert len({m["internal"] + m["external"] for m in marks}) > 10    # not all the same number


def test_grades_and_branch():
    assert [academics.grade(p) for p in (95, 85, 75, 65, 55, 45, 30)] == ["O", "A+", "A", "B+", "B", "C", "F"]
    assert academics.branch_of("nnm23is186@nmamit.in") == "IS"
    assert academics.branch_of("nnm23cs004@nmamit.in") == "CS"
    assert academics.branch_of("admin@nmamit.in") == ""
