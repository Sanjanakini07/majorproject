"""Desktop Client Launcher for NMAMIT Campus Voice Assistant (Offline).

Starts the local offline assistant server and opens the native application window.
No external backend or mobile connections are required.
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # PyInstaller 6 keeps bundled files in _internal, not next to the exe
    return Path(__file__).resolve().parent


def setup_user_data(base_dir: Path) -> tuple[Path, Path]:
    """Ensure writable data and models directories in %LOCALAPPDATA%."""
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        app_data_root = Path(local_app_data) / "NMAMIT_Assistant"
    else:
        app_data_root = base_dir

    data_dir = app_data_root / "data"
    models_dir = app_data_root / "models"
    data_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    # Seed data/app.db from bundled assets if not present
    bundled_data = base_dir / "data"
    target_db = data_dir / "app.db"
    if not target_db.exists() and (bundled_data / "app.db").exists():
        shutil.copy2(bundled_data / "app.db", target_db)

    # Seed chroma directory if not present
    target_chroma = data_dir / "chroma"
    if not target_chroma.exists() and (bundled_data / "chroma").exists():
        try:
            shutil.copytree(bundled_data / "chroma", target_chroma)
        except Exception:
            pass

    # Copy bundled models if needed
    bundled_models = base_dir / "models"
    if bundled_models.exists():
        for item in bundled_models.glob("*"):
            dest = models_dir / item.name
            if not dest.exists():
                try:
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
                except Exception:
                    pass

    return data_dir, models_dir


def find_browser_app_executable() -> str | None:
    """Find Microsoft Edge or Google Chrome to launch in application mode (--app)."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


STARTUP_SECONDS = 180


def show_error(message: str) -> None:
    """A Windows message box: the windowed exe has no console, so a printed error would go unseen."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "NMAMIT Campus Voice Assistant", 0x10)
    except Exception:
        pass


def run_server(port: int) -> None:
    import uvicorn

    try:
        from offline_app.main import app

        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except BaseException:  # an import or start-up failure would otherwise vanish with this thread
        import traceback

        traceback.print_exc()
        raise


def ensure_ollama() -> None:
    """Start the local AI (Ollama) if it is installed but not running, and download its model once when online."""
    from offline_app import config
    from offline_app.setup import ollama

    exe = ollama()
    if not exe:
        return  # not installed: answers come from Groq when online, or the exact facts
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        urllib.request.urlopen(config.OLLAMA_URL, timeout=2)
    except Exception:
        subprocess.Popen([exe, "serve"], creationflags=flags)
        time.sleep(3)
    try:
        with urllib.request.urlopen(f"{config.OLLAMA_URL}/api/tags", timeout=5) as r:
            have = r.read().decode()
        if f'"{config.OLLAMA_MODEL}"' not in have:
            subprocess.run([exe, "pull", config.OLLAMA_MODEL], creationflags=flags, timeout=3600)
    except Exception:
        pass  # offline or Ollama still starting: tried again next launch


def main():
    base_dir = get_base_dir()
    data_dir, models_dir = setup_user_data(base_dir)
    if sys.stdout is None:  # windowed exe has no console; uvicorn's logger needs a real stream
        log = open(data_dir / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log

    os.environ["BASE_DIR"] = str(base_dir)
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["MODELS_DIR"] = str(models_dir)
    port = int(os.getenv("OFFLINE_HTTP_PORT", "8100"))
    threading.Thread(target=ensure_ollama, daemon=True).start()

    # Start server in daemon thread
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"

    # Wait for the server. The first start after installing is slow (Windows Defender scans every new file).
    deadline = time.monotonic() + STARTUP_SECONDS
    ready = False
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/", timeout=2):
                ready = True
                break
        except Exception:
            if not server_thread.is_alive():
                break  # the server failed; its error is in the log
            time.sleep(0.5)

    if not ready:
        print("The assistant's server did not start.", flush=True)
        show_error("The assistant could not start. Close it, wait a minute and open it again.\n\n"
                   f"If it keeps happening, send this file to the developers:\n{data_dir / 'app.log'}")
        sys.exit(1)

    browser = find_browser_app_executable()
    if browser:
        # Its own browser profile, so this is a separate browser process that lives exactly as long as the
        # window (without it, an already open Edge takes the window and this process returns at once).
        profile = data_dir.parent / "browser"
        proc = subprocess.Popen([browser, f"--app={url}", "--window-size=1240,840", f"--user-data-dir={profile}",
                                 "--no-first-run", "--no-default-browser-check"])
        proc.wait()
    else:
        # Fallback to default browser
        webbrowser.open(url)
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback

        traceback.print_exc()
        show_error("The assistant stopped because of an error. Details are in app.log in "
                   "%LOCALAPPDATA%\\NMAMIT_Assistant\\data.")
        raise
