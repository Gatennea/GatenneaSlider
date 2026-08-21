@echo off
REM =====================================================
REM  Gatennea Slider Puzzle - Auto Build Script (PyInstaller)
REM  Packages main.py into a standalone Windows exe (~24MB).
REM  Uses optimized Gatenneaslider.spec configuration.
REM =====================================================
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo ================================================
echo  Project root : %PROJECT_DIR%
echo ================================================

REM ---------- Check Python ----------
set "PY=D:\python\python.exe"
if not exist "%PY%" (
    echo [ERROR] %PY% not found.
    exit /b 1
)
echo [OK] Python: & %PY% --version

REM ---------- Install / check PyInstaller ----------
%PY% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not installed, installing...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)
echo [OK] PyInstaller is ready.

REM ---------- Install pygame if missing ----------
%PY% -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [INFO] pygame not installed, installing...
    %PY% -m pip install pygame
)
echo [OK] pygame is ready.

REM ---------- Install setuptools with pkg_resources support ----------
%PY% -c "import pkg_resources" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing setuptools with pkg_resources support...
    %PY% -m pip install "setuptools<70"
    if errorlevel 1 (
        echo [ERROR] Failed to install setuptools.
        exit /b 1
    )
)
echo [OK] setuptools is ready.

REM ---------- Clean old build artifacts (keep .spec) ----------
echo [INFO] Cleaning old build artifacts...
if exist "build" rd /s /q "build"
if exist "dist"  rd /s /q "dist"

REM ---------- Clean corrupted PyInstaller cache ----------
echo [INFO] Cleaning PyInstaller binary cache...
if exist "%LOCALAPPDATA%\pyinstaller\bincache10py31264bit" rd /s /q "%LOCALAPPDATA%\pyinstaller\bincache10py31264bit"

REM ---------- Build using optimized spec ----------
echo.
echo [INFO] Building with optimized spec (expected ~24MB)...
%PY% -m PyInstaller --noconfirm --clean Gatenneaslider.spec

if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b 1
)

echo.
echo ================================================
echo  [DONE] Build succeeded.
echo  Executable: dist\Gatenneaslider.exe
echo ================================================

endlocal
