"""Jornadas de taller: lo que el equipo reporta cada día por Telegram.

Una jornada es una franja de trabajo sobre una tarea concreta:
"empecé a pintar a las 10:00, terminé a las 2:00, hice 10 platos".

De ahí salen dos cosas a la vez:
  1. El seguimiento del pedido — quién hizo qué, cuándo y cuántas piezas.
  2. EL TIEMPO ESTÁNDAR — minutos por pieza medidos en planta, que es
     justo el dato que al cotizador le falta. Cada jornada es una
     medición; el promedio de varias es el estándar.

Por eso la jornada guarda la etapa del Discovery además de la tarea en
las palabras del taller: "pintar" es trabajo de la etapa "Acabado".
"""

import re
from datetime import datetime

from sheets import agregar_fila, crear_pestana, escribir_rango, leer_sheet_numericos

PESTANA = "Jornadas"

CABECERA = ["Fecha", "Persona", "Pedido", "Tarea", "Etapa", "Tamaño", "Dificultad",
            "Piezas", "Inicio", "Fin", "Minutos", "Min/pieza", "Notas"]

# Las tres etapas del Discovery que sí son tiempo por pieza. La quema no
# está: es por hornada, no por pieza.
ETAPAS = ["Modelado", "Acabado", "Terminado, calidad y empaque"]

# Cómo habla el taller → a qué etapa del cotizador pertenece esa tarea.
TAREAS = {
    "Modelado": ["modelar", "modelado", "tornear", "torno", "dar forma", "amasar",
                 "aplique", "apliques", "relieve", "moldear", "molde"],
    "Acabado": ["pintar", "pintada", "pintado", "esmaltar", "esmaltado", "esmalte",
                "decorar", "decoracion", "vinilo", "adhesivo", "transfer", "sello",
                "sellos", "tintas", "letras", "engobe"],
    "Terminado, calidad y empaque": ["empacar", "empaque", "limpiar", "limpieza",
                                     "lijar", "pulir", "revisar", "calidad",
                                     "terminado", "acabado final", "embalar"],
}

_HORA = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?|am|pm)?\s*$", re.I)


def etapa_de_tarea(tarea: str) -> str:
    """A qué etapa del cotizador corresponde lo que dijo el taller."""
    t = (tarea or "").strip().lower()
    for etapa, palabras in TAREAS.items():
        for p in palabras:
            if p in t:
                return etapa
    return ""


def minutos_hora(texto: str):
    """'10:00 am' · '2 pm' · '14:30' → minutos desde medianoche. None si no se entiende."""
    m = _HORA.match(str(texto or ""))
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2) or 0)
    sufijo = (m.group(3) or "").replace(".", "").lower()
    if h > 23 or mi > 59:
        return None
    if sufijo.startswith("p") and h < 12:
        h += 12
    elif sufijo.startswith("a") and h == 12:
        h = 0
    return h * 60 + mi


def duracion(hora_inicio: str, hora_fin: str):
    """Minutos entre dos horas. Devuelve (minutos, aviso)."""
    a, b = minutos_hora(hora_inicio), minutos_hora(hora_fin)
    if a is None or b is None:
        return None, "No entendí las horas: escríbelas como '10:00 am' y '2:00 pm'."
    aviso = ""
    if b <= a:
        # Sin sufijo, "de 10 a 2" casi siempre es 10am a 2pm. Solo se corrige
        # cuando la hora de fin venía sin am/pm y el turno queda dentro del día.
        dijo_sufijo = bool(re.search(r"[ap]\.?\s*m", str(hora_fin or ""), re.I))
        if not dijo_sufijo and a < b + 12 * 60 < 24 * 60:
            b += 12 * 60
            aviso = f"Entendí que terminó a las {b // 60}:{b % 60:02d}."
        else:
            return None, "La hora de fin quedó antes que la de inicio."
    if b - a > 16 * 60:
        return None, "Esa jornada da más de 16 horas: revisa las horas."
    return b - a, aviso


def _asegurar_pestana():
    filas = leer_sheet_numericos(f"'{PESTANA}'!A1:M1")
    if filas and filas[0]:
        return
    crear_pestana(PESTANA)
    escribir_rango(f"'{PESTANA}'!A1:M1", [CABECERA])


