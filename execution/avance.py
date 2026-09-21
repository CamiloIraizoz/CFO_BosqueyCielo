"""La etapa de un pedido se deduce de lo que el taller reportó.

Antes la etapa era un campo que alguien actualizaba a mano, y por eso era una
opinión: un pedido de 150 platos "estaba en pintar bizcocho" aunque hubiera 40
pintados, 30 en el horno y 80 sin tocar.

Ahora sale de las jornadas. Un pedido pasó una etapa cuando el número de piezas
que reportaron en esa etapa alcanza la cantidad del pedido. La regla de oro:
**la deducción solo avanza, nunca retrocede** — si alguien corrigió la etapa a
mano, una jornada vieja no puede echarla para atrás.
"""

import re

from sheets import actualizar_celda, leer_sheet_numericos

# Las etapas de cada proceso, en orden. La última no es trabajo: es el final.
ETAPAS_PROCESO = {
    1: ["modelado", "secado", "primera quema", "esmaltado", "segunda quema",
        "acabado", "empaque", "entregado"],
    2: ["esmaltado inicial", "pintar bizcocho", "primera quema", "acabado",
        "empaque", "entregado"],
}

# Cómo habla el taller → a qué etapa pertenece esa tarea.
PALABRAS = {
    "modelado":          ["modelar", "modelado", "tornear", "torno", "amasar",
                          "moldear", "dar forma", "aplique", "relieve"],
    "secado":            ["secar", "secado", "oreo", "oreando"],
    "primera quema":     ["primera quema", "bizcochar", "quema 1", "quemar bizcocho"],
    "segunda quema":     ["segunda quema", "quema 2", "quema de esmalte"],
    "esmaltado inicial": ["esmaltar", "esmaltado", "esmalte", "engobe", "base"],
    "esmaltado":         ["esmaltar", "esmaltado", "esmalte", "engobe"],
    "pintar bizcocho":   ["pintar", "pintada", "pintado", "decorar", "vinilo",
                          "adhesivo", "transfer", "sello", "tintas", "letras"],
    "acabado":           ["acabado", "transparente", "retocar", "retoque", "pulir"],
    "empaque":           ["empacar", "empaque", "embalar", "limpiar", "lijar",
                          "revisar", "calidad", "terminado"],
}


def etapa_de_tarea(tarea, proceso):
    """A qué etapa de ESE proceso pertenece lo que reportó el taller."""
    t = (tarea or "").strip().lower()
    if not t:
        return ""
    etapas = ETAPAS_PROCESO.get(int(proceso or 2), ETAPAS_PROCESO[2])
    # Se recorre en orden inverso para que "segunda quema" gane sobre "quema".
    for etapa in reversed(etapas):
        for palabra in PALABRAS.get(etapa, []):
            if palabra in t:
                return etapa
    # "lo metí al horno" solo es asignable si el proceso tiene UNA sola quema.
    # Con dos (el clásico) es ambiguo y es mejor no adivinar.
    if any(w in t for w in ("horno", "hornear", "quemar", "quema")):
        quemas = [e for e in etapas if "quema" in e]
        if len(quemas) == 1:
            return quemas[0]
    return ""


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def cantidad_de(fila):
    """Las piezas del pedido: la columna K, o el número que abra la descripción."""
    if len(fila) > 10 and _num(fila[10]) > 0:
        return int(_num(fila[10]))
    m = re.search(r"\d+", str(fila[2]) if len(fila) > 2 else "")
    return int(m.group()) if m else 0


def piezas_por_etapa(pedido, proceso):
    """Cuántas piezas del pedido pasaron por cada etapa, según las jornadas."""
    clave = (pedido or "").strip().lower()
    conteo = {}
    for f in leer_sheet_numericos("'Jornadas'!A2:M1000"):
        if not f or len(f) < 8:
            continue
        if clave not in str(f[2]).strip().lower():
            continue
        etapa = etapa_de_tarea(f[3], proceso)
        if not etapa:
            continue
        conteo[etapa] = conteo.get(etapa, 0) + _num(f[7])
    return conteo


def etapa_deducida(pedido, proceso, cantidad):
    """(etapa, piezas hechas en ella, piezas que faltan). Sin cantidad no se puede."""
    etapas = ETAPAS_PROCESO.get(int(proceso or 2), ETAPAS_PROCESO[2])
    if not cantidad:
        return "", 0, 0
    conteo = piezas_por_etapa(pedido, proceso)
    for etapa in etapas[:-1]:
        hechas = conteo.get(etapa, 0)
        if hechas < cantidad:
            return etapa, int(hechas), int(cantidad - hechas)
    return etapas[-1], int(cantidad), 0


