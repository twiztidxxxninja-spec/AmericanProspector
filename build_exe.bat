@echo off
echo Building American Prospector executable...
echo.

pyinstaller --noconfirm --onedir --console ^
    --name "AmericanProspector" ^
    --add-data "data;data" ^
    --add-data "music;music" ^
    --add-data "src;src" ^
    --add-data "config.json.example;." ^
    --hidden-import "src" ^
    --hidden-import "pygame" ^
    --hidden-import "tcod" ^
    --hidden-import "numpy" ^
    main.py

echo.
echo Build complete! Output in dist\AmericanProspector\
echo.
echo To ship to friends:
echo   1. Copy dist\AmericanProspector\ folder
echo   2. Copy your config.json into that folder (with API key)
echo   3. Rename config.json.example to config.json if needed
echo   4. Zip and send!
pause
