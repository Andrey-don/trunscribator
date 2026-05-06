@echo off
chcp 65001 >nul
title Транскрибатор — Онлайн-установка
color 0A

echo.
echo  ================================================
echo   Транскрибатор — Онлайн-установка
echo   Скачивает всё необходимое с интернета
echo  ================================================
echo.
echo  Что будет установлено:
echo    [1] Python 3.11
echo    [2] ffmpeg
echo    [3] Приложение Транскрибатор
echo    [4] Зависимости Python
echo    [5] Ollama (локальный ИИ)
echo    [6] Модель gemma3:12b  (~8 ГБ, займёт время)
echo.
echo  Нужен интернет. Общий объём загрузки: ~10-12 ГБ
echo.
echo  Нажмите любую клавишу для начала...
pause >nul

set INSTALL_DIR=%USERPROFILE%\Trunscribator
set ZIP_URL=https://github.com/Andrey-don/trunscribator/archive/refs/heads/main.zip
set ZIP_TMP=%TEMP%\trunscribator_dl.zip
set UNZIP_TMP=%TEMP%\trunscribator_unzip

REM ── 1. Python ─────────────────────────────────────────────────────────────
echo.
echo  [1/6] Проверка Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  Устанавливаю Python 3.11...
    winget install --id Python.Python.3.11 -h --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo  [ОШИБКА] Python не удалось установить автоматически.
        echo  Скачайте вручную: https://www.python.org/downloads/
        echo  При установке отметьте "Add Python to PATH"
        pause
        exit /b 1
    )
    echo  [OK] Python установлен. Закройте это окно и запустите скрипт заново.
    pause
    exit /b 0
)
echo  [OK] Python найден

REM ── 2. ffmpeg ──────────────────────────────────────────────────────────────
echo.
echo  [2/6] Проверка ffmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo  Устанавливаю ffmpeg...
    winget install --id Gyan.FFmpeg -h --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo  [ПРЕДУПРЕЖДЕНИЕ] ffmpeg не установлен автоматически.
        echo  Скачайте вручную: https://ffmpeg.org/download.html
    ) else (
        echo  [OK] ffmpeg установлен
    )
) else (
    echo  [OK] ffmpeg найден
)

REM ── 3. Приложение ─────────────────────────────────────────────────────────
echo.
echo  [3/6] Скачивание приложения с GitHub...
curl -L --progress-bar -o "%ZIP_TMP%" "%ZIP_URL%"
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Не удалось скачать. Проверьте интернет.
    pause
    exit /b 1
)
if exist "%UNZIP_TMP%" rd /s /q "%UNZIP_TMP%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP_TMP%' -DestinationPath '%UNZIP_TMP%' -Force"
del "%ZIP_TMP%" >nul 2>&1
if exist "%INSTALL_DIR%" rd /s /q "%INSTALL_DIR%"
move /y "%UNZIP_TMP%\trunscribator-main" "%INSTALL_DIR%" >nul 2>&1
rd /s /q "%UNZIP_TMP%" >nul 2>&1
echo  [OK] Приложение скачано в: %INSTALL_DIR%

REM ── 4. Зависимости Python ─────────────────────────────────────────────────
echo.
echo  [4/6] Установка зависимостей Python (3-5 минут)...
cd /d "%INSTALL_DIR%"
python -m venv .venv
.venv\Scripts\pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Ошибка установки зависимостей
    pause
    exit /b 1
)
.venv\Scripts\pip install --quiet ollama
echo  [OK] Зависимости установлены

REM ── 5. Ollama ─────────────────────────────────────────────────────────────
echo.
echo  [5/6] Проверка Ollama...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  Устанавливаю Ollama...
    winget install --id Ollama.Ollama -h --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo  [ПРЕДУПРЕЖДЕНИЕ] Ollama не установлена.
        echo  Скачайте вручную: https://ollama.com
    ) else (
        echo  [OK] Ollama установлена
        timeout /t 5 /nobreak >nul
    )
) else (
    echo  [OK] Ollama уже установлена
)

REM ── 6. Модель Ollama ──────────────────────────────────────────────────────
echo.
echo  [6/6] Скачивание модели gemma3:12b (~8 ГБ)...
echo  Это может занять 10-30 минут в зависимости от скорости интернета...
echo.
ollama pull gemma3:12b
if %errorlevel% neq 0 (
    echo  [ПРЕДУПРЕЖДЕНИЕ] Модель не скачана.
    echo  Запустите вручную после установки: ollama pull gemma3:12b
)

REM ── Ярлык на рабочем столе ───────────────────────────────────────────────
set SHORTCUT=%USERPROFILE%\Desktop\Транскрибатор.lnk
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath='%INSTALL_DIR%\run_2.bat'; $s.WorkingDirectory='%INSTALL_DIR%'; $s.IconLocation='shell32.dll,21'; $s.Save()" >nul 2>&1
echo.
echo  [OK] Ярлык создан на рабочем столе

echo.
echo  ================================================
echo   Установка завершена!
echo   Запускайте через ярлык "Транскрибатор"
echo   на рабочем столе.
echo  ================================================
echo.
pause
