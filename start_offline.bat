@echo off
rem Double-click to start the offline NMAMIT Assistant: face sign-in, voice and AI all on this laptop.
rem The first run needs internet and installs everything (about 10-20 minutes). After that no internet is needed.
rem Keep this window open while using the app. Close it to stop the app.

setlocal
cd /d "%~dp0"
title NMAMIT Assistant (offline)
set PYTHONIOENCODING=utf-8
set URL=http://localhost:8100
set OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe

rem Already running? Just open it.
curl -s -o nul %URL%/ 2>nul && (
  echo The app is already running. Opening %URL%
  start "" %URL%
  exit /b 0
)

rem 1. Python 3.10 or newer
where python >nul 2>nul || goto :no_python
python -c "import sys; sys.exit(sys.version_info < (3, 10))" || goto :no_python

rem 2. Python environment and packages, installed again only when the requirements change
if not exist .venv\Scripts\python.exe (
  echo Creating the Python environment...
  python -m venv .venv || goto :failed
)
copy /b requirements.txt + requirements-offline.txt .venv\wanted-offline.txt >nul
fc /b .venv\wanted-offline.txt .venv\installed-offline.txt >nul 2>nul || (
  echo Installing packages. The first time takes a few minutes...
  .venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements-offline.txt || goto :failed
  copy /y .venv\wanted-offline.txt .venv\installed-offline.txt >nul
)

rem 3. Settings in .env
.venv\Scripts\python scripts\check_setup.py --offline || (
  echo Opening .env in Notepad. Fill it in, save it, then double-click start_offline.bat again.
  start "" notepad .env
  pause
  exit /b 1
)

rem 4. Ollama runs the local AI model
if not exist "%OLLAMA%" (
  echo Installing Ollama, which runs the AI model on this laptop...
  winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
)
if not exist "%OLLAMA%" goto :no_ollama
curl -s -o nul http://127.0.0.1:11434/ 2>nul || start "" /min "%OLLAMA%" serve

rem 5. Models, student photos and the first sync, done once
if not exist data\offline-setup-done (
  echo Downloading models and student photos. This happens only once...
  .venv\Scripts\python -m offline_app.setup || goto :failed
  echo done> data\offline-setup-done
)

rem 6. Start the app and open the browser when it is ready
echo.
echo Starting the app at %URL%
echo Phones: open %URL%/connect on this laptop and scan the QR code.
echo Keep this window open while you use it. Close this window to stop the app.
echo.
start "" /b powershell -NoProfile -Command "for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing '%URL%/' -TimeoutSec 2 | Out-Null; Start-Process '%URL%'; break } catch { Start-Sleep 1 } }"
.venv\Scripts\python -m offline_app
exit /b %errorlevel%

:no_python
echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during installation. Then double-click start_offline.bat again.
pause
exit /b 1

:no_ollama
echo Ollama could not be installed automatically. Install it from https://ollama.com/download
echo then double-click start_offline.bat again.
pause
exit /b 1

:failed
echo.
echo Something went wrong above. The first start needs internet; check it and try again.
echo If it keeps failing, send a screenshot of this window to the project team.
pause
exit /b 1
