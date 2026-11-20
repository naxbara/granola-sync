@echo off
title Granola Sync - Diario
cd /d "%~dp0"

:: Ventana movil de 3 dias (resistente a dias saltados: si un dia no corre,
:: el siguiente igual recupera lo pendiente). El dedup + la actualizacion de
:: notas hacen que re-revisar la ventana sea idempotente y casi gratis.
for /f "tokens=*" %%i in ('python -c "from datetime import datetime, timedelta; print((datetime.now() - timedelta(days=3)).strftime('%%Y-%%m-%%d'))"') do set FROM_DATE=%%i

echo ============================================
echo   Granola Sync - Sincronizacion Diaria
echo   Ultimos 3 dias (ventana movil)
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
