"""Build script to create the Windows Packaged Setup Executable.

Produces:
1. dist/NMAMIT_Assistant/ (The compiled standalone desktop app bundle)
2. dist/NMAMIT_Assistant_Setup.exe (The standalone Windows Setup Installer)
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
ICON_PATH = BASE_DIR / "app" / "static" / "icon.ico"


def run_command(cmd: list[str]) -> None:
    print(f"Running: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=str(BASE_DIR))


def clean() -> None:
    print("Cleaning previous builds...", flush=True)
    for p in (DIST_DIR, BUILD_DIR, BASE_DIR / "payload.zip"):
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


BUNDLE_DIR = BUILD_DIR / "bundle"
MODELS_DIR = BASE_DIR / "models"
# Settings copied from .env into the installed app. Turso, Firebase and the session key stay out of it.
BUNDLED_SETTINGS = ("GROQ_API_KEY", "GROQ_MODEL", "ADMIN_EMAILS", "ALLOWED_DOMAIN", "OLLAMA_MODEL", "WHISPER_MODEL",
                    "PIPER_VOICE", "FACE_MATCH_THRESHOLD", "FACE_MAX_FAILURES", "FACE_LOCK_MINUTES", "TOP_K",
                    "MAX_DISTANCE")


def prepare_bundle() -> None:
    """A fresh database with the default data, fully searchable, plus every model, made just for the installer.

    The developer's own data/ (enrolled faces, test edits) is never shipped."""
    print("\n--- Step 0: Preparing default data and models ---", flush=True)
    data = BUNDLE_DIR / "data"
    data.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "DATA_DIR": str(data), "MODELS_DIR": str(MODELS_DIR), "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, "-m", "offline_app.setup"], check=True, cwd=str(BASE_DIR), env=env)
    for leftover in ("lan-cert.pem", "lan-key.pem", "app.log"):
        (data / leftover).unlink(missing_ok=True)
    missing = [p for p in ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx",
                           "all-MiniLM-L6-v2", "piper") if not (MODELS_DIR / p).exists()]
    if missing or not (data / "app.db").exists():
        raise RuntimeError(f"Setup did not produce everything the app needs: {missing or 'data/app.db'}")

    wanted = {}
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in BUNDLED_SETTINGS and value.strip():
                wanted[key.strip()] = value.strip()
    if "GROQ_API_KEY" not in wanted:
        print("  Note: no GROQ_API_KEY in .env, so the installed app uses only the local model.", flush=True)
    (BUNDLE_DIR / ".env").write_text("".join(f"{k}={v}\n" for k, v in wanted.items()), encoding="utf-8")
    print(f"  Bundled settings: {', '.join(wanted) or 'none'}", flush=True)


def build_app() -> Path:
    print("\n--- Step 1: Building NMAMIT_Assistant.exe ---", flush=True)
    pyinstaller = sys.executable.replace("python.exe", "pyinstaller.exe")
    if not Path(pyinstaller).exists():
        pyinstaller = "pyinstaller"

    # PyInstaller arguments
    cmd = [
        pyinstaller,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name", "NMAMIT_Assistant",
        f"--icon={str(ICON_PATH)}",
        f"--add-data={str(BASE_DIR / 'app')}{os.pathsep}app",
        f"--add-data={str(BASE_DIR / 'offline_app')}{os.pathsep}offline_app",
        f"--add-data={str(BUNDLE_DIR / 'data')}{os.pathsep}data",
        f"--add-data={str(MODELS_DIR)}{os.pathsep}models",
        f"--add-data={str(BUNDLE_DIR / '.env')}{os.pathsep}.",
        # Packages that load models, data files or plugins by name at run time
        "--collect-all=chromadb",
        "--collect-all=onnxruntime",
        "--collect-all=tokenizers",
        "--collect-all=faster_whisper",
        "--collect-all=ctranslate2",
        "--collect-all=piper",
        "--collect-all=rapidocr",
        "--collect-data=certifi",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.lifespans",
        "--hidden-import=uvicorn.lifespans.on",
        "--hidden-import=uvicorn.lifespans.off",
        "--hidden-import=email_validator",
        str(BASE_DIR / "desktop_client.py"),
    ]
    run_command(cmd)

    app_dist = DIST_DIR / "NMAMIT_Assistant"
    if not app_dist.exists():
        raise RuntimeError("Failed to build NMAMIT_Assistant")
    print("  NMAMIT_Assistant build successful!", flush=True)
    return app_dist


def create_payload(app_dir: Path) -> Path:
    print("\n--- Step 2: Packaging Application into payload.zip ---", flush=True)
    payload_zip = BASE_DIR / "payload.zip"
    with zipfile.ZipFile(payload_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in app_dir.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(app_dir)
                zf.write(file, arcname)
    print(f"  payload.zip created ({payload_zip.stat().st_size / (1024*1024):.2f} MB)", flush=True)
    return payload_zip


def build_installer(payload_zip: Path) -> Path:
    print("\n--- Step 3: Building Standalone Setup Executable (NMAMIT_Assistant_Setup.exe) ---", flush=True)
    pyinstaller = sys.executable.replace("python.exe", "pyinstaller.exe")
    if not Path(pyinstaller).exists():
        pyinstaller = "pyinstaller"

    cmd = [
        pyinstaller,
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "NMAMIT_Assistant_Setup",
        f"--icon={str(ICON_PATH)}",
        f"--add-data={str(payload_zip)}{os.pathsep}.",
        str(BASE_DIR / "installer.py"),
    ]
    run_command(cmd)

    setup_exe = DIST_DIR / "NMAMIT_Assistant_Setup.exe"
    if not setup_exe.exists():
        raise RuntimeError("Failed to build NMAMIT_Assistant_Setup.exe")
    print(f"\n========================================================")
    print(f"SUCCESS! Packaged Setup built:")
    print(f"Location: {setup_exe}")
    print(f"Size: {setup_exe.stat().st_size / (1024*1024):.2f} MB")
    print(f"========================================================")
    return setup_exe


def main():
    clean()
    prepare_bundle()
    app_dir = build_app()
    payload_zip = create_payload(app_dir)
    build_installer(payload_zip)


if __name__ == "__main__":
    main()
