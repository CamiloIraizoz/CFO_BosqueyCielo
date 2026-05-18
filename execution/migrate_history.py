#!/usr/bin/env python3
"""
Migra todos los datos históricos de las pestañas legadas a Movimientos.
Usa VALUES_UPDATE para escribir todo en una sola llamada.
Run: python3 execution/migrate_history.py
"""
import os, json, subprocess
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=False)

COMPOSIO       = os.path.expanduser("~/.composio/composio")
SID            = os.getenv("SPREADSHEET_ID")


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


# ── Filas de migración ─────────────────────────────────────────────────────────
# Formato: [Fecha, Mes, Año, Tipo, Categoría, Descripción, Cliente/Proveedor, Método, Monto]

ROWS = [
    # ─── STUDIO AMPHORA ───────────────────────────────────────────────────────
    ["01/12/2025","Diciembre","2025","Ingreso","Studio Amphora","Mensualidades Diciembre","Amphoras","Transferencia","3370000"],
    ["01/01/2026","Enero",   "2026","Ingreso","Studio Amphora","Mensualidades Enero",    "Amphoras","Transferencia","4200000"],
    ["01/02/2026","Febrero", "2026","Ingreso","Studio Amphora","Mensualidades Febrero",  "Amphoras","Transferencia","7320000"],
    ["01/03/2026","Marzo",   "2026","Ingreso","Studio Amphora","Mensualidades Marzo",    "Amphoras","Transferencia","6500000"],
    ["01/04/2026","Abril",   "2026","Ingreso","Studio Amphora","Mensualidades Abril",    "Amphoras","Transferencia","6500000"],
    ["01/05/2026","Mayo",    "2026","Ingreso","Studio Amphora","Mensualidades Mayo",     "Amphoras","Transferencia","2500000"],

    # ─── CERAMIKIDS ───────────────────────────────────────────────────────────
    ["01/01/2026","Enero",   "2026","Ingreso","Ceramikids","Mensualidades Enero",  "Niños Ceramikids","Transferencia","500000"],
    ["01/02/2026","Febrero", "2026","Ingreso","Ceramikids","Mensualidades Febrero","Niños Ceramikids","Transferencia","2151000"],
    ["01/03/2026","Marzo",   "2026","Ingreso","Ceramikids","Mensualidades Marzo",  "Niños Ceramikids","Transferencia","2151000"],
    ["01/04/2026","Abril",   "2026","Ingreso","Ceramikids","Mensualidades Abril",  "Niños Ceramikids","Transferencia","2151000"],

    # ─── POTTERY LAB ──────────────────────────────────────────────────────────
    ["12/12/2025","Diciembre","2025","Ingreso","Pottery Lab","Taller corporativo Opticare",   "Opticare",        "Transferencia","780000"],
    ["01/02/2026","Febrero",  "2026","Ingreso","Pottery Lab","Talleres Febrero",              "Varios clientes", "Transferencia","2290000"],
    ["01/03/2026","Marzo",    "2026","Ingreso","Pottery Lab","Talleres Marzo",                "Varios clientes", "Transferencia","2288000"],
    ["01/04/2026","Abril",    "2026","Ingreso","Pottery Lab","Talleres Abril + Adelanto Antoninas","Varios clientes","Transferencia","3383230"],
    ["09/05/2026","Mayo",     "2026","Ingreso","Pottery Lab","Taller Antonia Chavarro",       "Antonia Chavarro","Transferencia","840000"],

    # ─── SHOP (tienda física) ─────────────────────────────────────────────────
    ["01/12/2025","Diciembre","2025","Ingreso","Shop","Ventas tienda Diciembre","Clientes tienda","Efectivo","1630000"],
    ["01/01/2026","Enero",   "2026","Ingreso","Shop","Ventas tienda Enero",    "Clientes tienda","Efectivo","756019"],
    ["01/02/2026","Febrero", "2026","Ingreso","Shop","Ventas tienda Febrero",  "Clientes tienda","Efectivo","450000"],
    ["01/03/2026","Marzo",   "2026","Ingreso","Shop","Ventas tienda Marzo",    "Clientes tienda","Efectivo","1713779"],
    ["20/03/2026","Marzo",   "2026","Ingreso","Shop","Season Market (evento)",  "Clientes evento","Efectivo","1920000"],
    ["01/04/2026","Abril",   "2026","Ingreso","Shop","Ventas tienda Abril",    "Clientes tienda","Efectivo","345000"],
    ["01/05/2026","Mayo",    "2026","Ingreso","Shop","Ventas tienda Mayo",     "Clientes tienda","Efectivo","520000"],

    # ─── B2B ──────────────────────────────────────────────────────────────────
    ["13/03/2026","Marzo","2026","Ingreso","B2B","Jarrones Proyecto Padova","PADOVA",           "Transferencia","3819057"],
    ["18/03/2026","Marzo","2026","Ingreso","B2B","Mugs y Platos corporativo","Natalia Rodriguez","Transferencia","2000000"],

    # ─── PERSONALIZACIÓN ──────────────────────────────────────────────────────
    ["13/05/2026","Mayo","2026","Ingreso","Personalización","Pedido especial","Isabella Spataro","Transferencia","1000000"],

    # ─── KINTSUGI ─────────────────────────────────────────────────────────────
    ["01/02/2026","Febrero","2026","Ingreso","Kintsugi","Taller Kintsugi (8 participantes)","Varios clientes","Efectivo","1440000"],

    # ─── MATERIA PRIMA ────────────────────────────────────────────────────────
    ["01/12/2025","Diciembre","2025","Egreso","Materia Prima","Compras Diciembre","Bitacora / Ceramicas Olave","Transferencia","417000"],
    ["01/01/2026","Enero",   "2026","Egreso","Materia Prima","Compras Enero",    "Bitacora / Fragancias Nelsy","Transferencia","320000"],
    ["01/02/2026","Febrero", "2026","Egreso","Materia Prima","Compras Febrero",  "Bitacora / Ceramicas Olave","Transferencia","926650"],
    ["01/03/2026","Marzo",   "2026","Egreso","Materia Prima","Compras Marzo",    "Jorge Perez / Bitacora / Minelaes","Transferencia","2216917"],
    ["01/04/2026","Abril",   "2026","Egreso","Materia Prima","Compras Abril",    "Bitacora / Don Marino","Transferencia","3067176"],
    ["09/05/2026","Mayo",    "2026","Egreso","Materia Prima","Compras Mayo",     "Jorge Perez / Bogotá","Transferencia","304600"],

    # ─── MANO DE OBRA ─────────────────────────────────────────────────────────
    ["01/01/2026","Enero",   "2026","Egreso","Mano de Obra","Pagos Enero",    "Jessica / Don Jair",           "Efectivo",    "300000"],
    ["01/02/2026","Febrero", "2026","Egreso","Mano de Obra","Pagos Febrero",  "Jessica / Andrea Ceramikids",  "Transferencia","1260000"],
    ["14/03/2026","Marzo",   "2026","Egreso","Mano de Obra","Pagos Marzo",    "Jessica / Andrea / Don Jair",  "Transferencia","3310000"],
    ["20/04/2026","Abril",   "2026","Egreso","Mano de Obra","Pagos Abril",    "Jessica / Andrea / Don Jair",  "Transferencia","3054000"],
    ["12/05/2026","Mayo",    "2026","Egreso","Mano de Obra","Bono Daniela",   "Daniela Sandoval",             "Transferencia","1500000"],

    # ─── GASTOS OPERATIVOS → categorizados ────────────────────────────────────
    # Diciembre
    ["15/12/2025","Diciembre","2025","Egreso","Servicios Admin","Agua","Jarron de agua","Efectivo","40000"],

    # Enero
    ["01/01/2026","Enero","2026","Egreso","Servicios Admin","Trasteo y consumibles Enero","Varios","Efectivo","246400"],

    # Febrero
    ["09/02/2026","Febrero","2026","Egreso","Costos Indirectos","Instalación Hornos","Taller","Transferencia","232050"],
    ["12/02/2026","Febrero","2026","Egreso","Eventos",         "Invitación Pisco Amphorita","Pisco Amphorita","Efectivo","144360"],
    ["01/02/2026","Febrero","2026","Egreso","Servicios Admin", "Agua, café, consumibles","Varios","Efectivo","145380"],

    # Marzo
    ["04/03/2026","Marzo","2026","Egreso","Eventos",          "Season Market (costo evento)","Season Market / Carulla","Efectivo","2215885"],
    ["06/03/2026","Marzo","2026","Egreso","Publicidad",        "Aviso letrero Bosque y Cielo","Sebastian Arenas","Transferencia","750000"],
    ["04/03/2026","Marzo","2026","Egreso","Envíos",            "Domicilios y envíos Marzo","Uber / Correo","Efectivo","140104"],
    ["04/03/2026","Marzo","2026","Egreso","Costos Indirectos", "Paño de Torno","Angelik","Efectivo","28000"],
    ["24/03/2026","Marzo","2026","Egreso","Servicios Admin",   "Mercado oficina Marzo","Merca Mio","Efectivo","28850"],

    # Abril
    ["10/04/2026","Abril","2026","Egreso","Eventos",          "Happy Bazar + Pizza & Ceramica (vinos)","Happy Bazar / Dislicores","Efectivo","1086779"],
    ["20/04/2026","Abril","2026","Egreso","Envíos",            "Envío Manizales","Correo","Efectivo","20000"],
    ["20/04/2026","Abril","2026","Egreso","Servicios Admin",   "Suministros, parqueadero, consumibles","Varios","Efectivo","267700"],
    ["20/04/2026","Abril","2026","Egreso","Impuesto de Renta", "Abono IVA DIAN","DIAN","Transferencia","1000000"],

    # Gastos registrados con fecha 20/4 (pizza evento + horno)
    ["20/04/2026","Abril","2026","Egreso","Eventos",           "Pizza y Vino - costo pizzas","Santiago Vergez","Transferencia","318000"],
    ["20/04/2026","Abril","2026","Egreso","Costos Indirectos", "Arreglo y movimiento horno","Santiago Vergez / Taller","Transferencia","840000"],
    ["20/04/2026","Abril","2026","Egreso","Envíos",            "Domicilio evento pizza","Santiago Vergez","Efectivo","100000"],
]


def main():
    print(f"Filas a migrar: {len(ROWS)}")

    # Determinar la primera fila vacía en Movimientos
    # Header = fila 1, Shopify orders = filas 2-15 (14 rows), empezar en 16
    START_ROW = 16
    end_row   = START_ROW + len(ROWS) - 1
    rango     = f"Movimientos!A{START_ROW}:I{end_row}"

    print(f"Escribiendo en {rango}...")
    resp = call("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": SID,
        "range": rango,
        "values": ROWS,
        "value_input_option": "USER_ENTERED"
    })

    if resp.get("successful"):
        print(f"✅ {len(ROWS)} filas migradas a Movimientos (filas {START_ROW}-{end_row}).")
    else:
        print(f"❌ Error: {resp.get('error', 'desconocido')}")


if __name__ == "__main__":
    main()
