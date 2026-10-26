import pytest

from app import main
from app.auth import FaceLockout, is_allowed_google_user, verify_firebase_token

from .conftest import login

GOOGLE = {"sign_in_provider": "google.com"}


def test_only_verified_college_google_accounts_are_allowed():
    ok = {"email": "Student@nmamit.in", "email_verified": True, "firebase": GOOGLE}
    assert is_allowed_google_user(ok)
    assert not is_allowed_google_user({**ok, "email": "x@gmail.com"})          # personal Gmail
    assert not is_allowed_google_user({**ok, "email_verified": False})
    assert not is_allowed_google_user({**ok, "email": "x@nmamit.in.evil.com"})
    assert not is_allowed_google_user({**ok, "email": "a@b@nmamit.in"})
    assert not is_allowed_google_user({**ok, "firebase": {"sign_in_provider": "password"}})
    assert not is_allowed_google_user({**ok, "firebase": None})


def test_garbage_token_is_rejected():
    with pytest.raises(Exception):
        verify_firebase_token("not-a-real-token")


def test_firebase_config_for_the_sign_in_page(client):
    body = client.get("/api/firebase-config").json()
    assert body == {
        "apiKey": "test-api-key",
        "authDomain": "test-project.firebaseapp.com",
        "projectId": "test-project",
        "allowedDomain": "nmamit.in",
    }


def test_sign_in_starts_a_session_for_college_accounts(client, monkeypatch):
    claims = {"email": "Student@nmamit.in", "email_verified": True, "name": "Stu", "firebase": GOOGLE}
    monkeypatch.setattr(main, "verify_firebase_token", lambda token: claims)
    res = client.post("/auth/session", json={"id_token": "x" * 40})
    assert res.status_code == 200 and res.json() == {"next": "/face"}
    me = client.get("/api/me").json()
    assert me["email"] == "student@nmamit.in" and me["name"] == "Stu" and me["face_ok"] is False


def test_sign_in_rejects_other_accounts_and_bad_tokens(client, monkeypatch):
    monkeypatch.setattr(main, "verify_firebase_token",
                        lambda token: {"email": "x@gmail.com", "email_verified": True, "firebase": GOOGLE})
    res = client.post("/auth/session", json={"id_token": "x" * 40})
    assert res.status_code == 403 and "@nmamit.in" in res.json()["detail"]
    assert client.get("/api/me").status_code == 401

    def bad(token):
        raise ValueError("bad signature")
    monkeypatch.setattr(main, "verify_firebase_token", bad)
    assert client.post("/auth/session", json={"id_token": "x" * 40}).status_code == 401


def test_signed_out_user_sees_login_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Sign in with your @nmamit.in" in res.text


def test_face_check_required_before_chat(client):
    login(client, "s@nmamit.in", face_ok=False)
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307 and res.headers["location"] == "/face"
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 403


def test_api_needs_sign_in(client):
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 401
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/admin/modules").status_code == 401


def test_admin_api_is_admin_only(client):
    login(client, "student@nmamit.in")
    assert client.get("/api/admin/modules").status_code == 403
    assert client.get("/admin", follow_redirects=False).status_code == 307
    login(client, "admin@nmamit.in")
    assert client.get("/api/admin/modules").status_code == 200
    assert client.get("/admin").status_code == 200


def test_admin_still_needs_face_check(client):
    login(client, "admin@nmamit.in", face_ok=False)
    assert client.get("/api/admin/modules").status_code == 403


def test_cross_site_posts_are_blocked(client):
    login(client, "admin@nmamit.in")
    res = client.post(
        "/api/admin/modules",
        json={"title": "t", "content": "c"},
        headers={"Origin": "https://evil.example"},
    )
    assert res.status_code == 403


def test_face_verify_without_registered_face(client):
    login(client, "new@nmamit.in", face_ok=False)
    res = client.post("/api/face/verify", files={"file": ("f.jpg", b"x", "image/jpeg")})
    assert res.status_code == 404
    assert "not registered" in res.json()["detail"]


def test_face_lockout_after_too_many_failures():
    lock = FaceLockout(max_failures=3, lock_seconds=600)
    for _ in range(2):
        lock.fail("a@nmamit.in")
    assert lock.seconds_left("a@nmamit.in") == 0
    assert lock.tries_left("a@nmamit.in") == 1
    lock.fail("a@nmamit.in")
    assert lock.seconds_left("a@nmamit.in") > 0
    assert lock.seconds_left("b@nmamit.in") == 0
    lock.reset("a@nmamit.in")
    assert lock.seconds_left("a@nmamit.in") == 0


def test_me(client):
    login(client, "admin@nmamit.in", name="Admin")
    body = client.get("/api/me").json()
    assert body == {
        "email": "admin@nmamit.in",
        "name": "Admin",
        "face_ok": True,
        "face_enrolled": False,
        "is_admin": True,
        "entries": 0,
    }
    client.post("/api/admin/modules", json={"title": "Library", "content": "Open at 9."})
    assert client.get("/api/me").json()["entries"] == 1
