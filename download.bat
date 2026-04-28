@echo off
chcp 65001 > nul
title Скачать и установить Транскрибатор
echo.
echo  ============================================
echo   Транскрибатор — загрузка и установка
echo  ============================================
echo.

REM ── Куда сохранить ───────────────────────────────────────────────────────
set INSTALL_DIR=%USERPROFILE%\Транскрибатор
set ZIP_URL=https://github.com/Andrey-don/trunscribator/archive/refs/heads/main.zip
set ZIP_TMP=%TEMP%\trunscribator.zip

echo  Папка установки: %INSTALL_DIR%
echo.

REM ── Скачать ZIP с GitHub ─────────────────────────────────────────────────
echo  [..] Скачиваю проект с GitHub...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%ZIP_TMP%'" >nul 2>&1
if not exist "%ZIP_TMP%" (
    echo  [ОШИБКА] Не удалось скачать. Проверьте интернет-соединение.
    pause
    exit /b 1
)
echo  [OK] Файл скачан

REM ── Распаковать ──────────────────────────────────────────────────────────
echo  [..] Распаковываю...
if exist "%INSTALL_DIR%" rd /s /q "%INSTALL_DIR%"
powershell -NoProfile -Command ^
  "Expand-Archive -Path '%ZIP_TMP%' -DestinationPath '%TEMP%\trunscribator_unzip' -Force" >nul 2>&1
move /y "%TEMP%\trunscribator_unzip\trunscribator-main" "%INSTALL_DIR%" >nul 2>&1
rd /s /q "%TEMP%\trunscribator_unzip" >nul 2>&1
del "%ZIP_TMP%" >nul 2>&1
echo  [OK] Распакован в %INSTALL_DIR%

REM ── Запустить установку ──────────────────────────────────────────────────
echo.
echo  [..] Запускаю установку зависимостей...
echo.
cd /d "%INSTALL_DIR%"
call install.bat
