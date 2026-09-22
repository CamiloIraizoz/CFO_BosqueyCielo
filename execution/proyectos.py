"""Proyectos y su mini PNL.

Bosque y Cielo vende por tres líneas y cada una se comporta distinto:

  · **personalizacion** — pedidos a la medida para una persona o empresa.
  · **b2b**             — volumen para otro negocio que revende.
  · **coleccion**       — la colección propia, que se vende en tienda y online.

Un proyecto pertenece a una línea. Su PNL sale de la pestaña `Movimientos`
—el libro contable de siempre— filtrando por la columna **Proyecto**. No hay
un segundo libro: lo que se registra una vez sirve para el PNL del mes y para
el del proyecto.

Lo que este módulo NO hace: repartir los costos fijos (arriendo, servicios,
gerencia). Un PNL por proyecto honesto llega hasta la **contribución** — lo que
el proyecto deja para pagar esos fijos. Sumar las contribuciones de todos los
proyectos del mes y restarles los fijos es lo que dice si se ganó dinero.
"""

import re
from datetime import datetime

from sheets import agregar_fila, crear_pestana, escribir_rango, leer_sheet_numericos, \
    renombrar_pestana

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
    try:
        return float(str(v).replace("$", "").replace(".", "").replace(",", ".") or 0)
    except (TypeError, ValueError):
        return 0.0


def _pesos(n):
    return f"${int(round(n)):,}".replace(",", ".")


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
    return None


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

def _movimientos_de(proyecto=""):
    """Las filas de Movimientos que pertenecen al proyecto (columna K)."""
    filas = leer_sheet_numericos(f"{MOVIMIENTOS}!A2:K5000")
    clave = str(proyecto or "").strip().lower()
    salida = []
    for f in filas:
        if not f or len(f) < 9:
            continue
        suyo = str(f[10]).strip().lower() if len(f) > 10 else ""
        if clave and suyo != clave and clave not in suyo:
            continue
        if not clave and not suyo:
            continue
        salida.append(f)
    return salida


def cifras(proyecto):
    """(ingresos, {grupo: egreso}, egresos totales)."""
    ingresos = 0.0
    egresos = {}
    for f in _movimientos_de(proyecto):
        monto = _num(f[8])
        if not monto:
            continue
        if str(f[3]).strip().lower().startswith("ingreso"):
            ingresos += monto
        else:
            g = grupo_de(f[4] if len(f) > 4 else "", f[5] if len(f) > 5 else "")
            egresos[g] = egresos.get(g, 0.0) + monto
    return ingresos, egresos, sum(egresos.values())


def pnl(proyecto):
    fila = buscar(proyecto)
    nombre = str(fila[0]).strip() if fila else proyecto
    linea = str(fila[1]).strip() if fila and len(fila) > 1 else "sin línea"
    ingresos, egresos, total_eg = cifras(nombre)

    if not ingresos and not total_eg:
        return (f"*{nombre}* ({linea})\n\nTodavía no tiene movimientos. "
                f"Registra las compras y los ingresos nombrando el proyecto.")

    directos = egresos.get("Materia prima", 0) + egresos.get("Mano de obra", 0)
    bruto = ingresos - directos
    otros = total_eg - directos
    contribucion = ingresos - total_eg

    l = [f"*{nombre}* — {linea}", ""]
    l.append(f"Ingresos: *{_pesos(ingresos)}*")
    for g in ("Materia prima", "Mano de obra"):
        if egresos.get(g):
            l.append(f"− {g}: {_pesos(egresos[g])} ({_pct(egresos[g], ingresos)})")
    l.append(f"*= Margen bruto: {_pesos(bruto)} ({_pct(bruto, ingresos)})*")
    for g, v in sorted(egresos.items(), key=lambda x: -x[1]):
        if g in ("Materia prima", "Mano de obra"):
            continue
        l.append(f"− {g}: {_pesos(v)} ({_pct(v, ingresos)})")
    if otros:
        l.append(f"*= Contribución: {_pesos(contribucion)} "
                 f"({_pct(contribucion, ingresos)})*")

    if fila and len(fila) > 6 and str(fila[6]).strip():
        cot = _num(fila[6])
        if cot:
            falta = cot - ingresos
            l.append("")
            l.append(f"Cotizado: {_pesos(cot)}" +
                     (f" · falta cobrar {_pesos(falta)}" if falta > 0
                      else " · cobrado completo"))
    l.append("")
    if contribucion < 0:
        l.append("⚠️ *Este proyecto está perdiendo plata* antes de contar los fijos.")
    else:
        l.append("Los fijos (arriendo, servicios, gerencia) NO están acá: esto es lo "
                 "que el proyecto deja para pagarlos.")
    return "\n".join(l)


def por_linea(linea=""):
    """El PNL de cada línea, o el comparativo de las tres."""
    claves = [normalizar_linea(linea)] if normalizar_linea(linea) else list(LINEAS)
    proyectos = listar()
    if not proyectos:
        return ("Todavía no hay proyectos registrados. Crea el primero y nombra el "
                "proyecto al registrar compras e ingresos.")

    bloques = []
    for clave in claves:
        bonito = LINEAS[clave]
        suyos = [f for f in proyectos
                 if str(f[1]).strip().lower() == bonito.lower()] if proyectos else []
        if not suyos:
            bloques.append(f"*{bonito}* — sin proyectos todavía.")
            continue
        ing = eg = 0.0
        detalle = []
        for f in suyos:
            i, _, e = cifras(str(f[0]).strip())
            ing += i
            eg += e
            if i or e:
                detalle.append((str(f[0]).strip(), i - e, i))
        contrib = ing - eg
        cab = (f"*{bonito}* — {len(suyos)} proyecto(s)\n"
               f"  Ingresos {_pesos(ing)} · costos {_pesos(eg)} · "
               f"*contribución {_pesos(contrib)}* ({_pct(contrib, ing)})")
        for nombre, c, i in sorted(detalle, key=lambda x: x[1]):
            marca = "⚠️" if c < 0 else "·"
            cab += f"\n  {marca} {nombre}: {_pesos(c)} sobre {_pesos(i)}"
        bloques.append(cab)

    pie = ("\nLa contribución es lo que queda antes de los fijos del mes "
           "(arriendo, servicios, gerencia).")
    return "*PNL por línea de negocio*\n\n" + "\n\n".join(bloques) + "\n" + pie
