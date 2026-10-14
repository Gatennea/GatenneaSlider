﻿@echo off
REM =====================================================
REM  Gatennea Slider Puzzle - Auto Build Script (PyInstaller)
REM  Packages main.py into a standalone Windows folder (onedir mode).
REM
REM  用法:
REM    build_exe.bat           正常打包（清理旧产物 + --clean）
REM    build_exe.bat skipclean 跳过清理，复用已有构建缓存（调试/沙箱用，更快）
REM
REM  脚本会统计打包用时，结束前统一汇报状态（结果/用时/产物），
REM  并以 pause 停留窗口，不会自动关闭。
REM =====================================================
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

REM ---------- 计时开始 ----------
set "START_RAW=%TIME%"
call :to_sec "%START_RAW%" START_SEC

echo ================================================
echo  Project root : %PROJECT_DIR%
echo  Start time  : %START_RAW%
echo ================================================

REM ---------- Check Python ----------
set "PY=D:\python\python.exe"
if not exist "%PY%" (
    echo [ERROR] %PY% not found.
    goto :report_fail
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
        goto :report_fail
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
        goto :report_fail
    )
)
echo [OK] setuptools is ready.

REM ---------- Clean old build artifacts (keep .spec) ----------
if /i "%~1"=="skipclean" (
    echo [INFO] skipclean 模式：跳过旧产物与缓存清理（复用已有构建缓存）
    goto :build
)
echo [INFO] Cleaning old build artifacts...
if exist "build" rd /s /q "build"
if exist "dist"  rd /s /q "dist"
echo [INFO] Cleaning PyInstaller binary cache...
if exist "%LOCALAPPDATA%\pyinstaller\bincache10py31264bit" rd /s /q "%LOCALAPPDATA%\pyinstaller\bincache10py31264bit"

:build
echo.
echo [INFO] Building with optimized spec (onedir)...
set "PI_FLAGS=--noconfirm"
if /i not "%~1"=="skipclean" set "PI_FLAGS=--noconfirm --clean"
%PY% -m PyInstaller %PI_FLAGS% Gatenneaslider.spec
set BUILD_RC=%ERRORLEVEL%

REM ---------- 计时结束 ----------
set "END_RAW=%TIME%"
call :to_sec "%END_RAW%" END_SEC
set /a "ELAPSED_SEC = END_SEC - START_SEC"
if %ELAPSED_SEC% LSS 0 set /a "ELAPSED_SEC += 86400"

REM ---------- 结果汇报 ----------
echo.
echo ================================================
if !BUILD_RC!==0 (
    echo  [DONE] 打包成功 - Build succeeded
) else (
    echo  [FAIL] 打包失败 - Build failed
)
echo  Exit code   : !BUILD_RC!
echo  Start time  : %START_RAW%
echo  End time    : %END_RAW%
echo  Elapsed     : %ELAPSED_SEC% 秒
echo  Output      : dist\Gatenneaslider\Gatenneaslider.exe
if !BUILD_RC!==0 (
    if exist "dist\Gatenneaslider\Gatenneaslider.exe" (
        for %%I in ("dist\Gatenneaslider\Gatenneaslider.exe") do (
            echo  EXE size    : %%~zI bytes
        )
    ) else (
        echo  EXE size    : [未找到 exe，请检查上方日志]
    )
)
echo ================================================
echo.
echo 按任意键关闭此窗口...
pause >nul
exit /b !BUILD_RC!

REM ---------- 环境检查失败的统一汇报 ----------
:report_fail
echo.
echo ================================================
echo  [FAIL] 环境检查未通过，打包未开始
echo  Start time  : %START_RAW%
set "END_RAW=%TIME%"
call :to_sec "%END_RAW%" END_SEC
set /a "ELAPSED_SEC = END_SEC - START_SEC"
if %ELAPSED_SEC% LSS 0 set /a "ELAPSED_SEC += 86400"
echo  End time    : %END_RAW%
echo  Elapsed     : %ELAPSED_SEC% 秒 (仅环境检查耗时)
echo ================================================
echo.
echo 按任意键关闭此窗口...
pause >nul
exit /b 1

REM ---------- 把 HH:MM:SS[.cc] 转成总秒数 ----------
:to_sec
setlocal
set "t=%~1"
set "t=%t: =0%"
set "t=%t:~0,8%"
for /f "tokens=1-3 delims=:" %%a in ("%t%") do set /a "secs=(%%a*3600 + %%b*60 + %%c)"
endlocal & set "%2=%secs%"
goto :eof
