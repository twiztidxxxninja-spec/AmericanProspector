@echo off
echo ============================================
echo  American Prospector — Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from python.org
    echo Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)

echo [1/3] Installing base dependencies...
pip install tcod numpy pygame
if errorlevel 1 (
    echo ERROR: Failed to install base dependencies.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing LLM support (llama-cpp-python)...
echo.
echo Checking for NVIDIA GPU...

:: Try CUDA-enabled build first
pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
if errorlevel 1 (
    echo.
    echo CUDA build failed. Installing CPU-only version...
    echo (Game will work but AI responses will be slower)
    pip install llama-cpp-python --prefer-binary
)

echo.
echo [3/3] Setup complete!
echo.
echo To play: run  play.bat  or  python main.py
echo.
echo The AI model (~4.7 GB) will download automatically on first launch.
echo You need an internet connection for the first run only.
echo.
pause
