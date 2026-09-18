#!/bin/bash
# Uso: ./leer_rango.sh "NombrePestaña!A1:Z50"
# Ejemplo: ./leer_rango.sh "PNL!A1:F20"

RANGO="${1:-}"
if [ -z "$RANGO" ]; then
  echo "Error: debes pasar un rango. Ejemplo: ./leer_rango.sh \"PNL!A1:F20\""
  exit 1
fi

python3 "$(dirname "$0")/composio_run.py" GOOGLESHEETS_VALUES_GET \
  "{\"spreadsheet_id\": \"1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE\", \"range\": \"$RANGO\", \"value_render_option\": \"FORMATTED_VALUE\"}"
