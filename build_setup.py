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
        f"--add-data={str(BASE_DIR / 'data')}{os.pathsep}data",
        f"--add-data={str(BASE_DIR / 'models')}{os.pathsep}models",
        f"--add-data={str(BASE_DIR / '.env.example')}{os.pathsep}.",
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
    app_dir = build_app()
    payload_zip = create_payload(app_dir)
    build_installer(payload_zip)


if __name__ == "__main__":
    main()
