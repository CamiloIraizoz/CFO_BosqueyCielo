#!/usr/bin/env python3
"""
Builds the 'Resumen' PnL tab from scratch with full P&L structure.
Run once: python3 execution/setup_resumen.py
"""
import os
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=False)

COMPOSIO       = os.path.expanduser("~/.composio/composio")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
MONTH_COLS = ["B","C","D","E","F","G","H","I","J","K","L","M"]


def call(tool, data):
    r = subprocess.run(
        [COMPOSIO, "execute", tool, "-d", json.dumps(data)],
        capture_output=True, text=True, timeout=60
    )
    out = "\n".join(l for l in r.stdout.splitlines()
                    if "Update available" not in l and "composio upgrade" not in l).strip()
    try:
        return json.loads(out)
    except Exception:
        return {"successful": False, "error": r.stderr or out}


def si(col, cat, tipo):
    return (f'=SUMIFS(Movimientos!$I:$I,'
            f'Movimientos!$B:$B,{col}$1,'
            f'Movimientos!$D:$D,"{tipo}",'
            f'Movimientos!$E:$E,"{cat}")')


def otros(col):
    return (f'=SUMIFS(Movimientos!$I:$I,Movimientos!$B:$B,{col}$1,'
            f'Movimientos!$D:$D,"Ingreso",Movimientos!$E:$E,"Kintsugi")'
            f'+SUMIFS(Movimientos!$I:$I,Movimientos!$B:$B,{col}$1,'
            f'Movimientos!$D:$D,"Ingreso",Movimientos!$E:$E,"Otros Ingresos")')


def pct(col, num_row, den_row):
    return f'=IF({col}{den_row}<>0,{col}{num_row}/{col}{den_row},0)'


def srow(row):
    return f"=SUM(B{row}:M{row})"


