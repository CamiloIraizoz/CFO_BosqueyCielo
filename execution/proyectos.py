"""Proyectos y su mini PNL.

Bosque y Cielo vende por tres líneas y cada una se comporta distinto:

  · **personalizacion** — pedidos a la medida para una persona o empresa.
  · **b2b**             — volumen para otro negocio que revende.
  · **coleccion**       — la colección propia, que se vende en tienda y online.

Un proyecto pertenece a una línea. Su PNL sale de la pestaña `Movimientos`
—el libro contable de siempre— filtrando por la columna **Proyecto**. No hay
un segundo libro: lo que se registra una vez sirve para el PNL del mes y para
el del proyecto.

El PNL tiene la misma estructura que el del mes (`setup_resumen.py`) y usa las
mismas categorías de Movimientos:

  Ingresos − costo de ventas            = utilidad bruta
           − gastos directos de venta   = CONTRIBUCIÓN (lo que el proyecto cubre solo)
           − gastos compartidos         = UTILIDAD OPERACIONAL

Los gastos compartidos son los egresos del mes que no tienen proyecto (taller,
mercadeo de marca, arriendo, gerencia, servicios). Se reparten **cada mes según
las ventas**: si el proyecto cobró el 10% de lo que entró a la empresa ese mes,
carga el 10% de esos gastos. Es el criterio sencillo que eligió Camilo el
2026-09-24; el otro (por pieza, como el cotizador) exige contar piezas.

Todo queda también en la pestaña **PNL Proyectos**, un proyecto por columna.
"""

import re
from datetime import datetime

from sheets import agregar_fila, crear_pestana, escribir_rango, formatear, id_pestana, \
    leer_sheet_numericos, limpiar_rango, renombrar_pestana

PESTANA = "Proyectos"
MOVIMIENTOS = "Movimientos"
COL_PROYECTO = "K"        # la columna Proyecto dentro de Movimientos

CABECERA = ["Proyecto", "Línea", "Cliente", "Estado", "Inicio", "Cierre",
            "Cotización", "Notas"]

LINEAS = {
    "personalizacion": "Personalización",
    "b2b":             "B2B",
    "coleccion":       "Colección propia",
}

# Cómo se agrupan los egresos en el PNL. El primero que coincida manda.
GRUPOS = [
    ("Materia prima",        ["materia prima", "bizcocho", "arcilla", "esmalte",
                              "vinilo", "transfer", "empaque", "insumo"]),
    ("Mano de obra",         ["mano de obra", "nomina", "nómina", "honorario",
                              "taller", "jornal"]),
    ("Producción indirecta", ["horno", "energia", "energía", "herramienta",
                              "mantenimiento", "gas"]),
    ("Comercial",            ["envio", "envío", "flete", "mercadeo", "marketing",
                              "publicidad", "comision", "comisión", "muestra"]),
]


def grupo_de(categoria, descripcion=""):
    """Palabras COMPLETAS: buscar "gas" dentro del texto clasificaba
    "Gastos Operativos" como producción indirecta."""
    texto = f"{categoria} {descripcion}".strip().lower()
    for nombre, palabras in GRUPOS:
        for p in palabras:
            if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", texto):
                return nombre
    return "Otros"


def normalizar_linea(linea):
    l = str(linea or "").strip().lower()
    for clave, bonito in LINEAS.items():
        if l == clave or l == bonito.lower() or l.startswith(clave[:6]):
            return clave
    return ""


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", ".") or 0)
    except (TypeError, ValueError):
        return 0.0


def _pesos(n):
    signo = "-" if n < 0 else ""
    return f"{signo}${abs(int(round(n))):,}".replace(",", ".")


def _pct(parte, total):
    return f"{parte / total * 100:.1f}%" if total else "—"


# ── El registro de proyectos ────────────────────────────────────────────────

def _cabecera_actual():
    filas = leer_sheet_numericos(f"'{PESTANA}'!A1:H1")
    return [str(x).strip() for x in filas[0]] if filas and filas[0] else []


