"""Registrar plata en el libro contable, atribuida a un proyecto.

La pestaña `Movimientos` ya existía y es el libro de toda la empresa. Tiene una
columna **Proyecto** (K) que casi nunca se llenaba, así que era imposible saber
qué dejó cada pedido.

Este módulo escribe ahí, con esa columna puesta. Un solo registro sirve para
dos cosas: el PNL del mes (por categoría) y el PNL del proyecto (`proyectos.py`).
No hay segundo libro ni doble digitación.
"""

from datetime import datetime

from sheets import agregar_fila, leer_sheet_numericos

PESTANA = "Movimientos"

MESES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
         7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre",
         11: "Noviembre", 12: "Diciembre"}

TIPOS = ("ingreso", "egreso")


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", ".") or 0)
    except (TypeError, ValueError):
        return 0.0


def _pesos(n):
    return f"${int(round(n)):,}".replace(",", ".")


def _partes_fecha(fecha):
    try:
        d = datetime.strptime(str(fecha).strip(), "%d/%m/%Y")
    except ValueError:
        d = datetime.now()
    return d.strftime("%d/%m/%Y"), MESES[d.month], str(d.year)


def registrar(tipo, monto, concepto, proyecto="", categoria="", fecha="",
              forma_pago="", cliente="", notas=""):
    """Una fila en Movimientos, con el proyecto puesto."""
    tipo = str(tipo or "").strip().lower()
    if tipo not in TIPOS:
        return "❌ El tipo tiene que ser 'ingreso' o 'egreso'."
    monto = _num(monto)
    if monto <= 0:
        return "❌ Falta el monto."
    if not str(concepto or "").strip():
        return "❌ Falta el concepto: qué se compró o de qué es el ingreso."

    # La cabecera tiene que estar: si no, la hoja no es la que creemos.
    if not leer_sheet_numericos(f"{PESTANA}!A1:K1"):
        return f"❌ No pude leer la pestaña {PESTANA}. No escribí nada."

    f, mes, anio = _partes_fecha(fecha)
    fila = [f, mes, anio, "Ingreso" if tipo == "ingreso" else "Egreso",
            categoria or ("Ecommerce" if tipo == "ingreso" else "Otros"),
            concepto, cliente, forma_pago, int(monto), "", proyecto]
    r = agregar_fila(f"{PESTANA}!A:K", fila)
    if str(r).startswith(("Error", "❌")):
        return "❌ No quedó registrado: " + str(r).replace("Error: ", "", 1)

    signo = "+" if tipo == "ingreso" else "−"
    salida = [f"✅ {signo}{_pesos(monto)} · {concepto}"]
    if proyecto:
        from proyectos import cifras
        ing, _, eg = cifras(proyecto)
        salida.append(f"   Proyecto *{proyecto}*: {_pesos(ing)} cobrado · "
                      f"{_pesos(eg)} gastado → {_pesos(ing - eg)}")
    else:
        salida.append("   ⚠️ Sin proyecto: no va a aparecer en ningún PNL de proyecto. "
                      "Si pertenece a uno, dime cuál y lo corrijo.")
    return "\n".join(salida)


def leer(proyecto="", limite=25):
    """Los últimos movimientos, de un proyecto o de todos."""
    filas = leer_sheet_numericos(f"{PESTANA}!A2:K5000")
    clave = str(proyecto or "").strip().lower()
    vivos = []
    for f in filas:
        if not f or len(f) < 9:
            continue
        suyo = str(f[10]).strip().lower() if len(f) > 10 else ""
        if clave and clave not in suyo:
            continue
        vivos.append(f)
    if not vivos:
        cual = f" del proyecto {proyecto}" if proyecto else ""
        return f"No hay movimientos registrados{cual}."

    lineas = [f"*Movimientos{' · ' + proyecto if proyecto else ''}*", ""]
    ing = eg = 0.0
    for f in vivos[-int(limite):]:
        monto = _num(f[8])
        entra = str(f[3]).strip().lower().startswith("ingreso")
        destino = "" if clave else (f" · {f[10]}" if len(f) > 10 and str(f[10]).strip() else "")
        lineas.append(f"· {f[0]} {'+' if entra else '−'}{_pesos(monto)} · {f[5]}{destino}")
    for f in vivos:
        monto = _num(f[8])
        if str(f[3]).strip().lower().startswith("ingreso"):
            ing += monto
        else:
            eg += monto
    lineas.append("")
    lineas.append(f"Total: {_pesos(ing)} cobrado · {_pesos(eg)} gastado "
                  f"→ {_pesos(ing - eg)}.")
    return "\n".join(lineas)
