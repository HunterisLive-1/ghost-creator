@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Ghost Creator AI v4.2.2 — Setup
cd /d "%~dp0"

echo.
echo  ============================================================
echo    GHOST CREATOR AI — One-Click Setup
echo  ============================================================
echo.

:: ================================================================
:: STEP 0 — Enable Windows Long Paths (needs Admin once)
:: ================================================================
echo  [1/7] Checking Windows Long Path support...

reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled 2>nul | findstr /C:"0x1" >nul
if %ERRORLEVEL% neq 0 (
    echo        Long Paths not enabled — requesting Admin permission...
    echo.
    powershell -Command "Start-Process cmd -ArgumentList '/c reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f' -Verb RunAs" 2>nul
    if %ERRORLEVEL% equ 0 (
        echo        [OK] Long Paths enabled!
    ) else (
        echo        [!] Could not enable Long Paths — you may need to do this manually.
        echo            Right-click setup.bat and "Run as Administrator" if needed.
    )
) else (
    echo        [OK] Already enabled.
)
echo.

:: ================================================================
:: STEP 1 — Detect Python
:: ================================================================
echo  [2/7] Detecting Python...

where py >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERROR] Python is NOT installed on this PC!
    echo.
    echo  Please download and install Python from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: During installation, check these boxes:
    echo    [x] Add Python to PATH
    echo    [x] Install py launcher for all users
    echo.
    pause
    exit /b 1
)

:: Show available Python versions
echo        Found Python installations:
py --list 2>nul
echo.

:: Try Python 3.12 first, then 3.11, then 3.10, then default
set PYVER=
for %%V in (3.12 3.11 3.10) do (
    if not defined PYVER (
        py -%%V --version >nul 2>&1
        if not errorlevel 1 (
            set PYVER=%%V
        )
    )
)

if not defined PYVER (
    echo        Using default Python version.
    set PYCMD=py
) else (
    echo        Using Python %PYVER%
    set PYCMD=py -%PYVER%
)
echo.

:: ================================================================
:: STEP 2 — Create Virtual Environment
:: ================================================================
echo  [3/7] Creating Ghost Creator virtual environment...

if exist "venv\Scripts\python.exe" (
    echo        [OK] venv already exists — skipping.
) else (
    %PYCMD% -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo  [ERROR] Failed to create venv!
        pause
        exit /b 1
    )
    echo        [OK] venv created!
)
echo.

:: ================================================================
:: STEP 3 — Install Ghost Creator Dependencies
:: ================================================================
echo  [4/7] Installing Ghost Creator dependencies (this may take a few minutes)...
echo.

call venv\Scripts\activate.bat

python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERROR] Some packages failed to install!
    echo  Try running this script again, or run manually:
    echo    venv\Scripts\activate.bat
    echo    pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo.
echo        [OK] All Ghost Creator dependencies installed!
echo.

:: ================================================================
:: STEP 4 — Set up Chatterbox TTS Server
:: ================================================================
echo  [5/7] Setting up Chatterbox TTS server...
echo.

set CHATTERBOX_DIR=%~dp0Chatterbox-TTS-Server-windows-easyInstallation

if not exist "%CHATTERBOX_DIR%\server.py" (
    echo        [!] Chatterbox server folder not found — skipping TTS setup.
    echo            Place the Chatterbox-TTS-Server folder in the project root.
    goto CHATTERBOX_SKIP
)

if exist "%CHATTERBOX_DIR%\venv\Scripts\python.exe" (
    echo        [OK] Chatterbox venv already exists — skipping install.
    goto CHATTERBOX_SKIP
)

:: Check for Python 3.10 (required by Chatterbox)
py -3.10 --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo        [!] Python 3.10 not found — required for Chatterbox TTS.
    echo            Download from: https://www.python.org/downloads/release/python-31011/
    echo            Then re-run setup.bat.
    goto CHATTERBOX_SKIP
)