def _ritmo(pedido, etapa="", proceso=2):
    """Minutos por pieza. Si se pide una etapa, el de ESA etapa.

    Promediar todas las etapas subestima feo: si esmaltar va a 6 min y pintar a
    24, el promedio dice 11 y el pintado que falta sale a menos de la mitad."""
    minutos = piezas = 0.0
    clave = (pedido or "").strip().lower()
    for f in leer_sheet_numericos("'Jornadas'!A2:M1000"):
        if not f or len(f) < 11 or clave not in str(f[2]).strip().lower():
            continue
        if etapa and etapa_de_tarea(f[3], proceso) != etapa:
            continue
        minutos += _num(f[10])
        piezas += _num(f[7])
    return (minutos / piezas) if piezas else 0.0


def proyeccion(pedido, etapa, faltan, proceso=2, horas_dia=12):
    """Cuántos días de taller faltan para cerrar la etapa en curso."""
    if not faltan:
        return ""
    ritmo = _ritmo(pedido, etapa, proceso)
    medido = bool(ritmo)
    if not medido:
        ritmo = _ritmo(pedido)          # nada de esa etapa: el del pedido entero
    if not ritmo:
        return ""
    horas = faltan * ritmo / 60.0
    dias = horas / float(horas_dia or 12)
    fuente = (f"a {round(ritmo, 1)} min/pieza medidos en {etapa}" if medido
              else f"a {round(ritmo, 1)} min/pieza — el promedio del pedido, "
                   f"porque todavía no hay jornadas de {etapa}")
    return (f"Cerrar *{etapa}* son ~{round(horas)} horas de taller "
            f"({round(dias, 1)} días a {horas_dia} h/día), {fuente}. "
            f"Faltan además las etapas siguientes.")


def _pedidos():
    return leer_sheet_numericos("Producción!A:K")


def recalcular(cliente=""):
    """Mueve la etapa de los pedidos según las jornadas. Solo hacia adelante."""
    filas = _pedidos()
    if not filas or len(filas) < 2:
        return ""
    cambios = []
    for i, fila in enumerate(filas[1:], start=2):
        if not fila or len(fila) < 8:
            continue
        nombre = str(fila[1]).strip()
        if not nombre or (cliente and cliente.strip().lower() not in nombre.lower()):
            continue
        proceso = int(_num(fila[4]) or 2)
        etapas = ETAPAS_PROCESO.get(proceso, ETAPAS_PROCESO[2])
        actual = str(fila[7]).strip().lower()
        nueva, hechas, faltan = etapa_deducida(nombre, proceso, cantidad_de(fila))
        if not nueva or nueva == actual:
            continue
        # Solo hacia adelante: una jornada vieja no deshace una corrección a mano.
        try:
            if etapas.index(nueva) <= etapas.index(actual):
                continue
        except ValueError:
            pass
        r = actualizar_celda(f"Producción!H{i}", nueva)
        if str(r).startswith(("Error", "❌")):
            continue
        cambios.append(f"· {nombre}: pasó a *{nueva}*")
    return "\n".join(cambios)


def estado(cliente=""):
    """El tablero: en qué va cada pedido, con lo que falta y la proyección."""
    filas = _pedidos()
    if not filas or len(filas) < 2:
        return "No hay pedidos en producción."
    lineas = []
    for fila in filas[1:]:
        if not fila or len(fila) < 8:
            continue
        nombre = str(fila[1]).strip()
        if not nombre or (cliente and cliente.strip().lower() not in nombre.lower()):
            continue
        proceso = int(_num(fila[4]) or 2)
        cantidad = cantidad_de(fila)
        etapa, hechas, faltan = etapa_deducida(nombre, proceso, cantidad)
        guardada = str(fila[7]).strip().lower()
        # La misma regla que al recalcular: si alguien corrigió a mano hacia
        # adelante, el tablero muestra la corrección, no la deducción atrasada.
        etapas = ETAPAS_PROCESO.get(proceso, ETAPAS_PROCESO[2])
        if etapa and guardada in etapas and etapas.index(guardada) > etapas.index(etapa):
            etapa, hechas, faltan = guardada, 0, cantidad
        etapa = etapa or guardada
        entrega = str(fila[6]).strip()
        cab = f"*{nombre}* — {str(fila[2]).strip()}"
        if not cantidad:
            lineas.append(f"{cab}\n  Etapa: {etapa} · entrega {entrega}\n"
                          f"  ⚠️ Sin cantidad de piezas no puedo deducir el avance.")
            continue
        if faltan == 0 and etapa == "entregado":
            lineas.append(f"{cab}\n  ✅ Completo · entrega {entrega}")
            continue
        detalle = f"  Etapa: *{etapa}* — {hechas} de {cantidad}, faltan {faltan}"
        proy = proyeccion(nombre, etapa, faltan, proceso)
        lineas.append(f"{cab}\n{detalle}\n  Entrega {entrega}" +
                      (f"\n  {proy}" if proy else ""))
    if not lineas:
        return "No hay pedidos en producción." if not cliente else f"No encontré el pedido de {cliente}."
    return "*Producción*\n\n" + "\n\n".join(lineas)
