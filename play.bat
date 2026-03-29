@echo off
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo Game crashed. Check error.log for details.
    pause
)
