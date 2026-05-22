@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo    GHOST CREATOR AI v4.2.2 - Full Electron Build
echo  ============================================================
echo.

call build-api.bat
if %ERRORLEVEL% neq 0 exit /b 1

call npm run build
if %ERRORLEVEL% neq 0 exit /b 1

call npm run electron:build
if %ERRORLEVEL% neq 0 exit /b 1

echo.
echo  [OK] Check release\ folder for installer output.
echo.
pause
