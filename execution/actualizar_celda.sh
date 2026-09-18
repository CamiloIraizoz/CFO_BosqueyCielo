#!/bin/bash
# Actualiza el valor de una celda específica.
# Uso: ./actualizar_celda.sh "Pestaña!B5" "NuevoValor"

RANGO="${1:-}"
VALOR="${2:-}"

if [ -z "$RANGO" ] || [ -z "$VALOR" ]; then
  echo "Error: debes pasar rango y valor."
  echo "Ejemplo: ./actualizar_celda.sh \"Mano de Obra!F5\" \"OK Pagado\""
  exit 1
fi

python3 "$(dirname "$0")/composio_run.py" GOOGLESHEETS_VALUES_UPDATE \
  "{\"spreadsheet_id\": \"1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE\", \"range\": \"$RANGO\", \"values\": [[\"$VALOR\"]], \"value_input_option\": \"USER_ENTERED\"}"
