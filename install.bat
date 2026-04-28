@echo off
chcp 65001 > nul
title Установка Транскрибатора
echo.
echo  ============================================
echo   Транскрибатор — установка
echo  ============================================
echo.

REM ── Проверка Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Python не найден.
    echo.
    echo  Скачайте Python 3.10 или новее:
    echo  https://www.python.org/downloads/
    echo.
    echo  При установке поставьте галочку "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER%

REM ── Проверка / установка ffmpeg ──────────────────────────────────────────
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [..] ffmpeg не найден. Устанавливаю через winget...
    winget install --id Gyan.FFmpeg -h --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo  [ПРЕДУПРЕЖДЕНИЕ] ffmpeg не удалось установить автоматически.
        echo  Скачайте вручную: https://ffmpeg.org/download.html
        echo  и добавьте папку bin\ в переменную PATH.
        echo.
        pause
    ) else (
        echo  [OK] ffmpeg установлен
    )
) else (
    echo  [OK] ffmpeg найден
)

REM ── Создание виртуального окружения ─────────────────────────────────────
if exist .venv (
    echo  [OK] Виртуальное окружение уже существует
) else (
    echo  [..] Создаю виртуальное окружение...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ОШИБКА] Не удалось создать venv
        pause
        exit /b 1
    )
    echo  [OK] Виртуальное окружение создано
)

REM ── Установка зависимостей ───────────────────────────────────────────────
echo  [..] Устанавливаю зависимости (может занять 3-5 минут)...
.venv\Scripts\pip install --quiet --upgrade pip
.venv\Scripts\pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Не удалось установить зависимости
    pause
    exit /b 1
)
echo  [OK] Зависимости установлены

REM ── Ярлык на рабочем столе ───────────────────────────────────────────────
set SHORTCUT_PATH=%USERPROFILE%\Desktop\Транскрибатор.lnk
set APP_DIR=%~dp0
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); ^
   $s.TargetPath = '%APP_DIR%run.bat'; ^
   $s.WorkingDirectory = '%APP_DIR%'; ^
   $s.IconLocation = 'shell32.dll,21'; ^
   $s.Description = 'Транскрибатор видео'; ^
   $s.Save()" >nul 2>&1
if exist "%SHORTCUT_PATH%" (
    echo  [OK] Ярлык создан на рабочем столе
)

echo.
echo  ============================================
echo   Установка завершена!
echo   Запуск: run.bat  или ярлык на рабочем столе
echo  ============================================
echo.
pause
