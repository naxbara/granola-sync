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

echo.
echo ============================================
echo   Sincronizacion completada
echo ============================================
pause
