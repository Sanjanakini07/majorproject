@echo off
rem Double-click to make the Windows installer: dist\NMAMIT_Assistant_Setup.exe
rem Copy that one file to any Windows PC and run it to install the desktop app.
rem Needs internet the first time (packages and models). Takes about 15-30 minutes.

setlocal
cd /d "%~dp0"
title Building the NMAMIT Assistant installer
set PYTHONIOENCODING=utf-8

rem 1. Python 3.10 or newer
where python >nul 2>nul || goto :no_python
python -c "import sys; sys.exit(sys.version_info < (3, 10))" || goto :no_python

rem 2. Python environment with the app's packages and PyInstaller
if not exist .venv\Scripts\python.exe (
  echo Creating the Python environment...
  python -m venv .venv || goto :failed
)
echo Installing packages (quick when they are already there)...
.venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements-offline.txt pyinstaller || goto :failed

rem 3. Settings: the Groq key in .env is copied into the installer so installed copies answer with Groq when online
if not exist .env (
  echo No .env file: the installed app will answer with the local model only.
) else (
  findstr /b /c:"GROQ_API_KEY=" .env | findstr /v /x /c:"GROQ_API_KEY=" >nul || echo Note: GROQ_API_KEY is empty in .env, so the installed app will use only the local model.
)

rem 4. Close a running copy of the app, so its files can be replaced
taskkill /im NMAMIT_Assistant.exe /f >nul 2>nul

rem 5. Default data, models, the app and the installer
.venv\Scripts\python build_setup.py || goto :failed

echo.
echo Done. The installer is dist\NMAMIT_Assistant_Setup.exe
echo On the other PC, install Ollama from https://ollama.com/download too, so answers work with no internet.
explorer /select,"%~dp0dist\NMAMIT_Assistant_Setup.exe"
pause
exit /b 0

:no_python
echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during installation. Then double-click create_installer.bat again.
pause
exit /b 1

:failed
echo.
echo Building the installer failed. Read the messages above for the reason.
pause
exit /b 1
