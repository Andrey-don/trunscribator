@echo off
chcp 65001 >nul
title Транскрибатор — Установка с моделью на носителе
color 0A

echo.
echo  ================================================
echo   Транскрибатор — Установка с моделью
echo   Ollama-модель берётся с носителя (не качается)
echo  ================================================
echo.

set INSTALL_DIR=%USERPROFILE%\Trunscribator
set ZIP_URL=https://github.com/Andrey-don/trunscribator/archive/refs/heads/main.zip
set ZIP_TMP=%TEMP%\trunscribator_dl.zip
set UNZIP_TMP=%TEMP%\trunscribator_unzip
set MODEL_SRC=%~dp0ollama_models

REM ── Проверка наличия папки с моделью ──────────────────────────────────────
if exist "%MODEL_SRC%" (
    echo  [OK] Папка ollama_models найдена — модель будет скопирована локально
) else (
    echo  [ПРЕДУПРЕЖДЕНИЕ] Папка ollama_models не найдена рядом с установщиком.
    echo.
    echo  Ожидается структура:
    echo    install_hybrid.bat
    echo    ollama_models\          ^<-- скопируйте сюда из источника
    echo      blobs\
    echo      manifests\
    echo.
    echo  Без папки модель будет скачана из интернета (~8 ГБ).
    echo.
    set /p CONTINUE=Продолжить со скачиванием? (y/n):
    if /i "%CONTINUE%" neq "y" exit /b 0
)
echo.
echo  Нажмите любую клавишу для начала...
pause >nul

REM ── 1. Python ─────────────────────────────────────────────────────────────
echo.
echo  [1/6] Проверка Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  Устанавливаю Python 3.11...
    winget install --id Python.Python.3.11 -h --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo  [ОШИБКА] Python не удалось установить.
        echo  Скачайте вручную: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo  [OK] Python установлен. Закройте окно и запустите скрипт заново.
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
        echo  [ПРЕДУПРЕЖДЕНИЕ] ffmpeg не установлен. Установите вручную.
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
    echo  [ОШИБКА] Не удалось скачать. Нужен интернет для приложения.
    pause
    exit /b 1
)
if exist "%UNZIP_TMP%" rd /s /q "%UNZIP_TMP%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP_TMP%' -DestinationPath '%UNZIP_TMP%' -Force"
del "%ZIP_TMP%" >nul 2>&1
if exist "%INSTALL_DIR%" rd /s /q "%INSTALL_DIR%"
move /y "%UNZIP_TMP%\trunscribator-main" "%INSTALL_DIR%" >nul 2>&1
rd /s /q "%UNZIP_TMP%" >nul 2>&1
echo  [OK] Приложение установлено в: %INSTALL_DIR%

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
        echo  [ПРЕДУПРЕЖДЕНИЕ] Ollama не установлена автоматически.
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
echo  [6/6] Установка модели gemma3:12b...
if exist "%MODEL_SRC%" (
    echo  Копирую модель с носителя (без скачивания)...
    set OLLAMA_MODELS=%USERPROFILE%\.ollama\models
    if not exist "%OLLAMA_MODELS%" mkdir "%OLLAMA_MODELS%"
    xcopy /e /i /q /y "%MODEL_SRC%\blobs" "%OLLAMA_MODELS%\blobs\" >nul 2>&1
    xcopy /e /i /q /y "%MODEL_SRC%\manifests" "%OLLAMA_MODELS%\manifests\" >nul 2>&1
    echo  [OK] Модель скопирована
) else (
    echo  Скачиваю модель из интернета (~8 ГБ)...
    ollama pull gemma3:12b
    if %errorlevel% neq 0 (
        echo  [ПРЕДУПРЕЖДЕНИЕ] Модель не скачана.
        echo  Запустите вручную: ollama pull gemma3:12b
    )
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
