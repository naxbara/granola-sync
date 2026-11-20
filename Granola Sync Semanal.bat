@echo off
title Granola Sync - Semanal
cd /d "%~dp0"

:: Calculate date 7 days ago (YYYY-MM-DD)
for /f "tokens=*" %%i in ('python -c "from datetime import datetime, timedelta; print((datetime.now() - timedelta(days=7)).strftime('%%Y-%%m-%%d'))"') do set FROM_DATE=%%i

echo ============================================
echo   Granola Sync - Sincronizacion Semanal
echo   Desde: %FROM_DATE%
echo ============================================
echo.

python -m granola_sync --mode=historical --from=%FROM_DATE% --config config.yaml
set "RC=%ERRORLEVEL%"

:: 0 = ok, 3 = notes written but vault indexes not rebuilt, anything else = failed.
:: Single-line IFs on purpose: this file uses LF endings, and cmd misreads blocks/labels with LF.
echo.
echo ============================================
if "%RC%"=="0" echo   Sincronizacion completada
if "%RC%"=="3" echo   Sincronizacion completada, pero los indices del vault no se regeneraron
if not "%RC%"=="0" if not "%RC%"=="3" echo   La sincronizacion FALLO (codigo %RC%) - revisa el error de arriba
echo ============================================
pause
exit /b %RC%
