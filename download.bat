@echo off
chcp 65001 > nul
title Trunscribator — download and install

set INSTALL_DIR=%USERPROFILE%\Trunscribator
set ZIP_URL=https://github.com/Andrey-don/trunscribator/archive/refs/heads/main.zip
set ZIP_TMP=%TEMP%\trunscribator_dl.zip
set UNZIP_TMP=%TEMP%\trunscribator_unzip

echo.
echo  ============================================
echo   Транскрибатор — загрузка и установка
echo  ============================================
echo.
echo  Папка установки: %INSTALL_DIR%
echo.

REM ── 1. Скачать ZIP ───────────────────────────────────────────────────────
echo  [1/4] Скачиваю с GitHub...
curl -L --progress-bar -o "%ZIP_TMP%" "%ZIP_URL%"
if %errorlevel% neq 0 (
    echo.
    echo  [ОШИБКА] Не удалось скачать файл.
    echo  Проверьте подключение к интернету.
    pause
    exit /b 1
)
echo  [OK] Файл скачан

REM ── 2. Распаковать ───────────────────────────────────────────────────────
echo  [2/4] Распаковываю...
if exist "%UNZIP_TMP%" rd /s /q "%UNZIP_TMP%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP_TMP%' -DestinationPath '%UNZIP_TMP%' -Force"
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Не удалось распаковать архив.
    pause
    exit /b 1
)
del "%ZIP_TMP%" >nul 2>&1
echo  [OK] Распакован

REM ── 3. Переместить в папку установки ────────────────────────────────────
echo  [3/4] Перемещаю в папку установки...
if exist "%INSTALL_DIR%" rd /s /q "%INSTALL_DIR%"
powershell -NoProfile -Command "Move-Item -Path '%UNZIP_TMP%\trunscribator-main' -Destination '%INSTALL_DIR%'"
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Не удалось переместить файлы.
    pause
    exit /b 1
)
rd /s /q "%UNZIP_TMP%" >nul 2>&1
echo  [OK] Файлы на месте

REM ── 4. Запустить установку ───────────────────────────────────────────────
echo  [4/4] Запускаю установку зависимостей...
echo.
cd /d "%INSTALL_DIR%"
call install.bat