def _asegurar_pestana():
    """Crea la pestaña, o avisa si la que hay es la vieja de 20 columnas.

    La v1 tenía Proyecto · Cliente/Colaborador · Estado · presupuesto original ·
    presupuesto revisado · real… Escribir 8 columnas encima de ese esquema
    metería los datos en las casillas equivocadas."""
    cab = _cabecera_actual()
    if not cab:
        r = crear_pestana(PESTANA)
        if str(r).startswith(("Error", "❌")):
            return str(r)
        escribir_rango(f"'{PESTANA}'!A1:H1", [CABECERA])
        return ""
    if len(cab) > 1 and cab[1].strip().lower() != "línea":
        return ("LA PESTAÑA ES LA VIEJA. La pestaña Proyectos tiene todavía el formato "
                "anterior (presupuesto original / revisado / real, 20 columnas). Escribir "
                "encima metería los datos en las casillas equivocadas. Para pasar al nuevo "
                "formato, usa `reconstruir_proyectos`: aparta la vieja como "
                "'Proyectos (v1)' y crea la nueva. No se borra nada.")
    return ""


def reconstruir():
    """Aparta la pestaña vieja y crea la nueva. No borra nada."""
    cab = _cabecera_actual()
    if cab and len(cab) > 1 and cab[1].strip().lower() == "línea":
        return "La pestaña Proyectos ya está en el formato nuevo."
    if cab:
        r = renombrar_pestana(PESTANA, "Proyectos (v1)")
        if str(r).startswith(("Error", "❌")):
            return "❌ No pude apartar la pestaña vieja: " + str(r)
    r = crear_pestana(PESTANA)
    if str(r).startswith(("Error", "❌")):
        return "❌ " + str(r)
    escribir_rango(f"'{PESTANA}'!A1:H1", [CABECERA])
    return ("✅ Pestaña *Proyectos* creada con el formato nuevo: "
            "Proyecto · Línea · Cliente · Estado · Inicio · Cierre · Cotización · Notas.\n"
            "   La anterior quedó apartada como *Proyectos (v1)*, sin borrar nada.")


def listar():
    return [f for f in leer_sheet_numericos(f"'{PESTANA}'!A2:H300") if f and str(f[0]).strip()]


def buscar(nombre):
    clave = str(nombre or "").strip().lower()
    if not clave:
        return None
    for f in listar():
        p = str(f[0]).strip().lower()
        cliente = str(f[2]).strip().lower() if len(f) > 2 else ""
        if clave == p or clave in p or (cliente and clave in cliente):
            return f
    # Por cliente: "Manuela Florez - Vajilla" encuentra el proyecto de Manuela,
    # pero solo si ella tiene UN proyecto abierto — con dos, adivinar es peor.
    del_cliente = [f for f in listar()
                   if len(f) > 2 and str(f[2]).strip()
                   and str(f[2]).strip().lower() in clave
                   and (len(f) < 4 or str(f[3]).strip().lower() != "cerrado")]
    return del_cliente[0] if len(del_cliente) == 1 else None


def crear(proyecto, linea, cliente="", cotizacion="", inicio="", notas=""):
    if not str(proyecto or "").strip():
        return "❌ Falta el nombre del proyecto."
    clave = normalizar_linea(linea)
    if not clave:
        return ("❌ La línea tiene que ser una de: personalizacion, b2b o coleccion.")
    if buscar(proyecto):
        return f"↩️ El proyecto '{proyecto}' ya existe."
    fallo = _asegurar_pestana()
    if fallo:
        return "❌ No pude crear la pestaña Proyectos: " + fallo
    fila = [proyecto.strip(), LINEAS[clave], cliente, "abierto",
            inicio or datetime.now().strftime("%d/%m/%Y"), "", cotizacion, notas]
    r = agregar_fila(f"'{PESTANA}'!A:H", fila)
    if str(r).startswith(("Error", "❌")):
        return "❌ " + str(r).replace("Error: ", "", 1)
    return (f"✅ Proyecto *{proyecto}* creado en {LINEAS[clave]}.\n"
            f"   Al registrar compras o ingresos, nómbralo para que entren a su PNL.")


# ── El PNL ──────────────────────────────────────────────────────────────────

HOJA_PNL = "PNL Proyectos"