def build_grid():
    grid = []

    # R1: Header
    grid.append(["PnL Ordenado 2026"] + MESES + ["TOTAL"])

    # R2: Section header
    grid.append(["INGRESOS OPERACIONALES"] + [""]*13)

    # R3-R9: Income categories (7 rows)
    for label, cat in [
        ("Ecommerce",     "Ecommerce"),
        ("Pottery Lab",   "Pottery Lab"),
        ("Studio Amphora","Studio Amphora"),
        ("Ceramikids",    "Ceramikids"),
        ("Personalización","Personalización"),
        ("Shop",          "Shop"),
        ("B2B",           "B2B"),
    ]:
        r = len(grid) + 1
        grid.append([label] + [si(c, cat, "Ingreso") for c in MONTH_COLS] + [srow(r)])

    # R10: Otros (Kintsugi + Otros Ingresos)
    r10 = len(grid) + 1  # == 10
    grid.append(["Otros"] + [otros(c) for c in MONTH_COLS] + [srow(r10)])

    # R11: Ventas Brutas
    r11 = len(grid) + 1  # == 11
    grid.append(["Ventas Brutas"] + [f"=SUM({c}3:{c}10)" for c in MONTH_COLS] + [srow(r11)])

    # R12: Devoluciones
    r12 = len(grid) + 1  # == 12
    grid.append(["(-) Devoluciones y Descuentos"] + [si(c, "Devoluciones", "Egreso") for c in MONTH_COLS] + [srow(r12)])

    # R13: VENTAS NETAS
    grid.append(["(=) VENTAS NETAS"] + [f"={c}11-{c}12" for c in MONTH_COLS] + ["=N11-N12"])

    # R14: blank
    grid.append([""]*14)

    # R15: Section header
    grid.append(["COSTOS DE VENTAS (PRODUCCIÓN)"] + [""]*13)

    # R16-R18: Cost of goods (3 rows)
    for label, cat in [
        ("Materia Prima Directa",            "Materia Prima"),
        ("Mano de Obra Directa",             "Mano de Obra"),
        ("Costos Indirectos de Producción",  "Costos Indirectos"),
    ]:
        r = len(grid) + 1
        grid.append([label] + [si(c, cat, "Egreso") for c in MONTH_COLS] + [srow(r)])

    # R19: UTILIDAD BRUTA
    grid.append(["(=) UTILIDAD BRUTA"] + [f"={c}13-SUM({c}16:{c}18)" for c in MONTH_COLS] + ["=N13-SUM(N16:N18)"])

    # R20: MARGEN BRUTO %
    r20 = len(grid) + 1  # == 20
    grid.append(["MARGEN BRUTO"] + [pct(c, 19, 13) for c in MONTH_COLS] + [pct("N", 19, 13)])

    # R21: blank
    grid.append([""]*14)

    # R22: Section header
    grid.append(["GASTOS DE VENTA"] + [""]*13)

    # R23-R29: Sales expenses (7 rows)
    for label, cat in [
        ("Manejo de redes",                   "Redes Sociales"),
        ("Publicidad y pauta",                "Publicidad"),
        ("Eventos y activaciones",            "Eventos"),
        ("Envíos y domicilios",               "Envíos"),
        ("Comisiones de pasarela / datáfono","Comisiones Pasarela"),
        ("Shopify",                           "Fee Shopify"),
        ("Empaques comerciales",              "Empaques"),
    ]:
        r = len(grid) + 1
        grid.append([label] + [si(c, cat, "Egreso") for c in MONTH_COLS] + [srow(r)])

    # R30: Total Gastos de Venta
    grid.append(["Total Gastos de Venta"] + [f"=SUM({c}23:{c}29)" for c in MONTH_COLS] + ["=SUM(N23:N29)"])

    # R31: blank
    grid.append([""]*14)

    # R32: Section header
    grid.append(["GASTOS ADMINISTRATIVOS"] + [""]*13)

    # R33-R37: Admin expenses (5 rows)
    for label, cat in [
        ("Arriendo",                              "Arriendo"),
        ("Salario gerente",                       "Salario Gerente"),
        ("Aportes seguridad social",              "Aportes"),
        ("Contadora",                             "Contadora"),
        ("Internet, servicios y varios admin",    "Servicios Admin"),
    ]:
        r = len(grid) + 1
        grid.append([label] + [si(c, cat, "Egreso") for c in MONTH_COLS] + [srow(r)])

    # R38: Total Gastos Admin
    grid.append(["Total Gastos Administrativos"] + [f"=SUM({c}33:{c}37)" for c in MONTH_COLS] + ["=SUM(N33:N37)"])

    # R39: UTILIDAD OPERACIONAL (EBIT)
    grid.append(["(=) UTILIDAD OPERACIONAL (EBIT)"] + [f"={c}19-{c}30-{c}38" for c in MONTH_COLS] + ["=N19-N30-N38"])

    # R40: MARGEN OPERACIONAL %
    grid.append(["MARGEN OPERACIONAL"] + [pct(c, 39, 13) for c in MONTH_COLS] + [pct("N", 39, 13)])

    # R41: blank
    grid.append([""]*14)

    # R42: Section header
    grid.append(["RESULTADO FINANCIERO"] + [""]*13)

    # R43: Ingresos Financieros
    r43 = len(grid) + 1  # == 43
    grid.append(["Ingresos Financieros"] + [si(c, "Ingresos Financieros", "Ingreso") for c in MONTH_COLS] + [srow(r43)])

    # R44: Gastos Financieros
    r44 = len(grid) + 1  # == 44
    grid.append(["Gastos Financieros"] + [si(c, "Gastos Financieros", "Egreso") for c in MONTH_COLS] + [srow(r44)])

    # R45: UTILIDAD ANTES DE IMPUESTOS
    grid.append(["(=) UTILIDAD ANTES DE IMPUESTOS"] + [f"={c}39+{c}43-{c}44" for c in MONTH_COLS] + ["=N39+N43-N44"])

    # R46: blank
    grid.append([""]*14)

    # R47: Section header
    grid.append(["IMPUESTOS Y CIERRE"] + [""]*13)

    # R48: Provisión Impuesto de Renta
    r48 = len(grid) + 1  # == 48
    grid.append(["Provisión Impuesto de Renta"] + [si(c, "Impuesto de Renta", "Egreso") for c in MONTH_COLS] + [srow(r48)])

    # R49: UTILIDAD NETA
    grid.append(["(=) UTILIDAD NETA"] + [f"={c}45-{c}48" for c in MONTH_COLS] + ["=N45-N48"])

    # R50: MARGEN NETO %
    grid.append(["MARGEN NETO"] + [pct(c, 49, 13) for c in MONTH_COLS] + [pct("N", 49, 13)])

    return grid


def main():
    print("Construyendo Resumen PnL...")
    grid = build_grid()
    print(f"  Filas generadas: {len(grid)}")
    assert len(grid) == 50, f"Expected 50 rows, got {len(grid)}"

    resp = call("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": SPREADSHEET_ID,
        "range": "Resumen!A1:N50",
        "values": grid,
        "value_input_option": "USER_ENTERED"
    })

    if resp.get("successful"):
        print("✅ Resumen construido. Formatear filas 20, 40, 50 como % en Sheets.")
    else:
        print(f"❌ Error: {resp.get('error', 'desconocido')}")


if __name__ == "__main__":
    main()
