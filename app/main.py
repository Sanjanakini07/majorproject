"""The web app: pages, sign-in, face check and the question endpoint.

Run with:  uvicorn app.main:app --reload
"""
import json
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import admin, config, db, face, rag
from .auth import (
    ask_limit,
    face_lockout,
    is_admin,
    is_allowed_google_user,
    signed_in_user,
    verified_user,
    verify_firebase_token,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

APP_DIR = config.BASE_DIR / "app"
PAGES = APP_DIR / "pages"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    if not config.FIREBASE_API_KEY or not config.FIREBASE_PROJECT_ID:
        log.warning("FIREBASE_API_KEY / FIREBASE_PROJECT_ID are not set: sign-in will not work. See README.")
    if not config.GROQ_API_KEY:
        log.warning("GROQ_API_KEY is not set: questions can't be answered. See README.")
    if not config.ADMIN_EMAILS:
        log.warning("ADMIN_EMAILS is empty: nobody can open the admin panel.")
    yield


app = FastAPI(title="NMAMIT Campus Voice Assistant", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="nva_session",
    max_age=config.SESSION_HOURS * 3600,
    same_site="lax",
    https_only=config.HTTPS_ONLY,
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.include_router(admin.router)


# Google sign-in runs Firebase's script from gstatic.com, which talks to Google's
# sign-in services and opens a helper frame on the Firebase project's own domain.
CSP = (
    "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
    "script-src 'self' https://www.gstatic.com https://apis.google.com; "
    "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com "
    "https://www.googleapis.com; "
    f"frame-src https://{config.FIREBASE_AUTH_DOMAIN} https://accounts.google.com; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def security(request: Request, call_next):
    # Block form posts and fetches coming from other websites (CSRF).
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        allowed = {request.headers.get("host"), urlparse(config.BASE_URL).netloc}
        if origin and urlparse(origin).netloc not in allowed:
            return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self)"
    return response


# --- Pages -----------------------------------------------------------------------

def page(name: str) -> FileResponse:
    return FileResponse(PAGES / name, headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
def home(request: Request):
    session = request.session
    if not session.get("email"):
        return page("login.html")
    if not session.get("face_ok"):
        return RedirectResponse("/face")
    return page("chat.html")


@app.get("/face", include_in_schema=False)
def face_page(request: Request):
    if not request.session.get("email"):
        return RedirectResponse("/")
    if request.session.get("face_ok"):
        return RedirectResponse("/")
    return page("face.html")


@app.get("/admin", include_in_schema=False)
def admin_page(request: Request):
    session = request.session
    if not session.get("email") or not session.get("face_ok"):
        return RedirectResponse("/")
    if not is_admin(session["email"]):
        return RedirectResponse("/")
    return page("admin.html")


# --- Google sign-in ---------------------------------------------------------------

@app.get("/api/firebase-config")
def firebase_config():
    """Public settings the sign-in page needs to show Google's sign-in window."""
    if not config.FIREBASE_API_KEY or not config.FIREBASE_PROJECT_ID:
        raise HTTPException(503, "Google sign-in is not set up on this server yet. See the README.")
    return {
        "apiKey": config.FIREBASE_API_KEY,
        "authDomain": config.FIREBASE_AUTH_DOMAIN,
        "projectId": config.FIREBASE_PROJECT_ID,
        "allowedDomain": config.ALLOWED_DOMAIN,
    }


class SignInIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=5000)


@app.post("/auth/session")
def sign_in(body: SignInIn, request: Request):
    """The page signed in with Google through Firebase; check the result and start a session."""
    try:
        claims = verify_firebase_token(body.id_token)
    except Exception as e:  # bad, expired or forged token, or Google's keys unreachable
        log.warning("Sign-in token rejected: %s", e)
        raise HTTPException(401, "Google sign-in could not be checked. Please try again.")

    request.session.clear()  # always start a fresh session after sign-in
    if not is_allowed_google_user(claims):
        log.info("Rejected sign-in from outside %s", config.ALLOWED_DOMAIN)
        raise HTTPException(403, f"Please use your @{config.ALLOWED_DOMAIN} college Google account.")

    email = claims["email"].lower()
    request.session.update({"email": email, "name": claims.get("name") or email, "face_ok": False})
    return {"next": "/face"}


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


@app.get("/api/me")
def me(user: dict = Depends(signed_in_user)):
    return {
        "email": user["email"],
        "name": user["name"],
        "face_ok": bool(user.get("face_ok")),
        "face_enrolled": db.get_face(user["email"]) is not None,
        "is_admin": is_admin(user["email"]),
        "entries": db.count_modules(),
    }


# --- Face check --------------------------------------------------------------------

@app.post("/api/face/verify")
async def verify_face(request: Request, file: UploadFile = File(...), user: dict = Depends(signed_in_user)):
    email = user["email"]
    wait = face_lockout.seconds_left(email)
    if wait:
        raise HTTPException(429, f"Too many failed tries. Try again in {wait // 60 + 1} minutes.")

    stored = db.get_face(email)
    if stored is None:
        raise HTTPException(404, "Your face is not registered yet. Ask an admin to add your photo.")

    data = await admin.read_upload(file, admin.MAX_IMAGE_BYTES)
    try:
        live = face.embedding(data)
    except face.FaceError as e:
        # A blurry or empty frame is not counted as a failed try.
        raise HTTPException(400, str(e))

    ok, score = face.is_match(live, face.from_bytes(stored))
    log.info("Face check for %s: score=%.3f match=%s", email, score, ok)
    if not ok:
        face_lockout.fail(email)
        left = face_lockout.tries_left(email)
        raise HTTPException(403, f"Face did not match. {left} tries left.")

    face_lockout.reset(email)
    request.session["face_ok"] = True
    return {"ok": True}


# --- Questions ---------------------------------------------------------------------

class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _line(obj: dict) -> bytes:
    return (json.dumps(obj) + "\n").encode()


@app.post("/api/ask")
def ask(body: AskIn, user: dict = Depends(verified_user)):
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Ask a question first.")
    if not ask_limit.allow(user["email"]):
        raise HTTPException(429, "You're asking very fast. Wait a minute and try again.")

    def steps():
        # Each line tells the page which step we're on, so it can show progress.
        yield _line({"stage": "searching"})
        try:
            hits = rag.search(question)
            sources = list(dict.fromkeys(h["title"] for h in hits))
            yield _line({"stage": "thinking", "sources": sources})
            answer = rag.answer(question, hits)
        except Exception:
            log.exception("Answering failed")
            yield _line({"stage": "error", "message": "Sorry, something went wrong while answering. Please try again."})
            return
        yield _line({"stage": "done", "answer": answer, "sources": sources})

    return StreamingResponse(steps(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})
