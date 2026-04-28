@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist .venv (
    echo  Виртуальное окружение не найдено.
    echo  Сначала запустите install.bat
    pause
    exit /b 1
)

.venv\Scripts\python main.py
