#!/usr/bin/env python3
"""
Conciliación bancaria mensual — Amphora B&C
Cruza el CSV de Bancolombia con la pestaña Movimientos del Sheet.

Genera pestaña "Conciliación MES YYYY" con TODOS los movimientos bancarios:
  ✅ En Movimientos = ya está registrado
  ⚠️ Pendiente     = falta registrar (con sugerencia de categoría/pestaña)

Uso:
    python3 execution/conciliacion_bancaria.py <archivo.csv> [--mes "Mayo 2026"]
"""
import sys
from pathlib import Path
from collections import Counter
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

sys.path.insert(0, str(Path(__file__).parent))
from sheets import crear_pestana, escribir_rango, leer_sheet_numericos

# ── Patrones de clasificación ─────────────────────────────────────────────────
# (substring_descripcion_upper, categoria, pestaña_sheet, concepto)
# Se aplica en orden; gana el primero que hace match.

PATRONES = [
    ("BOLD.CO",                "INGRESO", "Shop",              "Ventas POS Bold"),
    ("PAGO INTERBANC",         "INGRESO", "Clientes",          "Pago cliente transferencia"),
    ("PAGO DE PROV WOMPI",     "INGRESO", "Ecommerce",         "Pago Wompi"),
    ("WOMPI",                  "INGRESO", "Ecommerce",         "Ventas online Wompi"),
    ("PAGO LLAVE",             "INGRESO", "Clientes",          "Pago cliente Nequi/Llave"),
    ("ABONO INTERESES",        "INGRESO", "Gastos Operativos", "Intereses ahorros"),
    ("AJUSTE INTERES",         "EGRESO",  "Gastos Operativos", "Ajuste intereses banco"),
    ("SHOPIFY",                "EGRESO",  "Gastos Operativos", "Suscripción Shopify"),
    ("FACEBK",                 "EGRESO",  "Gastos Operativos", "Facebook Ads"),
    ("FACEBOOK",               "EGRESO",  "Gastos Operativos", "Facebook Ads"),
    ("COMCEL",                 "EGRESO",  "Gastos Operativos", "Celular Comcel"),
    ("UBER",                   "EGRESO",  "Gastos Operativos", "Transporte Uber"),
    ("DOLLARCITY",             "EGRESO",  "Gastos Operativos", "Compra Dollarcity"),
    ("PAYU*SOLUC",             "EGRESO",  "Gastos Operativos", "Alegra (sistema contable)"),
    ("APORTES EN LINEA",       "EGRESO",  "Mano de Obra",      "PILA / Aportes nómina"),
    ("CARULLA",                "EGRESO",  "Gastos Operativos", "Compra Carulla"),
    ("ALMACEN SI",             "EGRESO",  "Gastos Operativos", "Compra Almacén"),
    ("CENTRO COM",             "EGRESO",  "Gastos Operativos", "Compra Centro Comercial"),
    ("RETIRO CAJERO",          "EGRESO",  "Gastos Operativos", "Retiro cajero (efectivo)"),
    ("IMPTO GOBIERNO",         "EGRESO",  "Gastos Operativos", "Impuesto 4x1000"),
    ("4X1000",                 "EGRESO",  "Gastos Operativos", "Impuesto 4x1000"),
    ("COBRO IVA",              "EGRESO",  "Gastos Operativos", "IVA pagos automáticos"),
    ("C MANEJO TARJ",          "EGRESO",  "Gastos Operativos", "Cuota manejo tarjeta"),
    ("SERVICIO TRANSFERENCIA", "EGRESO",  "Gastos Operativos", "Comisión transferencia"),
]

# Patrones por monto exacto — aprendidos de los extractos; actualizar cada mes.
PATRONES_MONTO = {
    # Materia prima
    571200:    ("EGRESO",  "Materia Prima",     "Esmaltes Don Marino"),
    2270000:   ("EGRESO",  "Materia Prima",     "Bitácora (moldes y bizcochos)"),
    # Mano de obra
    5000000:   ("EGRESO",  "Mano de Obra",      "Salario Daniela (gerente)"),
    5500000:   ("EGRESO",  "Mano de Obra",      "Salario Daniela $5M + Meli con Miel $500K"),
    1500000:   ("EGRESO",  "Mano de Obra",      "Bono Daniela"),
    496600:    ("EGRESO",  "Mano de Obra",      "PILA / Aportes nómina"),
    500600:    ("EGRESO",  "Mano de Obra",      "PILA / Aportes nómina"),
    470000:    ("EGRESO",  "Mano de Obra",      "Sueldo Jessica Q1 (47h)"),
    # Gastos operativos
    2565000:   ("EGRESO",  "Gastos Operativos", "Redes sociales (gasto abril, pago mayo)"),
    2700000:   ("EGRESO",  "Gastos Operativos", "Arriendo (retiro cajero efectivo)"),
    108258.81: ("EGRESO",  "Gastos Operativos", "Suscripción Shopify"),
    # Ingresos identificados
    160067:    ("INGRESO", "Shop",              "Pago Bold POS"),
    158130.73: ("INGRESO", "Ecommerce",         "Pago Wompi"),
    84978.85:  ("INGRESO", "Ecommerce",         "Pago Wompi"),
    64908.55:  ("INGRESO", "Ecommerce",         "Pago Wompi"),
    63608.55:  ("INGRESO", "Ecommerce",         "Pago Wompi"),
    1343000:   ("INGRESO", "Clientes",          "Laura Ricci + Lori Ricci + Luca Ricci"),
    1090000:   ("INGRESO", "Clientes",          "Pago personalización"),
    716000:    ("INGRESO", "Clientes",          "Pago Juliana Ricci"),
    720000:    ("INGRESO", "Clientes",          "Pago Antonia Chavarro"),
}


