"""Download everything the offline app needs, once, while there is internet.

    python -m offline_app.setup

* Face models, search model, student photos and faces (scripts/setup_models.py)
* Speech-to-text model (faster-whisper) and voice (Piper) into ./models
* The local AI model, through Ollama
* A first sync with the Turso backend, if it is set up
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

from app import config as app_config
from app import db

from . import config, sync, voice


def ollama() -> str | None:
    found = shutil.which("ollama")
    default = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    return found or (str(default) if default.exists() else None)


def main() -> int:
    subprocess.run([sys.executable, str(app_config.BASE_DIR / "scripts" / "setup_models.py")], check=True)

    print("Speech and voice models...", flush=True)
    voice.download_models()
    print("  ok")

    print(f"Local AI model {config.OLLAMA_MODEL} (about 1 GB, first time only)...", flush=True)
    exe = ollama()
    if not exe:
        print("  Ollama is not installed. Install it from https://ollama.com/download and run setup again.")
        return 1
    for _ in range(30):  # start_offline.bat may have only just started Ollama
        try:
            requests.get(config.OLLAMA_URL, timeout=2)
            break
        except requests.ConnectionError:
            time.sleep(1)
    subprocess.run([exe, "pull", config.OLLAMA_MODEL], check=True)

    if sync.enabled():
        print("First sync with the backend...", flush=True)
        db.init()
        sync.init()
        sync.sync_once()
        print(f"  {sync.status['state']} {sync.status['message']}")

    print("All set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
