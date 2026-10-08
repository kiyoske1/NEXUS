@echo off
setlocal
cd /d "%~dp0"
title Build NEXUS for Windows

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :error
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error

python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

python -m PyInstaller --noconfirm --clean --onefile --windowed --name NEXUS --collect-all PySide6 main.py
if errorlevel 1 goto :error
if not exist "dist\NEXUS.exe" goto :error

echo.
echo Build complete: dist\NEXUS.exe
exit /b 0

:error
echo.
echo Build failed. Check the error above.
exit /b 1