def clasificar(descripcion: str, monto: float) -> tuple[str, str, str]:
    """Retorna (categoria, pestaña_sheet, concepto)."""
    desc_up = descripcion.upper()
    abs_m = round(abs(monto), 2)

    # Por monto exacto (verificando dirección del flujo)
    if abs_m in PATRONES_MONTO:
        cat, pestana, concepto = PATRONES_MONTO[abs_m]
        if (cat == "INGRESO" and monto > 0) or (cat == "EGRESO" and monto < 0):
            return cat, pestana, concepto

    # Por texto en descripción
    for substr, cat, pestana, concepto in PATRONES:
        if substr in desc_up:
            return cat, pestana, concepto

    # Por defecto según dirección
    if monto > 0:
        return "INGRESO", "", ""
    return "EGRESO", "", ""


def leer_csv(ruta: str) -> list[dict]:
    movimientos = []
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            partes = [p.strip() for p in linea.split(",")]
            if len(partes) < 8:
                continue
            try:
                fecha_raw = partes[3]
                monto = float(partes[5])
                descripcion = partes[7]
                fecha = f"{fecha_raw[6:8]}/{fecha_raw[4:6]}/{fecha_raw[:4]}"
                movimientos.append({
                    "fecha": fecha,
                    "descripcion": descripcion,
                    "monto": monto,
                })
            except (ValueError, IndexError):
                continue
    return movimientos


def leer_pool_movimientos() -> Counter:
    """Lee la pestaña Movimientos y retorna Counter de montos absolutos registrados."""
    filas = leer_sheet_numericos("Movimientos!A:Z")
    pool = Counter()
    for fila in filas[1:]:  # skip header
        for v in fila:
            if isinstance(v, (int, float)) and v > 0:
                pool[round(float(v), 2)] += 1
    return pool


def construir_tabla(movimientos: list[dict], pool: Counter) -> list[list]:
    encabezado = [
        "Fecha", "Descripción banco", "Monto",
        "Estado", "Categoría", "Pestaña Sheet", "Concepto", "Notas"
    ]
    filas = [encabezado]

    for m in movimientos:
        cat, pestana, concepto = clasificar(m["descripcion"], m["monto"])
        abs_m = round(abs(m["monto"]), 2)

        if pool[abs_m] > 0:
            estado = "✅ En Movimientos"
            pool[abs_m] -= 1
        else:
            estado = "⚠️ Pendiente"

        filas.append([
            m["fecha"],
            m["descripcion"],
            m["monto"],
            estado,
            cat,
            pestana,
            concepto,
            "",
        ])

    return filas


def imprimir_resumen(filas: list[list]) -> None:
    datos = filas[1:]
    cruzados  = [r for r in datos if "✅" in str(r[3])]
    pendientes = [r for r in datos if "⚠️" in str(r[3])]

    total_ing   = sum(r[2] for r in datos if r[2] > 0)
    total_egr   = sum(r[2] for r in datos if r[2] < 0)
    total_4x1000 = sum(r[2] for r in datos
                       if "IMPTO GOBIERNO" in r[1].upper() or "4X1000" in r[1].upper())
    total_int   = sum(r[2] for r in datos
                      if "INTERESES" in r[1].upper() or "AJUSTE INTERES" in r[1].upper())

    print(f"\n{'='*62}")
    print(f"  CONCILIACIÓN BANCARIA")
    print(f"{'='*62}")
    print(f"  Total movimientos banco   : {len(datos)}")
    print(f"  ✅ En Movimientos          : {len(cruzados)}")
    print(f"  ⚠️  Pendientes de registrar: {len(pendientes)}")
    print()
    print(f"  Ingresos banco            : ${total_ing:>14,.2f}")
    print(f"  Egresos banco             : ${total_egr:>14,.2f}")
    print(f"  Flujo neto                : ${total_ing + total_egr:>14,.2f}")
    print()
    print(f"  4x1000 (total mes)        : ${total_4x1000:>14,.2f}")
    print(f"  Intereses ahorros         : ${total_int:>14,.2f}")
    print()
    print(f"  ⚠️  PENDIENTES:")
    for r in pendientes:
        print(f"     {r[0]}  ${r[2]:>12,.0f}  {r[1][:38]:<38}  → {r[6] or '?'}")
    print(f"{'='*62}\n")


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 conciliacion_bancaria.py <archivo.csv> [--mes 'Mayo 2026']")
        sys.exit(1)

    archivo = sys.argv[1]
    mes = "Mayo 2026"
    if "--mes" in sys.argv:
        idx = sys.argv.index("--mes")
        mes = sys.argv[idx + 1]

    nombre_pestana = f"Conciliación {mes}"

    print(f"Leyendo CSV: {archivo}...")
    movimientos = leer_csv(archivo)
    print(f"  {len(movimientos)} movimientos bancarios.")

    print("Leyendo pestaña Movimientos del Sheet...")
    pool = leer_pool_movimientos()
    print(f"  {sum(pool.values())} valores numéricos en Movimientos.")

    filas = construir_tabla(movimientos, pool)
    imprimir_resumen(filas)

    print(f"Creando/actualizando pestaña '{nombre_pestana}'...")
    print(crear_pestana(nombre_pestana))

    print("Escribiendo tabla de conciliación...")
    print(escribir_rango(f"'{nombre_pestana}'!A1", filas))
    print("Listo.")


if __name__ == "__main__":
    main()
