@echo off
REM ---------------------------------------------------------------------------
REM Build a standalone DZ Forge .exe (so a machine without Python can run it).
REM Produces dist\DZForge\DZForge.exe (one-folder build; ship the whole folder).
REM
REM Caveats:
REM  * Smart App Control (this PC) BLOCKS unsigned exes — run it on the server
REM    box / a VM / any non-SAC Windows machine. On THIS PC use start.bat instead.
REM  * Ships CLEAN: no config and no map tiles are bundled, so a fresh copy shows
REM    the first-run setup screen (asks for the server folder + map). Map imagery
REM    needs tiles — generate them per map with tiler.py (see README).
REM ---------------------------------------------------------------------------
cd /d "%~dp0"
python -m pip install --quiet pyinstaller pillow
pyinstaller --noconfirm --onedir --name DZForge ^
  --hidden-import PIL.Image ^
  --add-data "app.html;." ^
  --add-data "index.html;." ^
  --add-data "turrets.html;." ^
  --add-data "vendor;vendor" ^
  server.py
echo.
echo Build output: dist\DZForge\DZForge.exe  (ship the entire dist\DZForge folder)