# Renglones directos: lo que tiene el proyecto puesto en la columna K.
# (clave, etiqueta, categorías de Movimientos)
COSTO_VENTAS = [
    ("mp", "Materia prima",                  {"materia prima"}),
    ("mo", "Mano de obra directa",           {"mano de obra"}),
    ("ci", "Costos indirectos de producción", {"costos indirectos"}),
]
GASTOS_VENTA = [
    ("env", "Envíos y empaques",       {"envíos", "envios", "empaques"}),
    ("com", "Comisiones y pasarelas",  {"comisiones pasarela", "fee shopify"}),
    ("mer", "Mercadeo del proyecto",   {"publicidad", "redes sociales", "eventos"}),
    ("otr", "Otros gastos del proyecto", set()),
]
# Si la categoría no es una de las de arriba, se clasifica por palabras.
_POR_GRUPO = {"Materia prima": "mp", "Mano de obra": "mo",
              "Producción indirecta": "ci", "Comercial": "env", "Otros": "otr"}

# Gastos compartidos: egresos SIN proyecto. Lo que no está acá (materia prima,
# empaques, envíos, comisiones sin proyecto) es costo directo de las ventas de
# tienda y online, no de los proyectos.
COMPARTIDOS = [
    ("prod", "Producción compartida",   {"mano de obra", "costos indirectos"}),
    ("marc", "Mercadeo de marca",       {"redes sociales", "publicidad", "eventos"}),
    ("adm",  "Administración",          {"arriendo", "salario gerente", "aportes",
                                         "contadora", "servicios admin",
                                         "gastos operativos"}),
]
NO_ES_VENTA = {"ingresos financieros"}


def _renglon_directo(categoria, descripcion):
    cat = str(categoria or "").strip().lower()
    for clave, _, cats in COSTO_VENTAS + GASTOS_VENTA:
        if cat in cats:
            return clave
    return _POR_GRUPO[grupo_de(categoria, descripcion)]


def _mes(f):
    """El mes contable (Mes y Año de la fila), el mismo que usa el PNL del mes."""
    mes, anio = str(f[1]).strip().capitalize(), str(f[2]).strip()
    try:
        anio = str(int(float(anio)))
    except ValueError:
        pass
    return f"{mes} {anio}" if mes and anio else ""


def _es_ingreso(f):
    return str(f[3]).strip().lower().startswith("ingreso")


def _libro():
    return [f for f in leer_sheet_numericos(f"{MOVIMIENTOS}!A2:K5000")
            if f and len(f) >= 9]


def calcular(registro=None, libro=None):
    """Un dict por proyecto con todo su PNL. Lee Movimientos UNA vez."""
    registro = listar() if registro is None else registro
    libro = _libro() if libro is None else libro

    # Lo que entró a la empresa y lo compartido, mes por mes.
    ventas_mes, pool_mes = {}, {}
    for f in libro:
        m, monto = _mes(f), _num(f[8])
        if not m or not monto:
            continue
        suyo = str(f[10]).strip() if len(f) > 10 else ""
        cat = str(f[4]).strip().lower()
        if _es_ingreso(f):
            if cat not in NO_ES_VENTA:
                ventas_mes[m] = ventas_mes.get(m, 0.0) + monto
        elif not suyo:
            for clave, _, cats in COMPARTIDOS:
                if cat in cats:
                    pool_mes.setdefault(m, {})
                    pool_mes[m][clave] = pool_mes[m].get(clave, 0.0) + monto

    salida = []
    for fila in registro:
        nombre = str(fila[0]).strip()
        clave = nombre.lower()
        p = {"nombre": nombre,
             "linea": str(fila[1]).strip() if len(fila) > 1 else "",
             "cliente": str(fila[2]).strip() if len(fila) > 2 else "",
             "estado": str(fila[3]).strip() if len(fila) > 3 else "",
             "cotizado": _num(fila[6]) if len(fila) > 6 else 0.0,
             "ingresos": 0.0, "directo": {}, "compartido": {}, "reparto": []}
        ingreso_mes = {}
        for f in libro:
            if len(f) <= 10 or str(f[10]).strip().lower() != clave:
                continue
            monto = _num(f[8])
            if not monto:
                continue
            if _es_ingreso(f):
                p["ingresos"] += monto
                m = _mes(f)
                ingreso_mes[m] = ingreso_mes.get(m, 0.0) + monto
            else:
                r = _renglon_directo(f[4], f[5] if len(f) > 5 else "")
                p["directo"][r] = p["directo"].get(r, 0.0) + monto

        for m, ing in ingreso_mes.items():
            total = ventas_mes.get(m, 0.0)
            if not total:
                continue
            parte = ing / total
            p["reparto"].append((m, parte))
            for c, v in pool_mes.get(m, {}).items():
                p["compartido"][c] = p["compartido"].get(c, 0.0) + v * parte

        d = p["directo"]
        p["costo_ventas"] = sum(d.get(k, 0) for k, _, _ in COSTO_VENTAS)
        p["bruta"] = p["ingresos"] - p["costo_ventas"]
        p["gastos_venta"] = sum(d.get(k, 0) for k, _, _ in GASTOS_VENTA)
        p["contribucion"] = p["bruta"] - p["gastos_venta"]
        p["total_compartido"] = sum(p["compartido"].values())
        p["operacional"] = p["contribucion"] - p["total_compartido"]
        p["por_cobrar"] = max(p["cotizado"] - p["ingresos"], 0) if p["cotizado"] else 0
        salida.append(p)
    return salida


