"""Download and prepare everything the offline app needs.

    python -m offline_app.setup

* Face models (YuNet and SFace) and search models
* Speech-to-text model (faster-whisper) and voice (Piper) into ./models
* The local AI model (if Ollama is installed)
* Initializes the local SQLite database as the source of truth
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

from app import config as app_config
from app import db, library, seed

from . import config, voice


def ollama() -> str | None:
    found = shutil.which("ollama")
    default = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    return found or (str(default) if default.exists() else None)


def main() -> int:
    print("Setting up face detection, recognition and embeddings...", flush=True)
    subprocess.run([sys.executable, str(app_config.BASE_DIR / "scripts" / "setup_models.py")], check=True)

    print("Speech and voice models...", flush=True)
    try:
        voice.download_models()
        print("  ok", flush=True)
    except Exception as e:
        print(f"  Voice models note: {e}")

    print("Initializing offline database as source of truth...", flush=True)
    db.init()
    library.seed_subjects()
    seed.run()
    print("  ok", flush=True)

    exe = ollama()
    if exe:
        print(f"Local AI model {config.OLLAMA_MODEL}...", flush=True)
        for _ in range(15):
            try:
                requests.get(config.OLLAMA_URL, timeout=2)
                break
            except requests.ConnectionError:
                time.sleep(1)
        try:
            subprocess.run([exe, "pull", config.OLLAMA_MODEL], check=True)
            print("  ok", flush=True)
        except Exception as e:
            print(f"  Ollama pull note: {e}")
    else:
        print("  Ollama not detected. The assistant will answer exact facts directly.")

    print("All set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
