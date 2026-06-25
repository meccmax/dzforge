@echo off
title DZ Forge
cd /d "%~dp0"
echo Starting DZ Forge server...
start "DZ Forge server" python server.py
timeout /t 2 >nul
start "" http://localhost:8777/app.html
echo.
echo DZ Forge is running at http://localhost:8777/app.html
echo Close the "DZ Forge server" window to stop it.
