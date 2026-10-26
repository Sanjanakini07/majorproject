"""Settings for the offline app. Shared settings (admins, face threshold, data folder) stay in app.config."""
import os

from app.config import MODELS_DIR  # importing app.config also loads .env

# --- Ports: the laptop uses http://localhost, phones use https on the Wi-Fi address ---
HTTP_PORT = int(os.getenv("OFFLINE_HTTP_PORT", "8100"))
HTTPS_PORT = int(os.getenv("OFFLINE_HTTPS_PORT", "8443"))

# --- Sync with the Turso backend (leave empty to stay offline only) ---
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()
SYNC_SECONDS = int(os.getenv("SYNC_SECONDS", "60"))

# --- Local AI models ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")
WHISPER_DIR = MODELS_DIR / f"whisper-{WHISPER_MODEL}"
PIPER_VOICE = os.getenv("PIPER_VOICE", "en_US-lessac-medium")
PIPER_PATH = MODELS_DIR / "piper" / f"{PIPER_VOICE}.onnx"
