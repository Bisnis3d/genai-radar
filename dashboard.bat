@echo off
cd /d "%~dp0"
call .venv\Scripts\activate

echo.
echo ========================================
echo  GenAI Radar - Dashboard
echo ========================================
echo.
echo Descargando datos de Notion y generando dashboard...
echo.

python generar_dashboard.py

echo.
pause
