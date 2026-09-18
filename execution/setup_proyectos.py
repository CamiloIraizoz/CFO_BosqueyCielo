#!/usr/bin/env python3
"""
Crea (o reconstruye) la pestaña "Proyectos": presupuesto original, presupuesto
revisado y real (via SUMIFS sobre Movimientos) por proyecto/colaboración puntual.

Uso: python3 execution/setup_proyectos.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from composio_run import run
import json
import subprocess

COMPOSIO = os.path.expanduser("~/.composio/composio")
SPREADSHEET_ID = "1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE"

HEADERS = [
    "Proyecto", "Cliente/Colaborador", "Estado", "Fecha Inicio", "Fecha Cierre",
    "Presup. Original - Materia Prima", "Presup. Original - Mano de Obra",
    "Presup. Original - Costos Indirectos", "Presup. Original - Ingreso Cotizado",
    "Presup. Revisado - Materia Prima", "Presup. Revisado - Mano de Obra",
    "Presup. Revisado - Costos Indirectos", "Presup. Revisado - Ingreso Cotizado",
    "Real - Materia Prima", "Real - Mano de Obra", "Real - Costos Indirectos",
    "Real - Ingreso", "Margen Cotizado %", "Margen Real %", "Notas",
]

# Fórmulas de ejemplo para la fila 2 (copiar hacia abajo al agregar un proyecto)
# Orden = columnas N,O,P,Q,R,S: Real MP, Real MO, Real CI, Real Ingreso, Margen Cotizado%, Margen Real%
FORMULAS_FILA2 = [
    '=SUMIFS(Movimientos!I:I,Movimientos!K:K,A2,Movimientos!E:E,"Materia Prima")',
    '=SUMIFS(Movimientos!I:I,Movimientos!K:K,A2,Movimientos!E:E,"Mano de Obra")',
    '=SUMIFS(Movimientos!I:I,Movimientos!K:K,A2,Movimientos!E:E,"Costos Indirectos")',
    '=SUMIFS(Movimientos!I:I,Movimientos!K:K,A2,Movimientos!D:D,"Ingreso")',
    '=IFERROR((I2-F2-G2-H2)/I2,"")',
    '=IFERROR((Q2-N2-O2-P2)/Q2,"")',
]


def composio_call(tool: str, data: dict) -> dict:
    result = subprocess.run(
        [COMPOSIO, "execute", tool, "-d", json.dumps(data)],
        capture_output=True, text=True
    )
    stdout = "\n".join(
        l for l in result.stdout.splitlines()
        if "Update available" not in l and "composio upgrade" not in l
    ).strip()
    try:
        return json.loads(stdout)
    except Exception:
        return {"successful": False, "error": result.stderr or stdout}


def sheet_existe(nombre: str) -> bool:
    resp = composio_call("GOOGLESHEETS_GET_SHEET_NAMES", {"spreadsheet_id": SPREADSHEET_ID})
    return resp.get("successful") and nombre in resp["data"].get("sheet_names", [])


def main():
    if sheet_existe("Proyectos"):
        print("La pestaña 'Proyectos' ya existe. No se crea de nuevo.")
    else:
        resp = composio_call("GOOGLESHEETS_ADD_SHEET", {
            "spreadsheet_id": SPREADSHEET_ID,
            "title": "Proyectos",
        })
        if not resp.get("successful"):
            print("Error creando la pestaña:", resp.get("error"))
            sys.exit(1)
        print("Pestaña 'Proyectos' creada.")

    resp = composio_call("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": SPREADSHEET_ID,
        "range": "Proyectos!A1:T1",
        "values": [HEADERS],
        "value_input_option": "USER_ENTERED",
    })
    print("Encabezados:", "OK" if resp.get("successful") else resp.get("error"))

    # Fila 2 de ejemplo: solo las columnas de fórmula (N:S), el resto lo llena
    # el usuario a mano al dar de alta un proyecto.
    resp = composio_call("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": SPREADSHEET_ID,
        "range": "Proyectos!N2:S2",
        "values": [FORMULAS_FILA2],
        "value_input_option": "USER_ENTERED",
    })
    print("Fórmulas fila 2:", "OK" if resp.get("successful") else resp.get("error"))


if __name__ == "__main__":
    main()
