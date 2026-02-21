@echo off
cd /d "%~dp0"
call .venv\Scripts\activate

echo.
echo ========================================
echo  GenAI Radar - Monitor de fuentes v3
echo ========================================
echo.

REM Limpiar digest_raw.txt de la ejecucion anterior
if exist digest_raw.txt (
    echo Limpiando digest_raw.txt anterior...
    del /f /q digest_raw.txt
)

REM Ejecutar monitor (genera digest_raw.txt)
python monitor_sources.py

echo.
if exist digest_raw.txt (
    echo ----------------------------------------
    echo  LISTO: digest_raw.txt generado
    echo  Arrastralo a Claude para clasificar
    echo  y descarga el digest.txt resultante
    echo ----------------------------------------
) else (
    echo  Sin novedades nuevas esta ejecucion.
)

echo.
pause
