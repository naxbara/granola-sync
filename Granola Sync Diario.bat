@echo off
title Granola Sync - Diario
cd /d "%~dp0"

echo ============================================
echo   Granola Sync - Sincronizacion Diaria
echo   Ultimas 24 horas
echo ============================================
echo.

python -m granola_sync --mode=daily --config config.yaml

echo.
echo ============================================
echo   Sincronizacion completada
echo ============================================
pause
