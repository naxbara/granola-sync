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

echo.
echo ============================================
echo   Sincronizacion completada
echo ============================================
pause
