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
        return Path(sys.executable).resolve().parent
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


def run_server(port: int) -> None:
    import uvicorn
    from offline_app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main():
    base_dir = get_base_dir()
    data_dir, models_dir = setup_user_data(base_dir)

    os.environ["BASE_DIR"] = str(base_dir)
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["MODELS_DIR"] = str(models_dir)
    port = int(os.getenv("OFFLINE_HTTP_PORT", "8100"))

    # Start server in daemon thread
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"

    # Wait for server to become responsive
    ready = False
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/", timeout=1):
                ready = True
                break
        except Exception:
            time.sleep(0.2)

    if not ready:
        print("Server took too long to start. Exiting.")
        sys.exit(1)

    browser = find_browser_app_executable()
    if browser:
        # Launch dedicated application window
        proc = subprocess.Popen([browser, f"--app={url}", "--window-size=1240,840"])
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
    main()
