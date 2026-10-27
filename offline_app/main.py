"""The offline NMAMIT Assistant: face sign-in, voice questions and answers, all on this Windows device.

Start it with:  python -m offline_app
The admin panel, marks, attendance, face check, knowledge store and search are reused from app/.
"""
import json
import logging
import re
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from app import academics, admin, bus, db, facelogin, library, personal, portal, rag, seed
from app import config as app_config
from app.auth import ask_limit, role_of, signed_in_user, verified_user

from . import config, llm, voice

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("offline_app")

HERE = app_config.BASE_DIR / "offline_app"
MAX_AUDIO_BYTES = 10 * 1024 * 1024
ROLL = re.compile(r"^[a-z0-9._-]{1,64}$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    library.seed_subjects()
    await run_in_threadpool(seed.run)
    if not app_config.ADMIN_EMAILS:
        log.warning("ADMIN_EMAILS is empty: nobody can open the admin panel.")
    yield


app = FastAPI(title="NMAMIT Assistant (offline)", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=app_config.SECRET_KEY,
    session_cookie="nva_session",
    max_age=app_config.SESSION_HOURS * 3600,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=app_config.BASE_DIR / "app" / "static"), name="static")
app.mount("/offline", StaticFiles(directory=HERE / "static"), name="offline")
app.include_router(admin.router)
app.include_router(portal.router)
app.include_router(library.router)
app.include_router(bus.router)

CSP = (
    "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; script-src 'self' 'unsafe-inline'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def security(request: Request, call_next):
    # Block form posts and fetches coming from other websites (CSRF).
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
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

def page(path) -> FileResponse:
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
def home(request: Request):
    if not request.session.get("face_ok"):
        return page(HERE / "pages" / "login.html")
    return page(HERE / "pages" / "chat.html")


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


# --- Face sign-in & registration --------------------------------------------------
# Offline Face Authentication:
#   First time registration -> 6 guided photos enrolled locally in SQLite 'faces' table.
#   Later sign-ins -> fresh photos compared against the enrolled signatures locally.

def roll_email(roll: str) -> tuple[str, str]:
    roll = roll.strip().lower()
    local = roll.removesuffix("@" + app_config.ALLOWED_DOMAIN)
    if not ROLL.match(local):
        raise HTTPException(400, "Enter your roll number, for example NNM23IS186.")
    return local, f"{local}@{app_config.ALLOWED_DOMAIN}"


@app.post("/api/login/status")
def login_status(roll: str = Form(..., max_length=100)):
    """Tells the page whether to enrol (first time) or just check the face."""
    _, email = roll_email(roll)
    facelogin.check_not_locked(email)
    return {"enrolled": db.get_face(email) is not None}


@app.post("/api/login")
async def login(
    request: Request,
    roll: str = Form(..., max_length=100),
    name: str = Form(default="", max_length=100),
    files: list[UploadFile] = File(...),
):
    local, email = roll_email(roll)
    facelogin.check_not_locked(email)
    images = await facelogin.read_images(files)

    display_name = name.strip() or local.upper()
    first_time = db.get_face(email) is None
    if first_time:
        await run_in_threadpool(facelogin.enroll, email, images, email)
        if role_of(email) == "student":
            academics.ensure_student(email, display_name)
        if name.strip():
            academics.adopt_name(email, name.strip())
            profile = db.get_profile(email)
            if profile and profile.get("name"):
                display_name = profile["name"]
    else:
        await run_in_threadpool(facelogin.verify, email, images)
        profile = db.get_profile(email)
        if profile and profile.get("name"):
            display_name = profile["name"]

    request.session.clear()  # always start a fresh session after sign-in
    request.session.update({"email": email, "name": display_name, "face_ok": True})
    return {"enrolled_now": first_time}


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


# --- Voice -------------------------------------------------------------------------

@app.post("/api/stt")
async def speech_to_text(file: UploadFile = File(...), user: dict = Depends(verified_user)):
    data = await admin.read_upload(file, MAX_AUDIO_BYTES)
    try:
        text = await run_in_threadpool(voice.transcribe, data)
    except voice.VoiceError as e:
        raise HTTPException(400, str(e))
    if not text:
        raise HTTPException(422, "I didn't hear anything. Tap the button and try again.")
    return {"text": text}


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/api/tts")
def text_to_speech(body: SpeakIn, user: dict = Depends(verified_user)):
    try:
        return Response(voice.speak(body.text), media_type="audio/wav", headers={"Cache-Control": "no-store"})
    except voice.VoiceError as e:
        raise HTTPException(503, str(e))  # the page falls back to the browser's own voice


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

    # Exact facts (their records, dates, the calendar) and which search results they make unnecessary.
    facts = personal.build(user["email"], user.get("name", ""), question)

    def steps():
        yield _line({"stage": "searching"})
        try:
            hits = personal.adjust_hits(rag.search(question), facts)
            sources = list(dict.fromkeys(h["title"] for h in hits))
            links = library.links_for([h.get("module_id") for h in hits])
            yield _line({"stage": "thinking", "sources": sources})
            answer = llm.answer(question, hits, facts.text)
        except rag.AnswerError as e:
            log.error("Answering failed: %s", e)
            yield _line({"stage": "error", "message": f"Sorry, I can't answer right now. {e}"})
            return
        except Exception:
            log.exception("Answering failed")
            yield _line({"stage": "error", "message": "Sorry, something went wrong while answering. Please try again."})
            return
        yield _line({"stage": "done", "answer": answer, "sources": sources, "links": links})

    return StreamingResponse(steps(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


# --- Offline status compatibility --------------------------------------------------

@app.get("/api/sync")
def sync_status():
    return {"state": "off", "message": "Offline only (local database is source of truth)", "pending": 0}


@app.post("/api/sync", status_code=200)
def sync_now():
    return {"state": "off", "message": "Offline only (local database is source of truth)", "pending": 0}
