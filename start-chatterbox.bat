@echo off
title Chatterbox TTS Server
cd /d "%~dp0"

echo.
echo  ============================================================
echo    Chatterbox TTS Server
echo  ============================================================
echo.

if not exist "Chatterbox-TTS-Server-windows-easyInstallation\venv\Scripts\python.exe" (
    echo  [ERROR] Chatterbox venv not found! Run setup.bat first.
    echo.
    pause
    exit /b 1
)

:: ── Check if already running ─────────────────────────────────
echo  [*] Checking server...
"Chatterbox-TTS-Server-windows-easyInstallation\venv\Scripts\python.exe" "_check_server.py" check
if %ERRORLEVEL% equ 0 (
    echo.
    echo  Web UI : http://localhost:8004
    echo  API    : http://localhost:8004/docs
    echo.
    pause
    exit /b 0
)

:: ── Start server directly ────────────────────────────────────
echo.
echo  [*] Starting Chatterbox TTS Server...
echo.
echo  ============================================================
echo  URL  : http://localhost:8004
echo  API  : http://localhost:8004/docs
echo  Press CTRL+C to stop.
echo  ============================================================
echo.

cd /d "%~dp0Chatterbox-TTS-Server-windows-easyInstallation"
call "venv\Scripts\activate.bat"
python server.py

echo.
echo  Server stopped.
echo.
pause
