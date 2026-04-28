@echo off
title Trunscribator Installer

set INSTALL_DIR=%USERPROFILE%\Trunscribator
set ZIP_URL=https://github.com/Andrey-don/trunscribator/archive/refs/heads/main.zip
set ZIP_TMP=%TEMP%\trunscribator_dl.zip
set UNZIP_TMP=%TEMP%\trunscribator_unzip

echo.
echo  === Trunscribator: download and install ===
echo.
echo  Install folder: %INSTALL_DIR%
echo.

echo  [1/4] Downloading from GitHub...
curl -L --progress-bar -o "%ZIP_TMP%" "%ZIP_URL%"
if %errorlevel% neq 0 (
    echo  [ERROR] Download failed. Check internet connection.
    pause
    exit /b 1
)
echo  [OK] Downloaded

echo  [2/4] Extracting...
if exist "%UNZIP_TMP%" rd /s /q "%UNZIP_TMP%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP_TMP%' -DestinationPath '%UNZIP_TMP%' -Force"
if %errorlevel% neq 0 (
    echo  [ERROR] Extraction failed.
    pause
    exit /b 1
)
del "%ZIP_TMP%" >nul 2>&1
echo  [OK] Extracted

echo  [3/4] Moving to install folder...
if exist "%INSTALL_DIR%" rd /s /q "%INSTALL_DIR%"
powershell -NoProfile -Command "Move-Item -Path '%UNZIP_TMP%\trunscribator-main' -Destination '%INSTALL_DIR%'"
if %errorlevel% neq 0 (
    echo  [ERROR] Move failed.
    pause
    exit /b 1
)
rd /s /q "%UNZIP_TMP%" >nul 2>&1
echo  [OK] Files ready

echo  [4/4] Running install script...
echo.
cd /d "%INSTALL_DIR%"
call install.bat