def registrar(persona, tarea, piezas, hora_inicio="", hora_fin="", minutos=None,
              pedido="", tamano="", dificultad="", fecha="", notas="", etapa=""):
    """Guarda una jornada y devuelve el texto que el bot le responde al taller."""
    piezas = int(piezas or 0)
    if piezas <= 0:
        return "❌ Falta cuántas piezas se hicieron: sin eso no sale el tiempo por pieza."

    aviso = ""
    if minutos is None:
        minutos, aviso = duracion(hora_inicio, hora_fin)
        if minutos is None:
            return "❌ " + aviso
    minutos = round(float(minutos), 1)
    if minutos <= 0:
        return "❌ La jornada quedó en cero minutos."

    etapa = etapa or etapa_de_tarea(tarea)
    por_pieza = round(minutos / piezas, 1)
    fecha = fecha or datetime.now().strftime("%d/%m/%Y")

    _asegurar_pestana()
    fila = [fecha, persona, pedido, tarea, etapa, (tamano or "").upper(),
            (dificultad or "").lower(), piezas, hora_inicio, hora_fin,
            minutos, por_pieza, notas]
    r = agregar_fila(f"'{PESTANA}'!A:M", fila)
    if str(r).startswith("❌"):
        return r

    horas = int(minutos // 60)
    resto = int(minutos % 60)
    dur = f"{horas}h {resto:02d}m" if horas else f"{resto} min"
    salida = [f"✅ Anotado: {persona} — {tarea}, {piezas} piezas en {dur}.",
              f"   Da *{por_pieza} min por pieza*."]
    if aviso:
        salida.append("   " + aviso)
    if not etapa:
        salida.append("   ⚠️ No supe a qué etapa pertenece esa tarea, así que no "
                      "cuenta para el estándar del cotizador.")
    elif not tamano:
        salida.append(f"   ⚠️ Etapa *{etapa}*, pero sin tamaño (XS-XL) no entra al "
                      "estándar. ¿De qué tamaño eran?")
    else:
        salida.append(_comparar(etapa, tamano, dificultad, por_pieza))
    return "\n".join([s for s in salida if s])


def _filas():
    filas = leer_sheet_numericos(f"'{PESTANA}'!A2:M1000")
    return [f for f in filas if f and len(f) >= 12]


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def promedio(etapa, tamano, dificultad=""):
    """(promedio min/pieza, cuántas jornadas, cuántas piezas) de lo medido."""
    tot_min = tot_piezas = n = 0
    for f in _filas():
        if str(f[4]).strip().lower() != etapa.strip().lower():
            continue
        if str(f[5]).strip().upper() != (tamano or "").strip().upper():
            continue
        if dificultad and str(f[6]).strip().lower() != dificultad.strip().lower():
            continue
        piezas, minutos = _num(f[7]), _num(f[10])
        if not piezas or minutos is None:
            continue
        tot_min += minutos
        tot_piezas += piezas
        n += 1
    if not tot_piezas:
        return None, 0, 0
    # Se pondera por piezas: una jornada de 30 piezas pesa más que una de 2.
    return round(tot_min / tot_piezas, 1), n, int(tot_piezas)


def _comparar(etapa, tamano, dificultad, por_pieza):
    prom, n, piezas = promedio(etapa, tamano, dificultad)
    if n <= 1:
        return (f"   Primera medición de *{etapa} · {tamano}*. Con dos o tres más "
                "ya sirve para cargarla como estándar.")
    linea = (f"   Con {n} jornadas ({piezas} piezas), *{etapa} · {tamano}* va en "
             f"*{prom} min/pieza*.")
    if prom and abs(por_pieza - prom) / prom > 0.35:
        linea += " ⚠️ Esta jornada se salió bastante del promedio: vale la pena mirar por qué."
    return linea


def resumen(etapa=""):
    """Tabla de lo medido hasta hoy, lista para cargar como estándar."""
    filas = _filas()
    if not filas:
        return ("Todavía no hay jornadas registradas. Cuando el equipo reporte por "
                "Telegram ('pinté 10 platos medianos de 10:00 a 2:00'), acá empiezan "
                "a salir los minutos por pieza medidos en planta.")
    grupos = {}
    for f in filas:
        e, t, d = str(f[4]).strip(), str(f[5]).strip().upper(), str(f[6]).strip().lower()
        if not e or not t:
            continue
        if etapa and e.lower() != etapa.strip().lower():
            continue
        piezas, minutos = _num(f[7]), _num(f[10])
        if not piezas or minutos is None:
            continue
        g = grupos.setdefault((e, t, d or "—"), [0.0, 0.0, 0])
        g[0] += minutos
        g[1] += piezas
        g[2] += 1
    if not grupos:
        return "Hay jornadas anotadas, pero ninguna con etapa y tamaño: sin eso no forman estándar."

    lineas = ["*Tiempos medidos en planta*", ""]
    for (e, t, d), (mins, piezas, n) in sorted(grupos.items()):
        prom = round(mins / piezas, 1)
        confianza = "sirve como estándar" if n >= 3 else f"apenas {n} jornada{'s' if n > 1 else ''}"
        lineas.append(f"· {e} · {t} · {d}: *{prom} min/pieza* ({int(piezas)} piezas, {confianza})")
    lineas.append("")
    lineas.append("Para dejarlo fijo en el cotizador: guardar_tiempo_estandar con esos minutos.")
    return "\n".join(lineas)


def bitacora(dias=7, pedido=""):
    """Qué se hizo en los últimos días: el parte de seguimiento."""
    filas = _filas()
    if not filas:
        return "No hay jornadas registradas todavía."
    hoy = datetime.now().date()
    vivas = []
    for f in filas:
        try:
            d = datetime.strptime(str(f[0]).strip(), "%d/%m/%Y").date()
        except ValueError:
            continue
        if (hoy - d).days > int(dias) or (hoy - d).days < 0:
            continue
        if pedido and pedido.strip().lower() not in str(f[2]).strip().lower():
            continue
        vivas.append((d, f))
    if not vivas:
        cual = f" de {pedido}" if pedido else ""
        return f"Sin jornadas{cual} en los últimos {dias} días."

    vivas.sort(key=lambda x: x[0], reverse=True)
    lineas = [f"*Últimos {dias} días en el taller*", ""]
    dia_actual = None
    total_min = total_piezas = 0
    for d, f in vivas:
        if d != dia_actual:
            dia_actual = d
            lineas.append(f"*{d.strftime('%d/%m')}*")
        minutos, piezas = _num(f[10]) or 0, _num(f[7]) or 0
        total_min += minutos
        total_piezas += piezas
        destino = f" · {f[2]}" if str(f[2]).strip() else ""
        tam = f" {f[5]}" if str(f[5]).strip() else ""
        lineas.append(f"  · {f[1]}: {f[3]}{tam} — {int(piezas)} piezas en "
                      f"{int(minutos)} min ({f[11]} min/pieza){destino}")
    lineas.append("")
    lineas.append(f"Total: {int(total_piezas)} piezas · {round(total_min / 60, 1)} horas de taller.")
    return "\n".join(lineas)