def cifras(proyecto):
    """(ingresos, {renglón: egreso}, egresos directos). Lo usa movimientos.py."""
    fila = buscar(proyecto)
    if not fila:
        return 0.0, {}, 0.0
    p = calcular([fila])[0]
    return p["ingresos"], p["directo"], p["costo_ventas"] + p["gastos_venta"]


def _reparto_txt(p):
    if not p["reparto"]:
        return "sin cobros aún"
    return " · ".join(f"{parte * 100:.0f}% de {m.split()[0].lower()[:3]}"
                      for m, parte in p["reparto"])


# ── Telegram ────────────────────────────────────────────────────────────────

# En el celular caben ~33 caracteres de ancho fijo: las etiquetas largas de la
# hoja no entran, así que el mensaje usa estas.
CORTAS = {"mp": "Materia prima", "mo": "Mano de obra", "ci": "Indirectos",
          "env": "Envíos/empaques", "com": "Comisiones", "mer": "Mercadeo",
          "otr": "Otros", "prod": "Taller compart.", "marc": "Marca",
          "adm": "Administración"}


def _linea_tabla(etiqueta, valor, base, signo=""):
    pct = f"{valor / base * 100:>4.0f}%" if base else ""
    return f"{(signo + etiqueta)[:17]:<17}{_pesos(valor):>11} {pct}"


def _texto_pnl(p):
    ing = p["ingresos"]
    t = [f"*{p['nombre']}* · {p['linea'] or 'sin línea'}"]
    if p["cotizado"]:
        t.append(f"Cotizado {_pesos(p['cotizado'])} · " +
                 (f"falta cobrar {_pesos(p['por_cobrar'])}" if p["por_cobrar"]
                  else "cobrado completo"))
    b = ["```", _linea_tabla("Ingresos", ing, ing)]
    for k, _, _ in COSTO_VENTAS:
        if p["directo"].get(k):
            b.append(_linea_tabla(CORTAS[k], p["directo"][k], ing, "− "))
    b.append(_linea_tabla("= Util. bruta", p["bruta"], ing))
    for k, _, _ in GASTOS_VENTA:
        if p["directo"].get(k):
            b.append(_linea_tabla(CORTAS[k], p["directo"][k], ing, "− "))
    b.append(_linea_tabla("= Contribución", p["contribucion"], ing))
    for k, _, _ in COMPARTIDOS:
        if p["compartido"].get(k):
            b.append(_linea_tabla(CORTAS[k], p["compartido"][k], ing, "− "))
    b.append(_linea_tabla("= Utilidad oper.", p["operacional"], ing))
    b.append("```")
    t.append("\n".join(b))
    if p["reparto"]:
        t.append(f"Gastos compartidos según su parte de las ventas: {_reparto_txt(p)}.")
    if p["contribucion"] < 0:
        t.append("⚠️ *Pierde plata aun sin contar arriendo ni gerencia.*")
    elif p["operacional"] < 0:
        t.append("⚠️ Cubre sus costos, pero no alcanza a pagar su parte de los fijos.")
    return "\n\n".join(t)


