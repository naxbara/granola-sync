#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "============================================"
echo "  Granola Sync - Sincronización Diaria"
echo "============================================"
echo

python3 -m granola_sync --mode=daily --config config.yaml

echo
echo "============================================"
echo "  Sincronización completada"
echo "============================================"
