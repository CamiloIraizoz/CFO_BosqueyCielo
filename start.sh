#!/bin/bash
set -e

echo "Configurando Composio..."

# Crear user_data.json directamente — sin login interactivo
mkdir -p /root/.composio
cat > /root/.composio/user_data.json << EOF
{
  "api_key": "${COMPOSIO_API_KEY}",
  "base_url": "https://backend.composio.dev",
  "web_url": "https://dashboard.composio.dev/",
  "org_id": "${COMPOSIO_ORG_ID}"
}
EOF

echo "Composio configurado. Iniciando servicios..."
python3 -u execution/shopify_sync.py &
exec python3 -u execution/bot.py
