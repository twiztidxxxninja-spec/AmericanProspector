@echo off
echo ============================================
echo  American Prospector — Build & Package
echo ============================================
echo.

REM Step 1: Build the exe
echo [1/4] Building executable...
python -m PyInstaller --noconfirm --onedir --console --name "AmericanProspector" --add-data "data;data" --add-data "music;music" main.py >nul 2>&1
if errorlevel 1 (
    echo BUILD FAILED. Make sure PyInstaller is installed:
    echo   pip install pyinstaller
    pause
    exit /b
)
echo       Done.

REM Step 2: Copy config with API key
echo [2/4] Copying config.json...
if exist config.json (
    copy /Y config.json dist\AmericanProspector\config.json >nul
    echo       Copied your config.json (with API key).
) else (
    copy /Y config.json.example dist\AmericanProspector\config.json >nul
    echo       WARNING: No config.json found. Copied example.
    echo       Edit dist\AmericanProspector\config.json to add your API key!
)

REM Step 3: Copy README
echo [3/4] Copying README...
copy /Y README.md dist\AmericanProspector\README.md >nul
echo       Done.

REM Step 4: Zip it
echo [4/4] Creating zip...
if exist AmericanProspector.zip del AmericanProspector.zip
powershell -command "Compress-Archive -Path 'dist\AmericanProspector' -DestinationPath 'AmericanProspector.zip' -Force"
if errorlevel 1 (
    echo ZIP FAILED.
    pause
    exit /b
)

REM Show result
echo.
echo ============================================
echo  BUILD COMPLETE
echo ============================================
echo.
for %%A in (AmericanProspector.zip) do echo  File: AmericanProspector.zip (%%~zA bytes)
echo.
echo  Send AmericanProspector.zip to your friends.
echo  They unzip it and double-click AmericanProspector.exe.
echo.
echo  Contents:
echo    AmericanProspector.exe  — the game
echo    _internal\              — runtime (don't touch)
echo    config.json             — settings + API key
echo    README.md               — instructions
echo.
pause
