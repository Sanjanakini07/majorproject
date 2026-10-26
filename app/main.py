"""The web app: pages, sign-in, face check and the question endpoint.

Run with:  uvicorn app.main:app --reload
"""
import json
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import academics, admin, config, db, facelogin, library, portal, rag
from .auth import (
    ask_limit,
    is_allowed_google_user,
    role_of,
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
    library.seed_subjects()
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
app.include_router(portal.router)
app.include_router(library.router)


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
async def normalize_localhost(request: Request, call_next):
    """Use localhost consistently so Firebase accepts the sign-in flow even if the browser hits 127.0.0.1."""
    host = request.headers.get("host", "").split(":", 1)[0].strip("[]").lower()
    if host in {"127.0.0.1", "::1"}:
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        netloc = f"localhost:{port}" if port not in (80, 443) else "localhost"
        return RedirectResponse(request.url.replace(netloc=netloc), status_code=307)
    return await call_next(request)


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
    if request.url.path.startswith(("/static/", "/offline/")):
        # Always re-check with the server, so an updated page never runs with old scripts or styles.
        response.headers["Cache-Control"] = "no-cache"
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


# --- Face check --------------------------------------------------------------------
# First sign-in: enrol several photos. Every later sign-in: fresh photos are compared with them.

@app.post("/api/face/enroll")
async def enroll_face(request: Request, files: list[UploadFile] = File(...), user: dict = Depends(signed_in_user)):
    email = user["email"]
    if db.get_face(email) is not None:
        raise HTTPException(409, "Your face is already enrolled. Ask an admin to reset it if you need to redo it.")
    images = await facelogin.read_images(files)
    await run_in_threadpool(facelogin.enroll, email, images, email)
    if role_of(email) == "student":
        academics.ensure_student(email, user["name"])
    request.session["face_ok"] = True
    return {"ok": True}


@app.post("/api/face/verify")
async def verify_face(request: Request, files: list[UploadFile] = File(...), user: dict = Depends(signed_in_user)):
    images = await facelogin.read_images(files)
    await run_in_threadpool(facelogin.verify, user["email"], images)
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
            links = library.links_for([h.get("module_id") for h in hits])
            yield _line({"stage": "thinking", "sources": sources})
            answer = rag.answer(question, hits)
        except Exception:
            log.exception("Answering failed")
            yield _line({"stage": "error", "message": "Sorry, something went wrong while answering. Please try again."})
            return
        yield _line({"stage": "done", "answer": answer, "sources": sources, "links": links})

    return StreamingResponse(steps(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})
