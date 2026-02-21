@echo off
setlocal
cd /d "%~dp0"

call ".\.venv\Scripts\activate.bat"
if errorlevel 1 (
  echo ERROR: No se pudo activar el entorno virtual .venv
  pause
  exit /b 1
)

echo.
echo [1/2] Limpiando entradas marcadas como Delete...
echo ------------------------------------------------
python ".\cleanup.py"
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo ERROR: Cleanup fallo con codigo %ERR%
  pause
  exit /b %ERR%
)

echo.
echo [2/2] Importando digest...
echo ------------------------------------------------
python ".\import_digest_to_notion.py"
set ERR=%ERRORLEVEL%

echo.
if %ERR% NEQ 0 (
  echo ERROR: La importacion fallo con codigo %ERR%
  pause
  exit /b %ERR%
) else (
  echo OK: Proceso completado
  pause
)
endlocal
