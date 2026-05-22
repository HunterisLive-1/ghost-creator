@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo    GHOST CREATOR AI v4.2.2 - Build Python API (.exe)
echo  ============================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo  [ERROR] Python venv missing. Run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

python -m pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    python -m pip install "pyinstaller>=6.0"
)

if not exist "docs\index.json" (
    echo  [ERROR] docs\ folder missing. Ensure project documentation exists.
    pause
    exit /b 1
)

if not exist "dist-api" mkdir dist-api

echo Building GhostCreatorAPI.exe ...
echo.

set ICON_ARG=
if exist "icon.ico" set ICON_ARG=--icon "%CD%\icon.ico"

python -m PyInstaller ^
  --clean ^
  --onefile ^
  --noconsole ^
  --name GhostCreatorAPI ^
  %ICON_ARG% ^
  --add-data "%CD%\docs;docs" ^
  --add-data "%CD%\api\templates;api\templates" ^
  --distpath dist-api ^
  --workpath build-api ^
  --specpath build-api ^
  --hidden-import api.server ^
  --hidden-import uvicorn ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import fastapi ^
  --hidden-import pydantic ^
  --hidden-import markdown ^
  --hidden-import backends.tts.omnivoice_tts ^
  --hidden-import backends.tts.edge_tts ^
  --hidden-import backends.tts.elevenlabs ^
  --hidden-import backends.image.gemini_imagen ^
  --exclude-module torch ^
  --exclude-module torchaudio ^
  --exclude-module torchvision ^
  --exclude-module omnivoice ^
  --exclude-module tensorboard ^
  --exclude-module numba ^
  --exclude-module scipy ^
  --exclude-module pandas ^
  --collect-submodules modules ^
  --collect-submodules core ^
  --collect-submodules api ^
  api\server.py

if %ERRORLEVEL% neq 0 (
    echo  [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo  [OK] dist-api\GhostCreatorAPI.exe
echo.
if /i not "%~1"=="--no-pause" pause
exit /b 0
