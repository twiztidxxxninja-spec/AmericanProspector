@echo off
echo American Prospector - Starting...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found! Install it from the Microsoft Store:
    echo   1. Open Microsoft Store
    echo   2. Search "Python 3.12"
    echo   3. Click Install
    echo   4. Run this file again
    echo.
    pause
    exit /b
)

REM Install dependencies if needed
echo Checking dependencies...
pip install python-tcod pygame-ce --quiet 2>nul

REM Check for config.json
if not exist config.json (
    if exist config.json.example (
        echo No config.json found. Copying from config.json.example...
        copy config.json.example config.json >nul
        echo.
        echo IMPORTANT: Edit config.json and add your API key if using AI features.
        echo The game will work without it, but freeform actions won't have AI responses.
        echo.
    )
)

echo Starting game...
python main.py
if errorlevel 1 (
    echo.
    echo Game crashed. Check error.log for details.
    pause
)
