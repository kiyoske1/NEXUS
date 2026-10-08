@echo off
setlocal
cd /d "%~dp0"
title Build NEXUS for Windows

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :error
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error
python -m PyInstaller --noconfirm --clean --windowed --name NEXUS main.py
if errorlevel 1 goto :error

echo.
echo Build complete. Look in the dist\NEXUS folder.
pause
exit /b 0

:error
echo.
echo Build failed. Check the error above.
pause
exit /b 1
