"""The offline web app: face sign-in, voice questions and answers, all on this laptop.

Start it with start_offline.bat, or:  python -m offline_app
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

from app import academics, admin, db, facelogin, portal, rag
from app import config as app_config
from app.auth import ask_limit, role_of, verified_user

from . import config, llm, net, sync, voice

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("offline_app")

HERE = app_config.BASE_DIR / "offline_app"
MAX_AUDIO_BYTES = 10 * 1024 * 1024
ROLL = re.compile(r"^[a-z0-9._-]{1,64}$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    sync.start()
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

CSP = (
    "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; script-src 'self'; "
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


@app.get("/connect", include_in_schema=False)
def connect_page():
    return page(HERE / "pages" / "connect.html")


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


# --- Face sign-in ------------------------------------------------------------------
# Like Face ID: the first time, six photos are taken while the student turns their head and
# their face signature is saved. Every later sign-in takes fresh photos and compares them.

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
async def login(request: Request, roll: str = Form(..., max_length=100), files: list[UploadFile] = File(...)):
    local, email = roll_email(roll)
    facelogin.check_not_locked(email)
    images = await facelogin.read_images(files)

    first_time = db.get_face(email) is None
    if first_time:
        await run_in_threadpool(facelogin.enroll, email, images, email)
        if role_of(email) == "student":
            academics.ensure_student(email, local.upper())
        sync.sync_soon()
    else:
        await run_in_threadpool(facelogin.verify, email, images)

    request.session.clear()  # always start a fresh session after sign-in
    request.session.update({"email": email, "name": local.upper(), "face_ok": True})
    return {"enrolled_now": first_time}


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

    def steps():
        yield _line({"stage": "searching"})
        try:
            hits = rag.search(question)
            sources = list(dict.fromkeys(h["title"] for h in hits))
            yield _line({"stage": "thinking", "sources": sources})
            answer = llm.answer(question, hits)
        except rag.AnswerError as e:
            log.error("Answering failed: %s", e)
            yield _line({"stage": "error", "message": f"Sorry, I can't answer right now. {e}"})
            return
        except Exception:
            log.exception("Answering failed")
            yield _line({"stage": "error", "message": "Sorry, something went wrong while answering. Please try again."})
            return
        yield _line({"stage": "done", "answer": answer, "sources": sources})

    return StreamingResponse(steps(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


# --- Phones and sync ---------------------------------------------------------------

def phone_urls() -> list[str]:
    return [f"https://{ip}:{config.HTTPS_PORT}" for ip in net.lan_ips()]


@app.get("/api/connect")
def connect_info():
    return {"phone_urls": phone_urls()}


@app.get("/api/qr.svg")
def qr(i: int = 0):
    urls = phone_urls()
    if not 0 <= i < len(urls):
        raise HTTPException(404, "This laptop is not on a Wi-Fi network.")
    return Response(net.qr_svg(urls[i]), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/sync")
def sync_status(user: dict = Depends(verified_user)):
    return sync.current_status()


@app.post("/api/sync", status_code=202)
def sync_now(user: dict = Depends(verified_user)):
    sync.sync_soon()
    return sync.current_status()
