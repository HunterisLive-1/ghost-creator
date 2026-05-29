@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo    GHOST CREATOR AI v4.3.0 - Build Python API (onedir)
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
if not exist "build-api" mkdir build-api

echo Cleaning previous build ...
if exist "dist-api\GhostCreatorAPI" rd /s /q "dist-api\GhostCreatorAPI"
if exist "build-api\GhostCreatorAPI" rd /s /q "build-api\GhostCreatorAPI"

echo.
echo Building GhostCreatorAPI (onedir) via spec file ...
echo.

python build_api.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERROR] PyInstaller build failed. Check output above for details.
    pause
    exit /b 1
)

echo.
echo  [OK] Build complete: dist-api\GhostCreatorAPI\GhostCreatorAPI.exe
echo.

if /i not "%~1"=="--no-pause" pause
exit /b 0
