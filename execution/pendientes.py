"""Pendientes del taller: lo que hay que hacer y todavía no se hizo.

Vivían en el tablero de la página; desde el 2026-09-20 producción tiene una
sola casa (el Sheet + Telegram) y estos vinieron con ella.
"""

from datetime import datetime

from sheets import agregar_fila, actualizar_celda, crear_pestana, escribir_rango, \
    leer_sheet_numericos

PESTANA = "Pendientes"
CABECERA = ["#", "Fecha", "Pedido", "Pendiente", "Para quién", "Estado", "Cerrado"]


def _asegurar_pestana():
    filas = leer_sheet_numericos(f"'{PESTANA}'!A1:G1")
    if filas and filas[0]:
        return
    crear_pestana(PESTANA)
    escribir_rango(f"'{PESTANA}'!A1:G1", [CABECERA])


def _filas():
    return [f for f in leer_sheet_numericos(f"'{PESTANA}'!A2:G500") if f and len(f) >= 4]


def _estado(fila):
    return (str(fila[5]).strip().lower() if len(fila) > 5 else "") or "abierto"


def agregar(texto, pedido="", quien=""):
    if not str(texto or "").strip():
        return "❌ Falta qué es el pendiente."
    _asegurar_pestana()
    num = len(_filas()) + 1
    fila = [num, datetime.now().strftime("%d/%m/%Y"), pedido, texto.strip(), quien, "abierto", ""]
    r = agregar_fila(f"'{PESTANA}'!A:G", fila)
    if str(r).startswith(("Error", "❌")):
        return r
    destino = f" ({pedido})" if pedido else ""
    de = f" — {quien}" if quien else ""
    return f"✅ Pendiente #{num}{destino}: {texto.strip()}{de}"


def leer(pedido="", incluir_cerrados=False):
    filas = _filas()
    if not filas:
        return "No hay pendientes anotados."
    vivos = []
    for f in filas:
        if not incluir_cerrados and _estado(f) != "abierto":
            continue
        if pedido and pedido.strip().lower() not in str(f[2]).strip().lower():
            continue
        vivos.append(f)
    if not vivos:
        cual = f" de {pedido}" if pedido else ""
        return f"Sin pendientes abiertos{cual}. 🎉"

    lineas = ["*Pendientes abiertos*", ""]
    for f in vivos:
        marca = "·" if _estado(f) == "abierto" else "✅"
        destino = f" — {f[2]}" if str(f[2]).strip() else ""
        quien = f" ({f[4]})" if len(f) > 4 and str(f[4]).strip() else ""
        lineas.append(f"{marca} #{f[0]} {f[3]}{destino}{quien}")
    return "\n".join(lineas)


def cerrar(referencia):
    """Cierra por número (#3) o por un pedazo del texto."""
    ref = str(referencia or "").strip().lstrip("#").lower()
    if not ref:
        return "❌ Dime cuál pendiente cerrar: el número o parte del texto."
    for i, f in enumerate(_filas(), start=2):
        if _estado(f) != "abierto":
            continue
        if str(f[0]).strip() == ref or ref in str(f[3]).strip().lower():
            actualizar_celda(f"'{PESTANA}'!F{i}", "cerrado")
            actualizar_celda(f"'{PESTANA}'!G{i}", datetime.now().strftime("%d/%m/%Y"))
            return f"✅ Cerrado #{f[0]}: {f[3]}"
    return f"No encontré un pendiente abierto que coincida con '{referencia}'."
