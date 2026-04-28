@echo off
title Trunscribator Setup
cd /d "%~dp0"

echo.
echo  === Trunscribator: setup ===
echo.

REM ── Check Python ─────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found.
    echo  Download Python 3.10+ from: https://www.python.org/downloads/
    echo  During install, check "Add Python to PATH"
    pause
    exit /b 1
)
echo  [OK] Python found

REM ── Check / install ffmpeg ────────────────────────────────────────────────
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [..] ffmpeg not found. Installing via winget...
    winget install --id Gyan.FFmpeg -h --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo  [WARN] Could not install ffmpeg automatically.
        echo  Download manually: https://ffmpeg.org/download.html
        echo  Add the bin\ folder to PATH.
        pause
    ) else (
        echo  [OK] ffmpeg installed
    )
) else (
    echo  [OK] ffmpeg found
)

REM ── Create virtual environment ────────────────────────────────────────────
if exist .venv (
    echo  [OK] Virtual environment already exists
) else (
    echo  [..] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create venv
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created
)

REM ── Install dependencies ──────────────────────────────────────────────────
echo  [..] Installing dependencies (3-5 min)...
.venv\Scripts\pip install --quiet --upgrade pip
.venv\Scripts\pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo  [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo  [OK] Dependencies installed

REM ── Desktop shortcut ──────────────────────────────────────────────────────
set SHORTCUT=%USERPROFILE%\Desktop\Trunscribator.lnk
set APP_DIR=%~dp0
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath='%APP_DIR%run.bat'; $s.WorkingDirectory='%APP_DIR%'; $s.IconLocation='shell32.dll,21'; $s.Save()" >nul 2>&1
if exist "%SHORTCUT%" echo  [OK] Desktop shortcut created

echo.
echo  === Setup complete! ===
echo  Run the app: run.bat or desktop shortcut
echo.
pause
