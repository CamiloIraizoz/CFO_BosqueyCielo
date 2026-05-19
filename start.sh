#!/bin/bash
set -e
export PATH="/opt/venv/bin:$PATH"
echo "Iniciando servicios Amphora B&C CFO..."
python3 -u execution/shopify_sync.py &
exec python3 -u execution/bot.py
