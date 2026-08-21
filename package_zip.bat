@echo off
REM =====================================================
REM  Gatennea Slider Puzzle - Auto Zip Script
REM  Creates a zip of the project while excluding:
REM      __pycache__, .pyc, .venv, venv, build, dist,
REM      *.spec, *.zip, .vscode, .git, .clinerules
REM =====================================================
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

for /f "tokens=2 delims==" %%I in (
    'wmic os get localdatetime /value ^| find "="'
) do set "dt=%%I"

set "YY=%dt:~0,4%"
set "MM=%dt:~4,2%"
set "DD=%dt:~6,2%"
set "HH=%dt:~8,2%"
set "MI=%dt:~10,2%"
set "SS=%dt:~12,2%"
set "ZIP_NAME=Gatenneaslider_%YY%%MM%%DD%_%HH%%MI%%SS%.zip"

echo ================================================
echo  Project root : %PROJECT_DIR%
echo  Output zip   : %ZIP_NAME%
echo ================================================

where powershell >nul 2>&1
if errorlevel 1 (
    echo [ERROR] powershell is required for zipping.
    exit /b 1
)

echo [INFO] Zipping (excluding __pycache__, *.pyc, venv dirs, build artifacts)...

set "PACK_SOURCE=%PROJECT_DIR%"
set "PACK_ZIPNAME=%ZIP_NAME%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dpn0.ps1"

if errorlevel 1 (
    echo [ERROR] Zipping failed.
    exit /b 1
)

echo.
echo ================================================
echo  [DONE] Zip: %ZIP_NAME%
echo ================================================

endlocal