echo  ============================================================
echo    CHATTERBOX TTS — GPU Selection
echo  ============================================================
echo.
echo    What GPU do you have?
echo.
echo    [1]  NVIDIA GPU (RTX/GTX)    ← Recommended for RTX 3050/3060/4070 etc.
echo    [2]  CPU Only                 ← Works on any PC (slower)
echo    [3]  AMD GPU (ROCm)           ← AMD RX 6000/7000 (Linux only)
echo    [4]  Skip Chatterbox setup
echo.
echo  ============================================================

set CB_CHOICE=
set /p CB_CHOICE=  Choose [1-4]: 

if "%CB_CHOICE%"=="4" goto CHATTERBOX_SKIP
if "%CB_CHOICE%"=="1" set CB_REQS=requirements-nvidia.txt
if "%CB_CHOICE%"=="2" set CB_REQS=requirements.txt
if "%CB_CHOICE%"=="3" set CB_REQS=requirements-rocm.txt

if not defined CB_REQS (
    echo        [!] Invalid choice — skipping Chatterbox setup.
    goto CHATTERBOX_SKIP
)

if not exist "%CHATTERBOX_DIR%\%CB_REQS%" (
    echo        [!] %CB_REQS% not found — falling back to CPU install.
    set CB_REQS=requirements.txt
)

echo.
echo        [*] Creating Chatterbox Python 3.10 venv...
py -3.10 -m venv "%CHATTERBOX_DIR%\venv"
if %ERRORLEVEL% neq 0 (
    echo        [ERROR] Failed to create Chatterbox venv!
    goto CHATTERBOX_SKIP
)
echo        [OK] Chatterbox venv created!
echo.
echo        [*] Upgrading pip...
"%CHATTERBOX_DIR%\venv\Scripts\pip.exe" install --upgrade pip >nul 2>&1

echo        [*] Installing Chatterbox %CB_REQS% (this downloads PyTorch — may take 5-15 min)...
echo            Please wait...
"%CHATTERBOX_DIR%\venv\Scripts\pip.exe" install -r "%CHATTERBOX_DIR%\%CB_REQS%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo        [!] Chatterbox install had errors — some packages may be missing.
    echo            You can retry manually:
    echo            cd %CHATTERBOX_DIR%
    echo            venv\Scripts\pip.exe install -r %CB_REQS%
) else (
    echo.
    echo        [OK] Chatterbox TTS installed successfully!
    echo        Model will be downloaded on first launch (~1.5 GB, one time).
)

:CHATTERBOX_SKIP
echo.

:: ================================================================
:: STEP 5 — Install Playwright Browsers
:: ================================================================
echo  [6/10] Installing Playwright browser (for YouTube upload)...

:: Re-activate Ghost Creator venv (may have been overridden)
call venv\Scripts\activate.bat

python -m playwright install chromium >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo        [!] Playwright browser install failed — YouTube upload may not work.
    echo            You can install manually later: python -m playwright install chromium
) else (
    echo        [OK] Playwright Chromium installed!
)
echo.

:: ================================================================
:: STEP 5b — Install GUI Dependencies (v2)
:: ================================================================
echo  [7/10] Installing API + GUI dependencies (FastAPI, edge-tts, Node/Electron)...

call venv\Scripts\activate.bat
pip install fastapi "uvicorn[standard]" pydantic Pillow edge-tts >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo        [!] Some Python packages failed to install.
) else (
    echo        [OK] Python API dependencies installed!
)

where npm >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo        [!] Node.js/npm not found — install from https://nodejs.org then run: npm install
) else (
    call npm install
    if %ERRORLEVEL% neq 0 (
        echo        [!] npm install failed.
    ) else (
        echo        [OK] Electron/React dependencies installed!
    )
)
echo.

echo  Install paid TTS backends? (ElevenLabs, Google Cloud TTS)
set /p PAID_TTS=  [y/N]: 
if /I "%PAID_TTS%"=="y" (
    pip install elevenlabs google-cloud-texttospeech
    echo        [OK] Paid TTS backends installed!
)
echo.

echo  Install Kokoro TTS? (local free, ~500MB model download)
set /p KOKORO=  [y/N]: 
if /I "%KOKORO%"=="y" (
    pip install kokoro soundfile
    echo        [OK] Kokoro TTS installed!
)
echo.

