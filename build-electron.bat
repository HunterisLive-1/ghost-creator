@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ============================================================
echo    GHOST CREATOR AI v4.3.0 - Full Electron Build
echo  ============================================================
echo.

echo  Stopping processes that may lock build files...
taskkill /F /IM GhostCreatorAPI.exe >nul 2>&1
taskkill /F /IM GhostCreatorAI.exe >nul 2>&1
taskkill /F /IM GhostCreatorAPI_test.exe >nul 2>&1
ping -n 3 127.0.0.1 >nul

echo  Cleaning previous build artifacts...
if exist "build-api\GhostCreatorAPI.spec" del /q "build-api\GhostCreatorAPI.spec" >nul 2>&1
if exist "build-api\GhostCreatorAPI_test.spec" del /q "build-api\GhostCreatorAPI_test.spec" >nul 2>&1
if exist "GhostCreatorAPI_test.spec" del /q "GhostCreatorAPI_test.spec" >nul 2>&1

if exist "build-api" rmdir /s /q "build-api" 2>nul
if exist "dist-api" rmdir /s /q "dist-api" 2>nul
if exist "dist" rmdir /s /q "dist" 2>nul
if exist "dist-electron" rmdir /s /q "dist-electron" 2>nul
if exist "release" rmdir /s /q "release" 2>nul

if exist "build-api" (
    echo  [ERROR] Could not remove build-api\ — close Ghost Creator, Python API, and retry.
    echo          Tip: close run.bat / Electron / any GhostCreatorAPI.exe in Task Manager.
    pause
    exit /b 1
)

echo  [OK] Fresh build - old output removed.
echo.

call build-api.bat --no-pause
if %ERRORLEVEL% neq 0 exit /b 1

call npm run build
if %ERRORLEVEL% neq 0 exit /b 1

call npm run electron:build
if %ERRORLEVEL% neq 0 exit /b 1

echo.
echo  [OK] Check release\ folder for installer output.
echo.
pause