def pnl(proyecto):
    fila = buscar(proyecto)
    if not fila:
        nombres = ", ".join(str(x[0]).strip() for x in listar()) or "ninguno"
        return f"No encontré el proyecto '{proyecto}'. Los que hay: {nombres}."
    todos = calcular()
    p = next((x for x in todos if x["nombre"] == str(fila[0]).strip()), None)
    aviso = actualizar_hoja(todos)
    if not p or (not p["ingresos"] and not p["costo_ventas"] and not p["gastos_venta"]):
        return (f"*{fila[0]}* todavía no tiene movimientos. Registra compras e "
                f"ingresos nombrando el proyecto.")
    return _texto_pnl(p) + aviso


def por_linea(linea=""):
    """El PNL de cada línea, o el comparativo de las tres."""
    claves = [normalizar_linea(linea)] if normalizar_linea(linea) else list(LINEAS)
    todos = calcular()
    if not todos:
        return ("Todavía no hay proyectos registrados. Crea el primero y nombra el "
                "proyecto al registrar compras e ingresos.")
    aviso = actualizar_hoja(todos)

    bloques = []
    for clave in claves:
        bonito = LINEAS[clave]
        suyos = [p for p in todos if p["linea"].lower() == bonito.lower()]
        if not suyos:
            bloques.append(f"*{bonito}* — sin proyectos todavía.")
            continue
        ing = sum(p["ingresos"] for p in suyos)
        con = sum(p["contribucion"] for p in suyos)
        ope = sum(p["operacional"] for p in suyos)
        cab = [f"*{bonito}* — {len(suyos)} proyecto(s)", "```",
               _linea_tabla("Ingresos", ing, ing),
               _linea_tabla("Contribución", con, ing),
               _linea_tabla("Util. operac.", ope, ing), "```"]
        for p in sorted(suyos, key=lambda x: x["operacional"]):
            if p["ingresos"] or p["costo_ventas"] or p["gastos_venta"]:
                marca = "⚠️" if p["operacional"] < 0 else "·"
                cab.append(f"{marca} {p['nombre']}: {_pesos(p['operacional'])} "
                           f"sobre {_pesos(p['ingresos'])}")
        bloques.append("\n".join(cab))
    return "*PNL por línea de negocio*\n\n" + "\n\n".join(bloques) + aviso


# ── La pestaña PNL Proyectos ────────────────────────────────────────────────

