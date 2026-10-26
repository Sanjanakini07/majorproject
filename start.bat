@echo off
rem Double-click to start the NMAMIT Campus Voice Assistant.
rem The first run installs everything (about 5-10 minutes). Later runs start in seconds.
rem Keep this window open while using the app. Close it to stop the app.

setlocal
cd /d "%~dp0"
title NMAMIT Campus Voice Assistant
set PYTHONIOENCODING=utf-8
set URL=http://localhost:8000

rem Already running? Just open it.
curl -s -o nul %URL%/ 2>nul && (
  echo The app is already running. Opening %URL%
  start "" %URL%
  exit /b 0
)

rem 1. Python 3.10 or newer
where python >nul 2>nul || goto :no_python
python -c "import sys; sys.exit(sys.version_info < (3, 10))" || goto :no_python

rem 2. Python environment and packages, installed again only when requirements.txt changes
if not exist .venv\Scripts\python.exe (
  echo Creating the Python environment...
  python -m venv .venv || goto :failed
)
fc /b requirements.txt .venv\installed-requirements.txt >nul 2>nul || (
  echo Installing packages. The first time takes a few minutes...
  .venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements.txt || goto :failed
  copy /y requirements.txt .venv\installed-requirements.txt >nul
)

rem 3. Settings in .env
.venv\Scripts\python scripts\check_setup.py || (
  echo Opening .env in Notepad. Fill it in, save it, then double-click start.bat again.
  start "" notepad .env
  pause
  exit /b 1
)

rem 4. Face models and search model, done once
if not exist data\setup-done (
  echo Downloading models. This happens only once...
  .venv\Scripts\python scripts\setup_models.py || goto :failed
  echo done> data\setup-done
)

rem 5. Start the app and open the browser when it is ready
echo.
echo Starting the app at %URL%
echo Keep this window open while you use it. Close this window to stop the app.
echo.
start "" /b powershell -NoProfile -Command "for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing '%URL%/' -TimeoutSec 2 | Out-Null; $chrome = '%ProgramFiles%\Google\Chrome\Application\chrome.exe'; if (Test-Path $chrome) { Start-Process $chrome '%URL%' } else { Start-Process '%URL%' } ; break } catch { Start-Sleep 1 } }"
.venv\Scripts\python -m uvicorn app.main:app --port 8000
exit /b %errorlevel%

:no_python
echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during installation. Then double-click start.bat again.
pause
exit /b 1

:failed
echo.
echo Something went wrong above. Check your internet connection and try again.
echo If it keeps failing, send a screenshot of this window to the project team.
pause
exit /b 1
