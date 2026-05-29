@echo off
setlocal
cd /d "%~dp0"
title Ghost Creator AI v4.3.0 — Launch

echo.
echo  ============================================================
echo    GHOST CREATOR AI v4.3.0 — Launch
echo  ============================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo  [ERROR] Python venv missing. Run setup.bat first.
    pause
    exit /b 1
)

where node >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Node.js not found. Install Node.js 18+ and re-run.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo  [ERROR] node_modules missing. Run setup.bat or: npm install
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo  Starting Electron + React GUI ^(Python API auto-starts on port 8766^)...
echo.

npm run electron:dev
if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERROR] Launch failed. Check errors above.
    pause
    exit /b 1
)

exit /b 0
