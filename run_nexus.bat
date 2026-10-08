@echo off
setlocal
cd /d "%~dp0"
title NEXUS Setup and Launcher

if not exist ".venv\Scripts\python.exe" (
    echo [NEXUS] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
echo [NEXUS] Installing or updating dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [NEXUS] Launching...
python main.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Something went wrong. Make sure Python 3.11+ is installed and added to PATH.
pause
exit /b 1
