#!/usr/bin/env bash
cd "$(dirname "$0")"

# Portable 7-days-ago: BSD/macOS `date -v`, GNU/Linux `date -d`.
FROM_DATE=$(date -v-7d "+%Y-%m-%d" 2>/dev/null || date -d "7 days ago" "+%Y-%m-%d")

echo "============================================"
echo "  Granola Sync - Sincronización Semanal"
echo "  Desde: $FROM_DATE"
echo "============================================"
echo

python3 -m granola_sync --mode=historical --from="$FROM_DATE" --config config.yaml

echo
echo "============================================"
echo "  Sincronización completada"
echo "============================================"
