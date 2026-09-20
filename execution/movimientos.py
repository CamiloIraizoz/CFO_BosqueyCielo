"""Plata que entra y sale de un pedido concreto.

Las pestañas de ingresos y egresos del Sheet están organizadas por línea de
negocio (Shop, B2B, Pottery Lab…) y por categoría de gasto (Materia Prima,
Mano de Obra…). Sirven para el PNL, pero **ninguna dice a qué pedido
pertenece la plata**, así que hoy es imposible responder "¿cuánto me dejó
realmente el pedido de Camilo Rojas?".

Esta pestaña es esa dimensión que falta: un libro por pedido. No reemplaza a
las otras — el PNL se sigue armando allá — y por eso cada movimiento guarda
también a qué pestaña de PNL corresponde, para poder cuadrarlos después.
"""

from datetime import datetime

from sheets import agregar_fila, crear_pestana, escribir_rango, leer_sheet_numericos

PESTANA = "Movimientos"
CABECERA = ["Fecha", "Tipo", "Pedido", "Categoría", "Concepto", "Monto",
            "Forma de pago", "Pestaña PNL", "Notas"]

TIPOS = ("ingreso", "egreso")


def _asegurar_pestana():
    if leer_sheet_numericos(f"'{PESTANA}'!A1:I1"):
        return ""
    r = crear_pestana(PESTANA)
    if str(r).startswith(("Error", "❌")):
        return str(r)
    escribir_rango(f"'{PESTANA}'!A1:I1", [CABECERA])
    return ""


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _pesos(n):
    return f"${int(round(n)):,}".replace(",", ".")


def registrar(tipo, monto, concepto, pedido="", categoria="", fecha="",
              forma_pago="", pestana_pnl="", notas=""):
    tipo = str(tipo or "").strip().lower()
    if tipo not in TIPOS:
        return "❌ El tipo tiene que ser 'ingreso' o 'egreso'."
    monto = _num(monto)
    if monto <= 0:
        return "❌ Falta el monto."
    if not str(pedido or "").strip():
        return ("❌ Falta a qué pedido pertenece. Si el movimiento no es de un pedido "
                "puntual (arriendo, servicios, nómina), va en su pestaña de siempre "
                "con agregar_fila, no acá.")

    fallo = _asegurar_pestana()
    if fallo:
        return "❌ No pude crear la pestaña Movimientos: " + fallo

    fila = [fecha or datetime.now().strftime("%d/%m/%Y"), tipo, pedido, categoria,
            concepto, int(monto), forma_pago, pestana_pnl, notas]
    r = agregar_fila(f"'{PESTANA}'!A:I", fila)
    if str(r).startswith(("Error", "❌")):
        return "❌ No quedó registrado: " + str(r).replace("Error: ", "", 1)

    signo = "+" if tipo == "ingreso" else "−"
    salida = [f"✅ {signo}{_pesos(monto)} · {concepto} · pedido {pedido}"]
    salida.append("   " + resumen_pedido(pedido, breve=True))
    if not pestana_pnl:
        salida.append("   ⚠️ Recuerda registrarlo también en su pestaña del PNL "
                      "(ver Directivas/registrar_transacciones.md).")
    return "\n".join(salida)


def _filas(pedido=""):
    filas = [f for f in leer_sheet_numericos(f"'{PESTANA}'!A2:I1000") if f and len(f) >= 6]
    if pedido:
        clave = pedido.strip().lower()
        filas = [f for f in filas if clave in str(f[2]).strip().lower()]
    return filas


def _totales(pedido):
    ingresos = egresos = 0.0
    for f in _filas(pedido):
        monto = _num(f[5])
        if str(f[1]).strip().lower() == "ingreso":
            ingresos += monto
        else:
            egresos += monto
    return ingresos, egresos


def _cotizado(pedido):
    """Lo que se le cotizó a ese cliente, para contrastarlo con lo real."""
    try:
        from registro_cotizaciones import PESTANA as P_COT
        clave = pedido.strip().lower()
        for f in leer_sheet_numericos(f"'{P_COT}'!A2:L500"):
            if not f or len(f) < 8:
                continue
            quien = f"{f[3]} {f[4]}".strip().lower()
            if clave in quien or quien in clave:
                return _num(f[7]), str(f[0]).strip()
    except Exception:
        pass
    return 0.0, ""


def resumen_pedido(pedido, breve=False):
    ingresos, egresos = _totales(pedido)
    neto = ingresos - egresos
    if breve:
        return (f"Va en {_pesos(ingresos)} cobrado y {_pesos(egresos)} gastado "
                f"→ {_pesos(neto)}.")

    cot, numero = _cotizado(pedido)
    lineas = [f"*Pedido: {pedido}*", ""]
    if cot:
        falta = cot - ingresos
        lineas.append(f"Cotizado ({numero}): {_pesos(cot)}")
        lineas.append(f"Cobrado: {_pesos(ingresos)}" +
                      (f" · falta cobrar {_pesos(falta)}" if falta > 0 else " · cobrado completo"))
    else:
        lineas.append(f"Cobrado: {_pesos(ingresos)}")
    lineas.append(f"Gastado: {_pesos(egresos)}")
    lineas.append(f"*Neto: {_pesos(neto)}*")
    if ingresos > 0:
        lineas.append(f"Margen sobre lo cobrado: {round(neto / ingresos * 100, 1)}%")
    if cot and egresos > 0:
        lineas.append(f"Margen sobre lo cotizado: {round((cot - egresos) / cot * 100, 1)}%")
    return "\n".join(lineas)


def leer(pedido="", limite=25):
    filas = _filas(pedido)
    if not filas:
        cual = f" del pedido {pedido}" if pedido else ""
        return f"No hay movimientos registrados{cual}."
    lineas = [f"*Movimientos{' · ' + pedido if pedido else ''}*", ""]
    for f in filas[-int(limite):]:
        signo = "+" if str(f[1]).strip().lower() == "ingreso" else "−"
        destino = "" if pedido else f" · {f[2]}"
        lineas.append(f"· {f[0]} {signo}{_pesos(_num(f[5]))} · {f[4]}{destino}")
    lineas.append("")
    if pedido:
        lineas.append(resumen_pedido(pedido, breve=True))
    else:
        ing, egr = _totales("")
        lineas.append(f"Total: {_pesos(ing)} cobrado · {_pesos(egr)} gastado "
                      f"→ {_pesos(ing - egr)}.")
    return "\n".join(lineas)
