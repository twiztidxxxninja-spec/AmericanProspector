@echo off
cd /d "%~dp0"
title American Prospector

REM ── Check for Python ─────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  Python is not installed. Installing now...
        echo.
        echo  This will open the Microsoft Store to install Python.
        echo  Click "Get" or "Install", wait for it to finish,
        echo  then close this window and double-click PLAY.bat again.
        echo.
        start ms-windows-store://pdp/?productid=9PJPW5LDXLZ5
        pause
        exit /b
    )
)

REM ── Install dependencies (silent, only first run) ────────────
if not exist ".deps_installed" (
    echo  First run — installing game libraries...
    echo  This takes about 30 seconds. Please wait.
    echo.
    pip install python-tcod pygame-ce --quiet 2>nul
    if errorlevel 1 (
        python -m pip install python-tcod pygame-ce --quiet 2>nul
    )
    echo done > .deps_installed
    echo  Done. Starting game...
    echo.
)

REM ── Create config.json if missing ────────────────────────────
if not exist "config.json" (
    if exist "config.json.example" (
        copy /Y config.json.example config.json >nul
    )
)

REM ── Launch ───────────────────────────────────────────────────
python main.py
if errorlevel 1 (
    echo.
    echo  Game crashed. Check error.log for details.
    echo.
    pause
)