:: ================================================================
:: STEP 5c — Install Image Backend Dependencies (v2)
:: ================================================================
echo  [8/10] Installing image backend dependencies...
call venv\Scripts\activate.bat
pip install fal-client replicate >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo        [!] Some image backend packages failed to install.
) else (
    echo        [OK] Image backend dependencies installed!
)
echo.

:: ================================================================
:: STEP 6 — Create .env File (Legacy)
:: ================================================================
echo  [9/10] Setting up configuration...

if exist ".env" (
    echo        [OK] .env already exists.
) else (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo        [OK] .env created from .env.example
    ) else (
        (
            echo # ============================================================
            echo # Ghost Creator AI - Environment Variables
            echo # Fill in your real API keys below.
            echo # ============================================================
            echo.
            echo # --- Google Gemini API ---
            echo # Get free key: https://aistudio.google.com/app/apikey
            echo GEMINI_API_KEY=
            echo.
            echo # --- Chatterbox TTS ^(Free Local Voice^) ---
            echo CHATTERBOX_ENABLED=true
            echo CHATTERBOX_API_URL=http://127.0.0.1:8004
            echo CHATTERBOX_REFERENCE_AUDIO=my_voice_reference.wav
            echo CHATTERBOX_LANGUAGE=hi
            echo.
            echo # --- Language ^(hindi / english / hinglish^) ---
            echo VOICEOVER_LANG=hindi
            echo.
            echo # --- YouTube / Playwright ---
            echo YT_PROFILE_DIR=
            echo YT_PROFILE_NAME=Default
        ) > ".env"
        echo        [OK] .env created!
    )
)
echo.

:: ================================================================
:: STEP 7b — Migrate .env → config.json (v2)
:: ================================================================
echo  [10/10] Setting up config.json (v2 config)...

if exist "config.json" (
    echo        [OK] config.json already exists.
) else (
    if exist ".env" (
        echo        Migrating .env settings to config.json...
        python -c "
import json, os
from pathlib import Path
env = {}
for line in Path('.env').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()
from core.config_manager import config
if env.get('GEMINI_API_KEY'): config.set('api_keys.gemini', env['GEMINI_API_KEY'])
if env.get('CHATTERBOX_API_URL'): config.set('tts.chatterbox_url', env['CHATTERBOX_API_URL'])
if env.get('CHATTERBOX_REFERENCE_AUDIO'): config.set('tts.chatterbox_reference_audio', env['CHATTERBOX_REFERENCE_AUDIO'])
config.save()
print('        [OK] Migrated .env → config.json')
print('        Your .env is kept as backup (.env.backup)')
" 2>nul
        if exist ".env" (
            copy ".env" ".env.backup" >nul 2>&1
        )
    ) else (
        echo        Creating default config.json...
        python -c "from core.config_manager import config; config.save(); print('        [OK] config.json created with defaults')" 2>nul
    )
)
echo.

:: ================================================================
:: DONE!
:: ================================================================
echo.
echo  ============================================================
echo    SETUP COMPLETE!
echo  ============================================================
echo.
echo    Next steps:
echo.
echo    1. Add your GEMINI_API_KEY:
echo       - Get free key: https://aistudio.google.com/app/apikey
echo       - Open the GUI and enter it in Settings tab
echo       - OR edit config.json directly
echo.
echo    2. Record your voice (10-30 sec) as:
echo       my_voice_reference.wav  ^(in this folder^)
echo.
echo    3. Launch Ghost Creator AI:
echo       - Install Node deps:  npm install
echo       - GUI mode ^(dev^):   npm run electron:dev
echo       - API only ^(dev^):   python -m api.server
echo       - CLI mode:          python main.py
echo.
echo    4. ^(Optional^) OmniVoice TTS: start local server if using that backend.
echo.
echo    5. ^(One-time^) Set up YouTube auto-upload:
echo       venv\Scripts\python.exe setup_chrome_profile.py
echo.
echo  ============================================================
echo.
pause