def _col(n):
    """0 → A, 25 → Z, 26 → AA."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _tabla(todos):
    """Las filas de la hoja y el tipo de cada una (para el formato)."""
    tot = {"nombre": "Total proyectos", "linea": "", "cliente": "", "estado": "",
           "reparto": [], "directo": {}, "compartido": {}}
    for k in ("ingresos", "cotizado", "por_cobrar", "costo_ventas", "bruta",
              "gastos_venta", "contribucion", "total_compartido", "operacional"):
        tot[k] = sum(p[k] for p in todos)
    for grupo in ("directo", "compartido"):
        for p in todos:
            for k, v in p[grupo].items():
                tot[grupo][k] = tot[grupo].get(k, 0) + v
    cols = todos + [tot]

    def num(fn):
        return [round(fn(p)) if fn(p) else 0 for p in cols]

    def pct(k):
        return [p[k] / p["ingresos"] if p["ingresos"] else "" for p in cols]

    filas = []   # (tipo, etiqueta, valores)
    filas.append(("cab", "PNL por proyecto", [p["nombre"] for p in cols]))
    filas.append(("txt", "Línea", [p["linea"] for p in cols]))
    filas.append(("txt", "Cliente", [p["cliente"] for p in cols]))
    filas.append(("txt", "Estado", [p["estado"] for p in cols]))
    filas.append(("vac", "", []))
    filas.append(("sec", "INGRESOS", []))
    filas.append(("num", "Ingresos cobrados", num(lambda p: p["ingresos"])))
    filas.append(("num", "Cotizado", num(lambda p: p["cotizado"])))
    filas.append(("num", "Por cobrar", num(lambda p: p["por_cobrar"])))
    filas.append(("vac", "", []))
    filas.append(("sec", "COSTO DE VENTAS", []))
    for k, et, _ in COSTO_VENTAS:
        filas.append(("num", et, num(lambda p, k=k: p["directo"].get(k, 0))))
    filas.append(("sub", "Total costo de ventas", num(lambda p: p["costo_ventas"])))
    filas.append(("res", "(=) UTILIDAD BRUTA", num(lambda p: p["bruta"])))
    filas.append(("pct", "Margen bruto", pct("bruta")))
    filas.append(("vac", "", []))
    filas.append(("sec", "GASTOS DIRECTOS DE VENTA", []))
    for k, et, _ in GASTOS_VENTA:
        filas.append(("num", et, num(lambda p, k=k: p["directo"].get(k, 0))))
    filas.append(("sub", "Total gastos directos", num(lambda p: p["gastos_venta"])))
    filas.append(("res", "(=) CONTRIBUCIÓN", num(lambda p: p["contribucion"])))
    filas.append(("pct", "Margen de contribución", pct("contribucion")))
    filas.append(("vac", "", []))
    filas.append(("sec", "GASTOS COMPARTIDOS (según su parte de las ventas del mes)", []))
    filas.append(("txt", "Parte de las ventas", [_reparto_txt(p) if p is not tot else ""
                                                 for p in cols]))
    for k, et, _ in COMPARTIDOS:
        filas.append(("num", et, num(lambda p, k=k: p["compartido"].get(k, 0))))
    filas.append(("sub", "Total gastos compartidos", num(lambda p: p["total_compartido"])))
    filas.append(("res", "(=) UTILIDAD OPERACIONAL", num(lambda p: p["operacional"])))
    filas.append(("pct", "Margen operacional", pct("operacional")))
    filas.append(("vac", "", []))
    try:
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo("America/Bogota"))
    except Exception:
        ahora = datetime.now()
    filas.append(("nota", f"Actualizado {ahora.strftime('%d/%m/%Y %H:%M')}. La "
                  "hace el bot: no se edita a mano. Los gastos compartidos (taller, "
                  "mercadeo de marca, arriendo, gerencia, servicios) son los egresos "
                  "del mes sin proyecto, repartidos según lo que cobró cada proyecto "
                  "ese mes sobre todo lo que cobró la empresa. Un proyecto que aún no "
                  "cobra nada no carga gastos compartidos.", []))
    return filas, len(cols)


def _formato(hid, filas, n_cols):
    ultima = n_cols  # columnas B.. hasta la de total (índice n_cols)
    def rango(f0, f1, c0=0, c1=None):
        return {"sheetId": hid, "startRowIndex": f0, "endRowIndex": f1,
                "startColumnIndex": c0, "endColumnIndex": ultima + 1 if c1 is None else c1}

    def celda(r, fmt, campos):
        return {"repeatCell": {"range": r, "cell": {"userEnteredFormat": fmt},
                               "fields": "userEnteredFormat(" + campos + ")"}}

    verde = {"red": 0.36, "green": 0.45, "blue": 0.36}
    crema = {"red": 0.96, "green": 0.94, "blue": 0.90}
    gris = {"red": 0.95, "green": 0.95, "blue": 0.95}
    blanco = {"red": 1, "green": 1, "blue": 1}
    req = [
        # Todo a cero: el formato de una pasada anterior no debe quedar pegado.
        celda(rango(0, len(filas) + 5, 0, ultima + 6), {}, "backgroundColor,textFormat,"
              "numberFormat,borders,horizontalAlignment,wrapStrategy"),
        {"updateSheetProperties": {"properties": {"sheetId": hid, "gridProperties": {
            "frozenRowCount": 1, "frozenColumnCount": 1}},
            "fields": "gridProperties(frozenRowCount,frozenColumnCount)"}},
        {"updateDimensionProperties": {"range": {"sheetId": hid, "dimension": "COLUMNS",
            "startIndex": 0, "endIndex": 1}, "properties": {"pixelSize": 300},
            "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": hid, "dimension": "COLUMNS",
            "startIndex": 1, "endIndex": ultima + 1}, "properties": {"pixelSize": 170},
            "fields": "pixelSize"}},
        celda(rango(0, 1), {"backgroundColor": verde, "wrapStrategy": "WRAP",
              "textFormat": {"bold": True, "foregroundColor": blanco}}, "backgroundColor,textFormat,wrapStrategy"),
        celda(rango(0, len(filas), ultima, ultima + 1), {"backgroundColor": gris},
              "backgroundColor"),
        celda(rango(0, 1, ultima, ultima + 1), {"backgroundColor": verde,
              "textFormat": {"bold": True, "foregroundColor": blanco}}, "backgroundColor,textFormat"),
    ]
    borde = {"style": "SOLID", "color": {"red": 0.6, "green": 0.6, "blue": 0.6}}
    for i, (tipo, _, _) in enumerate(filas):
        r = rango(i, i + 1)
        rv = rango(i, i + 1, 1)
        if tipo == "sec":
            req.append(celda(r, {"backgroundColor": crema, "textFormat": {"bold": True}},
                             "backgroundColor,textFormat"))
        if tipo in ("num", "sub", "res"):
            req.append(celda(rv, {"numberFormat": {"type": "CURRENCY",
                                  "pattern": "$#,##0;[Red]-$#,##0;\"–\""}}, "numberFormat"))
        if tipo == "pct":
            req.append(celda(rv, {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"},
                                  "textFormat": {"italic": True}}, "numberFormat,textFormat"))
            req.append(celda(rango(i, i + 1, 0, 1), {"textFormat": {"italic": True}}, "textFormat"))
        if tipo == "sub":
            req.append(celda(r, {"textFormat": {"bold": True}}, "textFormat"))
        if tipo == "res":
            req.append(celda(r, {"textFormat": {"bold": True}, "backgroundColor": crema,
                                 "borders": {"top": borde}}, "textFormat,backgroundColor,borders"))
        if tipo == "txt":
            req.append(celda(rv, {"horizontalAlignment": "RIGHT", "wrapStrategy": "WRAP"},
                             "horizontalAlignment,wrapStrategy"))
        if tipo == "nota":
            req.append({"mergeCells": {"range": rango(i, i + 1), "mergeType": "MERGE_ALL"}})
            req.append(celda(r, {"wrapStrategy": "WRAP", "textFormat": {
                "italic": True, "fontSize": 9}}, "wrapStrategy,textFormat"))
    return req


def actualizar_hoja(todos=None):
    """Reescribe la pestaña PNL Proyectos. Devuelve "" si salió bien, o un aviso
    corto para pegar al final del mensaje: la hoja nunca debe tumbar la respuesta."""
    try:
        todos = calcular() if todos is None else todos
        if not todos:
            return ""
        filas, n_cols = _tabla(todos)
        hid = id_pestana(HOJA_PNL)
        if hid is None:
            r = crear_pestana(HOJA_PNL)
            if str(r).startswith("Error"):
                return f"\n\n⚠️ No pude crear la pestaña {HOJA_PNL}."
            hid = id_pestana(HOJA_PNL)
        valores = [[et] + list(vals) for _, et, vals in filas]
        rango = f"'{HOJA_PNL}'!A1:{_col(n_cols)}{len(filas)}"
        # Deshacer uniones de una pasada anterior antes de limpiar y reescribir.
        formatear([{"unmergeCells": {"range": {"sheetId": hid}}}])
        limpiar_rango(f"'{HOJA_PNL}'!A1:ZZ200")
        r = escribir_rango(rango, valores)
        if str(r).startswith("Error"):
            return f"\n\n⚠️ No pude actualizar la pestaña {HOJA_PNL}: {r}"
        formatear(_formato(hid, filas, n_cols))
        return ""
    except Exception as e:
        return f"\n\n⚠️ No pude actualizar la pestaña {HOJA_PNL}: {e}"


if __name__ == "__main__":
    print(actualizar_hoja() or f"✅ {HOJA_PNL} actualizada.")
