@echo off
cd /d "%~dp0"

start /wait notepad digest.txt

echo.
echo Lanzando importacion...

call importar_digest.bat
