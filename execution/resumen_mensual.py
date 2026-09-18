#!/usr/bin/env python3
"""
Genera un resumen financiero del mes leyendo el Sheet via Composio.
Uso: python3 resumen_mensual.py [mes]
Ejemplo: python3 resumen_mensual.py Mayo
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from composio_run import run
import json
import subprocess

COMPOSIO = os.path.expanduser("~/.composio/composio")
SPREADSHEET_ID = "1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE"

def leer_rango(rango):
    result = subprocess.run(
        [COMPOSIO, "execute", "GOOGLESHEETS_VALUES_GET", "-d",
         json.dumps({"spreadsheet_id": SPREADSHEET_ID, "range": rango, "value_render_option": "FORMATTED_VALUE"})],
        capture_output=True, text=True
    )
    stdout = "\n".join(
        l for l in result.stdout.splitlines()
        if "Update available" not in l and "composio upgrade" not in l
    ).strip()
    try:
        resp = json.loads(stdout)
        if resp.get("successful"):
            return resp["data"].get("values", [])
    except Exception:
        pass
    return []

def fmt_tabla(filas, titulo):
    if not filas:
        return
    print(f"\n{'─'*55}")
    print(f"  {titulo}")
    print(f"{'─'*55}")
    for fila in filas:
        if fila and any(str(c).strip() for c in fila):
            cols = [str(c).ljust(25) for c in fila[:4]]
            print("  " + " │ ".join(cols))

def main():
    mes = sys.argv[1] if len(sys.argv) > 1 else "Mayo"
    print(f"\n{'═'*55}")
    print(f"  RESUMEN FINANCIERO — {mes.upper()}")
    print(f"{'═'*55}")

    pnl = leer_rango("PNL!A1:F25")
    fmt_tabla(pnl, "P&L — Estado de Resultados")

    consolid = leer_rango("Ingresos/Egresos Consolidados!A1:J15")
    fmt_tabla(consolid, "Ingresos / Egresos Consolidados")

    banco = leer_rango("Resumen Bancario 2026!A1:D15")
    fmt_tabla(banco, "Resumen Bancario 2026")

    print(f"\n{'═'*55}\n")

if __name__ == "__main__":
    main()
