#!/bin/bash
# Agrega una fila al final de un rango.
# Uso: ./agregar_fila.sh "Pestaña!A:E" '["val1","val2","val3"]'

RANGO="${1:-}"
VALORES="${2:-}"

if [ -z "$RANGO" ] || [ -z "$VALORES" ]; then
  echo "Error: debes pasar rango y valores."
  echo "Ejemplo: ./agregar_fila.sh \"Materia Prima!A:E\" '[\"2026-05-13\",\"Jorge Perez\",\"Arcilla\",\"736500\",\"Pendiente\"]'"
  exit 1
fi

python3 "$(dirname "$0")/composio_run.py" GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND \
  "{\"spreadsheet_id\": \"1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE\", \"range\": \"$RANGO\", \"values\": [$VALORES], \"value_input_option\": \"USER_ENTERED\", \"insert_data_option\": \"INSERT_ROWS\"}"
