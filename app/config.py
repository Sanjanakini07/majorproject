"""All settings come from environment variables (or the .env file)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


def _email_set(name: str) -> set[str]:
    return {e.strip().lower() for e in os.getenv(name, "").split(",") if e.strip()}


# --- Google sign-in (through Firebase Authentication) ----------------------
# Both values are on the Firebase console: Project settings > General > Your apps.
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "").strip()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FIREBASE_AUTH_DOMAIN = f"{FIREBASE_PROJECT_ID}.firebaseapp.com"
ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "nmamit.in").strip().lower()
# The address people open in the browser (used to recognise same-site requests).
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

# --- Who is an admin --------------------------------------------------------
ADMIN_EMAILS = _email_set("ADMIN_EMAILS")

# --- Sessions ---------------------------------------------------------------
# Without a fixed SECRET_KEY a random one is used, so everyone is signed out
# whenever the server restarts. Set it in .env for anything beyond local testing.
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
HTTPS_ONLY = _bool("HTTPS_ONLY", False)
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "8"))

# --- Groq (the AI model) ----------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# --- Face check -------------------------------------------------------------
# Cosine similarity between a live photo and an enrolled one. 0.363 is the
# value OpenCV recommends for the SFace model; raise it to be stricter.
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.363"))
FACE_MAX_FAILURES = int(os.getenv("FACE_MAX_FAILURES", "10"))
FACE_LOCK_MINUTES = int(os.getenv("FACE_LOCK_MINUTES", "10"))

# --- RAG --------------------------------------------------------------------
TOP_K = int(os.getenv("TOP_K", "4"))
# Cosine distance (0 = same meaning, 1+ = unrelated). Chunks further away than
# this are ignored. With the default embedding model, related text is usually
# below 0.6 and unrelated text above 0.7.
MAX_DISTANCE = float(os.getenv("MAX_DISTANCE", "0.7"))
ASKS_PER_MINUTE = int(os.getenv("ASKS_PER_MINUTE", "15"))

# --- Storage ----------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
MODELS_DIR = Path(os.getenv("MODELS_DIR", str(BASE_DIR / "models")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
