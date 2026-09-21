#!/usr/bin/env python3
"""
Motor de cotización de Bosque y Cielo.

Replica la cadena de costeo de la hoja "Cotizador Interno":

    materiales (bizcocho + esmaltes + vinilo)
  + mano de obra (minutos x valor minuto)
  + quemas (bizcocho + esmalte + transfer)
  + empaque
  = costo directo
  + desperdicio (%)
  = costo directo total
  + mercadeo (% del costo directo total)
  + arriendo y servicios por pieza
  + gastos administrativos por pieza
  = gran total costo + gastos
  + margen (%)
  = PVP sin IVA   → + IVA → precio final

Dos decisiones tomadas con Camilo el 2026-09-17:

 1. Los costos fijos se reparten entre un VOLUMEN DE REFERENCIA fijo (150
    piezas/mes, la producción real del taller), no entre las piezas del pedido.
    Si se repartieran entre el pedido, uno de 30 piezas cargaría $69.000 de fijos
    por pieza y el precio saldría absurdo. El volumen es un parámetro editable:
    hay que actualizarlo cuando cambie la capacidad del taller.
 2. Los minutos de acabado salen de la tabla del Discovery (medida por tamaño
    y dificultad). Los demás pasos son parámetros hasta que se midan en planta.

Nada se estima en silencio: lo que no está cargado sale como advertencia y el
precio se marca como incompleto.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)
sys.path.insert(0, str(Path(__file__).parent))

# Hoja "Cotizador Interno" (archivo aparte del de Ventas y Costos).
COTIZADOR_SHEET_ID = os.getenv(
    "COTIZADOR_SHEET_ID", "1SRji5gNT85HPLOXBgUhQdIRG7WZvTTWx6eDPEu6exKE")
PESTANA_PARAMS = "Parámetros Cotizador"

# Dónde quedan guardadas las cotizaciones. Por defecto, el mismo Cotizador Interno:
# ahí ya viven los parámetros y la plantilla original. Si algún día se quieren en un
# archivo aparte, basta con definir COTIZACIONES_SHEET_ID en el entorno.
COTIZACIONES_SHEET_ID = os.getenv("COTIZACIONES_SHEET_ID", "") or COTIZADOR_SHEET_ID

# Valores leídos de la hoja el 2026-09-17. Son el respaldo si la pestaña de
# parámetros todavía no existe o el bot aún no tiene acceso al archivo.
PARAMS_DEFECTO = {
    # Mano de obra
    "salario_mensual":        4_000_000,
    "horas_semanales":        48,
    "semanas_mes":            4,
    # Lo que cuesta de verdad una hora de taller (Camilo, 2026-09-20: $10.000).
    # Si está en cero se deduce del salario mensual, que es lo que se hacía antes
    # y daba $20.833 — más del doble. Puesto a mano, este manda.
    "costo_hora_mo":          10_000,
    # La capacidad real del taller: dos personas, 6 horas al día cada una.
    # De acá sale cuántos días de trabajo quedan para un pedido.
    "personas_taller":        2,
    "horas_dia_persona":      6,
    # Reparto de fijos
    "volumen_referencia":     150,        # piezas/mes — producción real (Camilo, 2026-09-17)
    # La gerencia entra al costo SOLO por la parte de su tiempo que va a producción
    # (planear, supervisar, calidad). Lo que dedica a ventas, clientes y plata es
    # gasto de operación y lo recupera el margen, no el costo de la pieza.
    "sueldo_gerente_mes":     5_000_000,  # Camilo, 2026-09-21
    # 20% confirmado por Camilo el 2026-09-21: el resto de su día son tareas
    # gerenciales (ventas, clientes, plata), que no son costo de la pieza.
    # Es el parámetro más sensible del modelo — cada 10% son $3.333 por pieza
    # al volumen de referencia actual — así que revisarlo si cambia su rol.
    "pct_gerente_produccion": 20,
    "gastos_admin_mes":         230_000,  # contador 10% + supervisor 30% (sin la gerente)
    "arriendo_mes":           3_200_000,
    "servicios_mes":          1_000_000,  # incluye la energía de las quemas
    "pct_uso_local":          20.0,       # % del local dedicado a producción
    "pct_uso_servicios":      70.0,       # % de los servicios que carga producción — los
                                          # hornos consumen mucho más que el resto del
                                          # local (Camilo, 2026-09-17)
    # Porcentajes
    "desperdicio_pct":        10.0,
    "mercadeo_pct":           5.0,
    "margen_pct":             40.0,
    "margen_modo":            "markup",   # markup = costo x (1+m) · sobre_venta = costo / (1-m)
    "iva_pct":                19.0,
    # Costos por pieza — los pide el bot cuando faltan
    "costo_bizcocho":         0,
    "costo_esmaltes":         0,      # o se deriva de oz_esmalte_por_pieza
    "oz_esmalte_por_pieza":   0.0,    # onzas de esmalte que lleva una pieza
    "costo_vinilo":           0,      # por pieza, cuando la pieza lleva vinilo
    # El vinilo adhesivo se pinta por encima: gasta el mismo esmalte pero se
    # trabaja más rápido (Camilo, 2026-09-19). Cuánto más rápido está sin medir:
    # en 0 no descuenta nada y el precio sale por lo alto, que es lo prudente.
    "minutos_ahorro_vinilo":  0.0,
    "costo_empaque":          0,    # por pieza: sale de repartir el empaque del pedido
    # UNA sola quema: el bizcocho se compra ya quemado, así que el taller solo
    # hace la del esmalte (Camilo, 2026-09-17). Y va en cero porque su energía ya
    # está dentro de servicios públicos, que se prorratea arriba: cargarla aquí
    # sería contarla dos veces. Solo se llenaría si algún día se mide el consumo
    # por hornada y se saca de servicios.
    "costo_quema":            0,
    # Minutos de los pasos que no son acabado (preparación, pulido, cargue…)
    "minutos_otros_pasos":    0.0,
}

# Referencia de materiales de la hoja "Cotizador Interno" (2026-09-17).
# Sirven para derivar el costo por pieza a partir del consumo: es mucho más fácil
# saber "lleva 1.5 onzas de esmalte" que "el esmalte cuesta $3.000 por pieza".
MATERIALES = {
    "esmalte_blanco":   {"nombre": "Esmalte blanco",           "precio": 260_000, "unidades": 128,    "unidad": "oz"},
    "barbotina_blanca": {"nombre": "Barbotina Blanca Marino",  "precio": 18_000,  "unidades": 128,    "unidad": "oz"},
    "arcilla_reyes":    {"nombre": "Arcilla Luis Reyes",       "precio": 4_800,   "unidades": 1_000,  "unidad": "g"},
    "arcilla_negra":    {"nombre": "Arcilla Negra Jorge Pérez","precio": 39_100,  "unidades": 10_000, "unidad": "g"},
}


def precio_unitario_material(clave: str) -> float:
    """Precio por onza o por gramo de un material de referencia."""
    m = MATERIALES[clave]
    return m["precio"] / m["unidades"]


# Lo que el bot puede preguntar y guardar solo. El texto es la pregunta literal.
PARAMS_PREGUNTABLES = {
    "costo_bizcocho":      "¿Cuánto te cuesta el bizcocho por pieza?",
    "oz_esmalte_por_pieza": "¿Cuántas onzas de esmalte lleva una pieza? "
                            f"(el galón de 128 oz cuesta $260.000, o sea ${precio_unitario_material('esmalte_blanco'):,.0f} la onza)".replace(",", "."),
    "costo_esmaltes":      "¿Cuánto cuestan los esmaltes por pieza? "
                           "(si prefieres, dime las onzas y yo saco el valor)",

    "costo_vinilo":        "¿Cuánto cuesta el vinilo o transfer por pieza? (0 si no lleva)",
    "minutos_otros_pasos": "Además del acabado, ¿cuántos minutos por pieza se van en "
                           "preparación, pulido, cargue de horno y empaque?",
    "volumen_referencia":  "¿Cuántas piezas al mes está produciendo el taller?",
    "pct_gerente_produccion": ("¿Qué parte del tiempo de la gerente se va en producción "
                               "—planear, supervisar, calidad— y no en ventas o plata?"),
    "margen_pct":          "¿Qué margen quieres aplicar sobre el costo? (en %)",
}

# Tiempos estándar en minutos por pieza, por etapa / tamaño / dificultad, como los
# plantea el Discovery. None = no medido todavía; el motor lo dice, no lo estima.
#
# El taller compra el bizcocho, así que la etapa de MODELADO (placa, vaciado,
# retornear, oreja, pulir crudo, cargue del horno de bizcocho) no aplica y no está.
TIEMPOS_ACABADO = {   # esmalte color + esmalte transparente, letras y reverso
    "XS": {"facil": 4.0,  "medio": 10.0, "dificil": 20.0},
    "S":  {"facil": 6.5,  "medio": 12.6, "dificil": 23.0},
    "M":  {"facil": 9.5,  "medio": 14.7, "dificil": 23.0},
    "L":  {"facil": None, "medio": 18.3, "dificil": 26.2},
    "XL": {"facil": None, "medio": 26.0, "dificil": None},
}

_VACIA = {t: {"facil": None, "medio": None, "dificil": None}
          for t in ["XS", "S", "M", "L", "XL"]}

# Transformar la arcilla en la forma del producto. Solo aplica cuando la pieza NO
# se compra en bizcocho: de 36 productos analizados en el Discovery, uno solo
# llevaba modelado. Sin medir.
TIEMPOS_MODELADO = {t: dict(d) for t, d in _VACIA.items()}
# Revisión final, ajustes menores, limpieza y empaque. Sin medir.
TIEMPOS_TERMINADO = {t: dict(d) for t, d in _VACIA.items()}

# Los cuatro procesos del Discovery. La Quema no va acá porque no es tiempo por
# pieza sino por hornada: vive en HORNO.
ETAPAS_TIEMPO = {
    "Modelado":                     TIEMPOS_MODELADO,
    "Acabado":                      TIEMPOS_ACABADO,
    "Terminado, calidad y empaque": TIEMPOS_TERMINADO,
}
ETAPAS_RENOMBRADAS = {          # para leer hojas y bases viejas
    "Preparación del bizcocho": None,            # se disolvió dentro de Acabado
    "Terminado y empaque": "Terminado, calidad y empaque",
}
PESTANA_TIEMPOS = "Tiempos Estándar"

TAMANOS = list(TIEMPOS_ACABADO.keys())
DIFICULTADES = ["facil", "medio", "dificil"]

# Discovery: la dificultad de acabado se puntúa por % de superficie pintada y
# número de tintas. Bajo <= 1 punto, Medio 2-3, Alto 4+.
def grado_acabado(pct_pintado: float, num_tintas: int, solo_relieve: bool = False) -> str:
    """Traduce '60% pintado, 3 tintas' a 'dificil'. Ver Discovery, sección Estándares.

    Cada dimensión aporta 0, 1 o 2 puntos (grado 1, 2 o 3 del Discovery menos uno).
    Con la escala 1/2/3 el mínimo posible sería 2 y el nivel "Bajo: 1 o menos" del
    Discovery nunca se alcanzaría, así que la escala es 0/1/2.
      · Superficie pintada: 0-29% = 0 · 30-59% = 1 · 60-100% = 2
      · Tintas:             0-1 = 0   · 2-3 = 1     · 4+ = 2
      · Pintura solo sobre el relieve: resta 1 punto.
    Total: Bajo <= 1 · Medio 2-3 · Alto 4+
    """
    puntos = 2 if pct_pintado >= 60 else (1 if pct_pintado >= 30 else 0)
    puntos += 2 if num_tintas >= 4 else (1 if num_tintas >= 2 else 0)
    if solo_relieve:
        puntos -= 1

    return "facil" if puntos <= 1 else ("medio" if puntos <= 3 else "dificil")


def grado_modelado(pct_relieve: float, apliques: int, tecnica: int = 0) -> str:
    """Dificultad del MODELADO, según el Discovery (sección Estándares).

    Tres dimensiones, cada una de 0 a 2 puntos (el grado del Discovery menos uno):
      · Relieve:  0-12,5% = 0 · 12,6-25% = 1 · 25,1-60% = 2
      · Apliques: 0-1 = 0     · 2-3 = 1      · 4+ = 2
      · Técnica:  la define el taller; el Discovery la nombra pero no le pone escala.
    Total: Bajo <= 2 · Medio 3-4 · Alto 5+ (por eso la escala es 0/1/2: con 1/2/3
    el mínimo sería 3 y "Bajo: 2 o menos" no existiría).
    """
    puntos = 2 if pct_relieve > 25 else (1 if pct_relieve > 12.5 else 0)
    puntos += 2 if apliques >= 4 else (1 if apliques >= 2 else 0)
    puntos += max(0, min(2, int(tecnica or 0)))
    return "facil" if puntos <= 2 else ("medio" if puntos <= 4 else "dificil")


# Quema y capacidad de horno (Discovery, Frente 1). La quema no es un tiempo por
# pieza: es una hornada con su temperatura y su enfriamiento, y el horno cabe un
# número distinto de piezas según el tamaño. De ahí sale el tope de producción.
HORNO_DEFECTO = {
    "capacidad_XS": 0, "capacidad_S": 0, "capacidad_M": 0,
    "capacidad_L": 0, "capacidad_XL": 0,
    "quema1_horas": 0.0, "quema1_temperatura": 0, "quema1_enfriamiento_horas": 0.0,
    "quema2_horas": 0.0, "quema2_temperatura": 0, "quema2_enfriamiento_horas": 0.0,
}


PARAMS_DEFECTO.update(HORNO_DEFECTO)


def hornadas(cantidad: int, tamano: str, params: dict) -> int:
    """Cuántas hornadas necesita ese pedido. 0 = todavía no se sabe la capacidad."""
    cupo = float(params.get("capacidad_" + str(tamano).upper(), 0) or 0)
    if cupo <= 0:
        return 0
    import math
    return int(math.ceil(int(cantidad) / cupo))


def _rango(pestana: str, celdas: str) -> str:
    """'Parámetros Cotizador'!A2:B60 — las comillas son obligatorias cuando el
    nombre de la pestaña tiene espacios; sin ellas la API no parsea el rango."""
    return f"'{pestana}'!{celdas}"


def _fmt(n) -> str:
    return f"${int(round(n)):,}".replace(",", ".")


def fijos_locativos_mes(params: dict) -> float:
    """Arriendo y servicios que carga producción. Los servicios incluyen las quemas,
    así que su % de uso puede ser mayor que el del local."""
    return (float(params["arriendo_mes"]) * float(params["pct_uso_local"]) / 100.0
            + float(params["servicios_mes"]) * float(params["pct_uso_servicios"]) / 100.0)


def parametros_pendientes(params: dict = None) -> list:
    """Parámetros preguntables que siguen en cero, en orden de impacto en el precio."""
    params = params or cargar_parametros()
    pendientes = []
    if not float(params.get("costo_bizcocho", 0) or 0):
        pendientes.append("costo_bizcocho")
    # El esmalte está resuelto si hay onzas O valor en pesos.
    if not (float(params.get("oz_esmalte_por_pieza", 0) or 0)
            or float(params.get("costo_esmaltes", 0) or 0)):
        pendientes.append("oz_esmalte_por_pieza")
    # El empaque ya no se pregunta como parámetro: va por pedido, en la cotización.
    if not float(params.get("minutos_otros_pasos", 0) or 0):
        pendientes.append("minutos_otros_pasos")
    return pendientes


def cargar_parametros() -> dict:
    """Lee la pestaña de parámetros. Si no se puede, usa los valores de respaldo
    y lo deja anotado en _origen para que la cotización lo advierta."""
    params = dict(PARAMS_DEFECTO)
    params["_origen"] = "respaldo"
    try:
        from sheets import leer_sheet_numericos
        filas = leer_sheet_numericos(_rango(PESTANA_PARAMS, "A2:B60"),
                                     sheet_id=COTIZADOR_SHEET_ID)
        leidos = 0
        for fila in filas:
            if len(fila) < 2 or not str(fila[0]).strip():
                continue
            clave = str(fila[0]).strip()
            if clave not in PARAMS_DEFECTO:
                continue
            valor = fila[1]
            params[clave] = valor if clave == "margen_modo" else float(valor or 0)
            leidos += 1
        if leidos:
            params["_origen"] = "hoja"
    except Exception as e:
        print(f"[cotizador] Usando parámetros de respaldo ({e})")
    return params


def cargar_tiempos() -> dict:
    """Lee la pestaña de tiempos estándar. Sin ella, usa las tablas de respaldo."""
    etapas = {nombre: {t: dict(d) for t, d in tabla.items()}
              for nombre, tabla in ETAPAS_TIEMPO.items()}
    try:
        from sheets import leer_sheet_numericos
        filas = leer_sheet_numericos(_rango(PESTANA_TIEMPOS, "A2:E40"),
                                     sheet_id=COTIZADOR_SHEET_ID)
        for fila in filas:
            if len(fila) < 3:
                continue
            etapa, tamano = str(fila[0]).strip(), str(fila[1]).strip().upper()
            if etapa not in etapas or tamano not in TAMANOS:
                continue
            for i, dif in enumerate(DIFICULTADES, start=2):
                valor = fila[i] if len(fila) > i else ""
                if str(valor).strip() != "":
                    etapas[etapa][tamano][dif] = float(valor)
    except Exception as e:
        print(f"[cotizador] Tiempos de respaldo ({e})")
    return etapas


def asegurar_pestana_parametros() -> str:
    """Crea la pestaña de parámetros con los valores actuales si todavía no existe."""
    from sheets import crear_pestana, escribir_rango
    respuesta = crear_pestana(PESTANA_PARAMS, sheet_id=COTIZADOR_SHEET_ID)
    if "creada" not in respuesta:
        return respuesta
    filas = [["Parámetro", "Valor", "Notas"]]
    filas += [[c, v, PARAMS_PREGUNTABLES.get(c, "")] for c, v in PARAMS_DEFECTO.items()]
    escritura = escribir_rango(_rango(PESTANA_PARAMS, f"A1:C{len(filas)}"), filas,
                               sheet_id=COTIZADOR_SHEET_ID)
    return respuesta if not escritura.startswith("Error") else escritura


def asegurar_pestana_tiempos() -> str:
    """Crea la pestaña de tiempos con todas las filas (etapa x tamaño) si no existe."""
    from sheets import crear_pestana, escribir_rango
    respuesta = crear_pestana(PESTANA_TIEMPOS, sheet_id=COTIZADOR_SHEET_ID)
    if "creada" not in respuesta:
        return respuesta
    filas = [["Etapa", "Tamaño", "Fácil", "Medio", "Difícil"]]
    for etapa, tabla in ETAPAS_TIEMPO.items():
        for tam in TAMANOS:
            fila = [etapa, tam]
            fila += [tabla[tam][d] if tabla[tam][d] is not None else "" for d in DIFICULTADES]
            filas.append(fila)
    escribir_rango(_rango(PESTANA_TIEMPOS, f"A1:E{len(filas)}"), filas,
                   sheet_id=COTIZADOR_SHEET_ID)
    return respuesta


def guardar_tiempo(etapa: str, tamano: str, dificultad: str, minutos: float) -> str:
    """Guarda un tiempo estándar en la pestaña de tiempos."""
    etapa = next((e for e in ETAPAS_TIEMPO if e.lower() == str(etapa).strip().lower()), "")
    if not etapa:
        return f"Etapa no válida. Las que hay: {', '.join(ETAPAS_TIEMPO)}"
    tamano = str(tamano).strip().upper()
    dificultad = str(dificultad).strip().lower()
    if tamano not in TAMANOS or dificultad not in DIFICULTADES:
        return f"Usa tamaño {'/'.join(TAMANOS)} y dificultad {'/'.join(DIFICULTADES)}"

    try:
        from sheets import leer_sheet_numericos, escribir_rango
        asegurar_pestana_tiempos()
        filas = leer_sheet_numericos(_rango(PESTANA_TIEMPOS, "A1:B40"),
                                     sheet_id=COTIZADOR_SHEET_ID)
        destino = None
        for i, fila in enumerate(filas, start=1):
            if (len(fila) >= 2 and str(fila[0]).strip() == etapa
                    and str(fila[1]).strip().upper() == tamano):
                destino = i
                break
        if destino is None:
            destino = len(filas) + 1
            escribir_rango(_rango(PESTANA_TIEMPOS, f"A{destino}:B{destino}"),
                           [[etapa, tamano]], sheet_id=COTIZADOR_SHEET_ID)
        columna = {"facil": "C", "medio": "D", "dificil": "E"}[dificultad]
        escritura = escribir_rango(_rango(PESTANA_TIEMPOS, f"{columna}{destino}"),
                                   [[float(minutos)]], sheet_id=COTIZADOR_SHEET_ID)
        if escritura.startswith("Error"):
            return f"❌ No se pudo guardar: {_motivo(escritura)}"
        return f"✅ Guardado: {etapa} · {tamano} · {dificultad} = {minutos} min"
    except Exception as e:
        return f"❌ No se pudo guardar el tiempo: {e}"


def guardar_parametro(clave: str, valor) -> str:
    """Escribe un parámetro en la hoja para que quede guardado de una vez por todas."""
    if clave not in PARAMS_DEFECTO:
        return (f"'{clave}' no es un parámetro del cotizador. "
                f"Los que se pueden guardar: {', '.join(sorted(PARAMS_DEFECTO))}")
    try:
        from sheets import leer_sheet_numericos, escribir_rango
        asegurar_pestana_parametros()
        filas = leer_sheet_numericos(_rango(PESTANA_PARAMS, "A1:A60"),
                                     sheet_id=COTIZADOR_SHEET_ID)
        fila_destino = None
        for i, fila in enumerate(filas, start=1):
            if fila and str(fila[0]).strip() == clave:
                fila_destino = i
                break
        if fila_destino is None:
            fila_destino = len(filas) + 1
            escribir_rango(_rango(PESTANA_PARAMS, f"A{fila_destino}"), [[clave]],
                           sheet_id=COTIZADOR_SHEET_ID)
        # Bug 2: antes se daba por guardado sin mirar el resultado, así que un
        # error de la API se reportaba como éxito y el precio no cambiaba.
        escritura = escribir_rango(_rango(PESTANA_PARAMS, f"B{fila_destino}"), [[valor]],
                                   sheet_id=COTIZADOR_SHEET_ID)
        if escritura.startswith("Error"):
            return f"❌ No se pudo guardar {clave}: {_motivo(escritura)}"
        return f"✅ Guardado: {clave} = {valor}"
    except Exception as e:
        return f"No se pudo guardar {clave}: {e}"


# Datos que se dan POR LÍNEA y mandan sobre el parámetro general. Un plato lleva
# más bizcocho y más esmalte que un pocillo: cotizar los dos con el mismo costo de
# material era la mayor imprecisión del motor.
AJUSTES_LINEA = [
    "costo_bizcocho", "oz_esmalte_por_pieza", "costo_esmaltes", "costo_vinilo",
    "lleva_vinilo",                     # la pieza va con vinilo adhesivo o no
    "margen_pct",                       # sobreescriben el parámetro general
    "minutos_extra",                    # se suman al tiempo de la pieza
    "descuento_pct",                    # baja el total de esa línea
]
# El EMPAQUE no está acá: no es un costo de la pieza sino del pedido (Camilo,
# 2026-09-18). Se cotiza una vez, se reparte entre las piezas del pedido y así
# entra al costo unitario y lleva margen como cualquier otro costo.


def cotizar(cantidad: int, tamano: str, dificultad: str = "medio",
            minutos_acabado: float = None, params: dict = None,
            producto: str = "", tiempos: dict = None,
            ajustes: dict = None, notas: str = "",
            cantidad_pedido: int = None, empaque_pedido: float = None,
            modelado: bool = False) -> dict:
    """Calcula el precio de una pieza y del pedido. Devuelve el desglose completo.

    `ajustes` son los datos propios de esta línea (ver AJUSTES_LINEA). `cantidad_pedido`
    es el total de piezas del pedido completo: sirve para que la advertencia de volumen
    mire el pedido entero y para repartir el empaque. `empaque_pedido` es lo que cuesta
    empacar TODO el pedido; se divide entre esas piezas. `modelado` = la pieza se
    modela en el taller en vez de comprarse en bizcocho: solo entonces cuenta el
    tiempo de esa etapa.
    """
    params = dict(params or cargar_parametros())
    ajustes = {k: v for k, v in (ajustes or {}).items()
               if k in AJUSTES_LINEA and v not in (None, "")}
    # Si la línea trae el esmalte en pesos, las onzas del parámetro general no aplican.
    if "costo_esmaltes" in ajustes and "oz_esmalte_por_pieza" not in ajustes:
        params["oz_esmalte_por_pieza"] = 0
    for clave, valor in ajustes.items():
        if clave in PARAMS_DEFECTO:
            params[clave] = float(valor)
    lleva_vinilo = bool(ajustes.pop("lleva_vinilo", False))
    minutos_extra = float(ajustes.get("minutos_extra", 0) or 0)
    descuento_pct = float(ajustes.get("descuento_pct", 0) or 0)
    piezas_pedido = int(cantidad_pedido or cantidad) or 1
    if empaque_pedido is not None:
        params["costo_empaque"] = float(empaque_pedido) / piezas_pedido
    advertencias = []

    if params.get("_origen") == "respaldo":
        advertencias.append(
            "No pude leer la pestaña de parámetros del Cotizador Interno: estoy usando "
            "los valores de respaldo. Lo que cambies en la hoja no se está aplicando.")

    tamano = (tamano or "M").upper()
    if tamano not in TIEMPOS_ACABADO:
        raise ValueError(f"Tamaño '{tamano}' no válido. Usa: {', '.join(TAMANOS)}")
    dificultad = (dificultad or "medio").lower()
    if dificultad not in DIFICULTADES:
        raise ValueError(f"Dificultad '{dificultad}' no válida. Usa: {', '.join(DIFICULTADES)}")

    # ── Tiempo: se suman las etapas que apliquen ────────────────────────────
    etapas = tiempos or cargar_tiempos()

    if minutos_acabado is None:
        minutos_acabado = etapas["Acabado"][tamano][dificultad]
    if minutos_acabado is None:
        raise ValueError(
            f"No hay tiempo de acabado medido para {tamano} / {dificultad}. "
            f"Pásalo a mano con minutos_acabado, o mídelo en planta.")

    minutos_por_etapa = {"Acabado": float(minutos_acabado)}
    sin_medir = []
    for nombre, tabla in etapas.items():
        if nombre == "Acabado":
            continue
        if nombre == "Modelado" and not modelado:
            continue        # la pieza se compra en bizcocho
        valor = tabla.get(tamano, {}).get(dificultad)
        if valor is None:
            sin_medir.append(nombre)
        else:
            minutos_por_etapa[nombre] = float(valor)

    # Respaldo: un único número para todo lo que no es acabado.
    minutos_sueltos = float(params.get("minutos_otros_pasos", 0) or 0)
    if sin_medir and minutos_sueltos:
        minutos_por_etapa["Otros pasos (estimado a ojo)"] = minutos_sueltos
        sin_medir = []
    if sin_medir:
        advertencias.append(
            "Sin medir: " + ", ".join(f"{e.lower()} ({tamano}/{dificultad})" for e in sin_medir)
            + ". Solo se está cobrando el acabado, así que el tiempo real es mayor.")

    # El adhesivo se pinta por encima: mismo esmalte, menos tiempo.
    ahorro = float(params.get("minutos_ahorro_vinilo", 0) or 0) if lleva_vinilo else 0.0
    if ahorro:
        minutos_por_etapa["Ahorro por vinilo"] = -ahorro
    elif lleva_vinilo:
        advertencias.append(
            "La pieza lleva vinilo, que se pinta más rápido, pero todavía no está medido "
            "cuánto tiempo ahorra: se está cobrando el acabado completo.")
    if minutos_extra:
        minutos_por_etapa["Ajuste manual"] = minutos_extra

    minutos_totales = max(0.0, sum(minutos_por_etapa.values()))

    # El costo por hora puesto a mano manda sobre el deducido del salario: el
    # salario mensual incluye gente que no está produciendo piezas.
    valor_hora = float(params.get("costo_hora_mo", 0) or 0)
    if not valor_hora:
        horas_mes  = float(params["horas_semanales"]) * float(params["semanas_mes"])
        valor_hora = float(params["salario_mensual"]) / horas_mes if horas_mes else 0
    costo_mo = (minutos_totales / 60.0) * valor_hora

    # ── Materiales y proceso ────────────────────────────────────────────────
    # El esmalte se puede cargar en pesos por pieza o en onzas: si hay onzas, mandan.
    onzas = float(params.get("oz_esmalte_por_pieza", 0) or 0)
    costo_esmaltes = (onzas * precio_unitario_material("esmalte_blanco")
                      if onzas else float(params["costo_esmaltes"]))
    # El vinilo solo se cobra si la pieza lo lleva.
    costo_vinilo = float(params["costo_vinilo"]) if lleva_vinilo else 0.0
    materiales = float(params["costo_bizcocho"]) + costo_esmaltes + costo_vinilo
    quemas = float(params.get("costo_quema", 0) or 0)
    empaque = float(params["costo_empaque"])

    # Las quemas no se listan: su energía ya va dentro de servicios públicos.
    faltantes = [n for n, v in [
        ("bizcocho", params["costo_bizcocho"]),
        ("esmaltes", costo_esmaltes),
        ("empaque del pedido", params["costo_empaque"])] if float(v) == 0]
    if faltantes:
        advertencias.append("Sin costo cargado: " + ", ".join(faltantes) +
                            ". El precio sale por debajo del real.")

    costo_directo = materiales + costo_mo + quemas + empaque
    desperdicio   = costo_directo * float(params["desperdicio_pct"]) / 100.0
    directo_total = costo_directo + desperdicio

    # ── Fijos: repartidos entre el volumen de referencia, no entre el pedido ─
    volumen = float(params["volumen_referencia"]) or 1
    mercadeo  = directo_total * float(params["mercadeo_pct"]) / 100.0
    arriendo  = fijos_locativos_mes(params) / volumen
    gerente_produccion = (float(params.get("sueldo_gerente_mes", 0) or 0)
                          * float(params.get("pct_gerente_produccion", 0) or 0) / 100.0)
    admin     = (float(params["gastos_admin_mes"]) + gerente_produccion) / volumen
    gran_total = directo_total + mercadeo + arriendo + admin

    if piezas_pedido < volumen * 0.2:
        advertencias.append(
            f"El pedido ({piezas_pedido} piezas) es chico frente al volumen de referencia "
            f"({int(volumen)}/mes). Los fijos se reparten igual, así que este precio "
            f"solo se sostiene si el mes se llena con otros pedidos.")

    # ── Precio ──────────────────────────────────────────────────────────────
    margen = float(params["margen_pct"]) / 100.0
    if str(params["margen_modo"]).strip().lower() == "sobre_venta":
        if margen >= 1:
            raise ValueError("Un margen sobre venta del 100% o más no tiene solución.")
        pvp = gran_total / (1 - margen)
    else:
        pvp = gran_total * (1 + margen)

    iva     = pvp * float(params["iva_pct"]) / 100.0
    con_iva = pvp + iva

    bruto_linea     = pvp * cantidad
    descuento_linea = bruto_linea * descuento_pct / 100.0
    total_linea     = bruto_linea - descuento_linea

    # ── Los costos agrupados como los pide contabilidad: materia prima, mano de
    #    obra e indirectos, con el desperdicio aparte porque sale de las dos
    #    primeras (asesor de producción y costos, 2026-09-19).
    indirectos = mercadeo + arriendo + admin
    grupos = [
        ("Materia prima", materiales + empaque + quemas, [
            ("Bizcocho", float(params["costo_bizcocho"])),
            ("Esmaltes", costo_esmaltes),
            ("Vinilo o transfer", costo_vinilo),
            ("Empaque (del pedido, por pieza)", empaque),
            ("Quema", quemas),
        ]),
        ("Mano de obra", costo_mo, [
            (f"{round(minutos_totales, 1)} min a {_fmt(valor_hora)} la hora", costo_mo),
        ]),
        ("Desperdicio", desperdicio, [
            (f"{float(params['desperdicio_pct']):g}% sobre materia prima y mano de obra",
             desperdicio),
        ]),
        ("Costos indirectos", indirectos, [
            ("Mercadeo", mercadeo),
            ("Arriendo y servicios", arriendo),
            (f"Gerencia ({float(params.get('pct_gerente_produccion', 0) or 0):g}% de su tiempo) "
             f"y administración", admin),
        ]),
    ]

    return {
        "producto": producto, "cantidad": int(cantidad),
        "tamano": tamano, "dificultad": dificultad,
        "minutos_acabado": round(float(minutos_acabado), 1),
        "minutos_totales": round(minutos_totales, 1),
        "minutos_por_etapa": {k: round(v, 1) for k, v in minutos_por_etapa.items()},
        "valor_hora": round(valor_hora),
        "desglose": [
            ("Materiales (bizcocho, esmaltes, vinilo)", materiales),
            ("Mano de obra", costo_mo),
            ("Quema del esmalte", quemas),
            ("Empaque (del pedido, por pieza)", empaque),
            ("Desperdicio", desperdicio),
            ("Mercadeo", mercadeo),
            ("Arriendo y servicios (incluye quemas)", arriendo),
            ("Gastos administrativos", admin),
        ],
        "grupos": [(titulo, round(total), [(e, round(v)) for e, v in detalle])
                   for titulo, total, detalle in grupos],
        "materia_prima": round(materiales + empaque + quemas),
        "mano_de_obra":  round(costo_mo),
        "indirectos":    round(indirectos),
        "costo_directo": round(costo_directo),
        "directo_total": round(directo_total),
        "gran_total":    round(gran_total),
        "pvp_unitario":  round(pvp),
        "iva_unitario":  round(iva),
        "precio_con_iva": round(con_iva),
        "margen_unitario": round(pvp - gran_total),
        "descuento_pct":       descuento_pct,
        "descuento_linea":     round(descuento_linea),
        "bruto_linea":         round(bruto_linea),
        "total_linea":         round(total_linea),
        "minutos_extra":       round(minutos_extra, 1),
        "lleva_vinilo":        lleva_vinilo,
        "ajustes":             ajustes,
        "notas":               notas,
        "total_pedido_sin_iva": round(total_linea),
        "total_pedido_con_iva": round(total_linea * (1 + float(params["iva_pct"]) / 100.0)),
        "volumen_referencia": int(volumen),
        "modelado": bool(modelado),
        "hornadas": hornadas(cantidad, tamano, params),
        "advertencias": advertencias,
        "params_usados": {k: v for k, v in params.items() if not k.startswith("_")},
    }



# ── Cotización de varios productos en un mismo pedido ───────────────────────
# Un cliente casi nunca pide una sola referencia: pide 40 tazas, 20 platos y 10
# materas. Cada línea se cotiza con SU tamaño, SU decoración y SUS materiales; lo
# que se comparte es el pedido — descuento, urgencia, envío e IVA.
CONDICIONES_DEFECTO = {
    "empaque":       0.0,    # lo que cuesta empacar TODO el pedido; se reparte por pieza
    "descuento_pct": 0.0,    # descuento comercial sobre todo el pedido
    "urgencia_pct":  0.0,    # recargo por entrega express
    "envio":         0.0,    # flete, si se cobra
    "desarrollo":    0.0,    # molde, prueba o diseño: se cobra una sola vez
    "cobrar_iva":    True,
    "validez_dias":  15,
    "plazo":         "4-6 semanas hábiles",
    "anticipo_pct":  50,
    "notas":         "",
}


def cotizar_pedido(lineas: list, condiciones: dict = None, params: dict = None,
                   tiempos: dict = None, cliente: str = "") -> dict:
    """Cotiza varias referencias de una vez y arma los totales del pedido.

    Cada línea es un dict: producto, cantidad, tamano, y la decoración por
    pct_pintado/num_tintas/solo_relieve (o dificultad directa). Puede traer también
    cualquiera de los AJUSTES_LINEA y `notas`.

    Los parámetros y los tiempos se leen UNA vez y se pasan a todas las líneas: leerlos
    por línea serían 20 llamadas a Sheets para un pedido de 10 referencias.
    """
    if not lineas:
        raise ValueError("Un pedido necesita al menos una línea.")

    cond = dict(CONDICIONES_DEFECTO)
    cond.update({k: v for k, v in (condiciones or {}).items() if v not in (None, "")})

    params = params or cargar_parametros()
    tiempos = tiempos or cargar_tiempos()
    piezas = sum(int(l.get("cantidad", 0) or 0) for l in lineas)

    resultados, advertencias = [], []
    for l in lineas:
        dificultad = l.get("dificultad") or ""
        if not dificultad:
            dificultad = grado_acabado(float(l.get("pct_pintado", 50) or 0),
                                       int(l.get("num_tintas", 0) or 0),
                                       bool(l.get("solo_relieve")))
        ajustes = {k: l[k] for k in AJUSTES_LINEA if k in l}
        r = cotizar(int(l.get("cantidad", 1) or 1), l.get("tamano", "M"), dificultad,
                    l.get("minutos_acabado"), params=params,
                    producto=l.get("producto", ""), tiempos=tiempos,
                    ajustes=ajustes, notas=l.get("notas", ""),
                    cantidad_pedido=piezas,
                    empaque_pedido=float(cond["empaque"] or 0) or None,
                    modelado=bool(l.get("modelado")))
        r["pct_pintado"] = l.get("pct_pintado")
        r["num_tintas"] = l.get("num_tintas")
        resultados.append(r)
        # Las advertencias se repiten línea por línea; en el pedido van una sola vez.
        for a in r["advertencias"]:
            if a not in advertencias:
                advertencias.append(a)

    # "Sin medir" sale una vez por tamaño/dificultad: en un pedido de 10 referencias
    # serían 10 avisos diciendo lo mismo. Se colapsan en uno.
    sin_medir = [a for a in advertencias if a.startswith("Sin medir:")]
    if len(sin_medir) > 1:
        advertencias = [a for a in advertencias if not a.startswith("Sin medir:")]
        advertencias.insert(0, "Sin medir: preparación del bizcocho y terminado y empaque, "
                               "en varias referencias. Solo se está cobrando el acabado, "
                               "así que el tiempo real por pieza es mayor.")

    subtotal   = sum(r["total_linea"] for r in resultados)
    urgencia   = subtotal * float(cond["urgencia_pct"]) / 100.0
    descuento  = (subtotal + urgencia) * float(cond["descuento_pct"]) / 100.0
    envio      = float(cond["envio"] or 0)
    desarrollo = float(cond["desarrollo"] or 0)
    base       = subtotal + urgencia - descuento + envio + desarrollo
    iva        = base * float(params["iva_pct"]) / 100.0 if cond["cobrar_iva"] else 0.0

    total_hornadas = sum(r["hornadas"] for r in resultados)
    if total_hornadas:
        advertencias.append(
            f"Son {total_hornadas} hornada{'s' if total_hornadas != 1 else ''} de horno. "
            f"Tenlo en cuenta para el plazo de entrega.")

    return {
        "cliente": cliente, "lineas": resultados, "piezas": piezas,
        "hornadas": total_hornadas,
        "condiciones": cond,
        "subtotal":   round(subtotal),
        "urgencia":   round(urgencia),
        "descuento":  round(descuento),
        "envio":      round(envio),
        "desarrollo": round(desarrollo),
        "base":       round(base),
        "iva":        round(iva),
        "total":      round(base + iva),
        "anticipo":   round((base + iva) * float(cond["anticipo_pct"]) / 100.0),
        "advertencias": advertencias,
        "params_usados": {k: v for k, v in params.items() if not k.startswith("_")},
    }


def formato_telegram_pedido(r: dict) -> str:
    """El pedido completo, línea por línea, en texto."""
    cond = r["condiciones"]
    lineas = [f"💰 Cotización{' para ' + r['cliente'] if r['cliente'] else ''} · "
              f"{len(r['lineas'])} referencias · {r['piezas']} piezas", ""]
    for i, l in enumerate(r["lineas"], start=1):
        titulo = l["producto"] or f"Referencia {i}"
        lineas.append(f"{i}. {titulo} — {l['cantidad']} x {l['tamano']}, "
                      f"acabado {l['dificultad']}")
        detalle = f"   {_fmt(l['pvp_unitario'])} c/u"
        if l["descuento_pct"]:
            detalle += f" · -{l['descuento_pct']:g}%"
        lineas.append(detalle + f" = {_fmt(l['total_linea'])}")
    lineas += ["", f"Subtotal: {_fmt(r['subtotal'])}"]
    if r["urgencia"]:
        lineas.append(f"Recargo por urgencia ({cond['urgencia_pct']:g}%): {_fmt(r['urgencia'])}")
    if r["descuento"]:
        lineas.append(f"Descuento ({cond['descuento_pct']:g}%): -{_fmt(r['descuento'])}")
    if r["envio"]:
        lineas.append(f"Envío: {_fmt(r['envio'])}")
    if r["desarrollo"]:
        lineas.append(f"Molde o desarrollo: {_fmt(r['desarrollo'])}")
    if r["iva"]:
        lineas.append(f"IVA: {_fmt(r['iva'])}")
    lineas += [f"➡️ TOTAL: {_fmt(r['total'])}",
               f"Anticipo {cond['anticipo_pct']:g}%: {_fmt(r['anticipo'])} · "
               f"entrega {cond['plazo']} · validez {cond['validez_dias']} días"]
    if r["advertencias"]:
        lineas.append("")
        lineas += [f"⚠️ {a}" for a in r["advertencias"]]
    return "\n".join(lineas)


PESTANA_INDICE = "Cotizaciones"


def _nombre_pestana(r: dict, numero: str = "") -> str:
    """Nombre corto y único para la pestaña de una cotización."""
    from datetime import date
    base = numero or f"Cot {date.today().strftime('%d-%m')}"
    producto = (r.get("producto") or "").strip()
    if producto:
        base = f"{base} {producto}"
    base = base.replace("/", "-").replace("\\", "-")[:80]

    try:
        from sheets import listar_pestanas
        existentes = listar_pestanas(sheet_id=COTIZACIONES_SHEET_ID)
    except Exception:
        existentes = ""
    if base not in existentes:
        return base
    for i in range(2, 50):
        candidato = f"{base} ({i})"
        if candidato not in existentes:
            return candidato
    return base


def guardar_hoja_cotizacion(r: dict, numero: str = "") -> str:
    """Deja una pestaña con el desglose completo de una cotización, para poder
    auditar de dónde salió el precio. Registra también una fila en el índice."""
    from datetime import date
    from sheets import agregar_fila, crear_pestana, escribir_rango

    hoy = date.today().strftime("%d/%m/%Y")
    pestana = _nombre_pestana(r, numero)
    respuesta = crear_pestana(pestana, sheet_id=COTIZACIONES_SHEET_ID)
    if respuesta.startswith("Error"):
        return f"❌ No se pudo crear la hoja: {_motivo(_explicar_403(respuesta))}"

    p = r.get("params_usados", {})
    filas = [
        [f"COTIZACIÓN — {r.get('producto') or 'Pieza'}", "", ""],
        ["Fecha", hoy, ""],
        ["Número", numero, ""],
        ["", "", ""],
        ["LA PIEZA", "", ""],
        ["Cantidad", r["cantidad"], "piezas"],
        ["Tamaño", r["tamano"], ""],
        ["Dificultad del acabado", r["dificultad"], ""],
        ["Minutos de acabado", r["minutos_acabado"], "estándar del Discovery"],
    ]
    filas += [[f"Minutos — {etapa.lower()}", valor, ""]
              for etapa, valor in r.get("minutos_por_etapa", {}).items()
              if etapa != "Acabado"]
    filas += [
        ["Minutos totales por pieza", r["minutos_totales"], ""],
        ["Valor hora de taller", r["valor_hora"], "salario / horas del mes"],
        ["", "", ""],
        ["COSTO POR PIEZA", "", ""],
    ]
    for titulo, total, detalle in r["grupos"]:
        filas.append([titulo.upper(), round(total), ""])
        if len(detalle) > 1:
            filas += [["  " + etiqueta, round(valor), ""] for etiqueta, valor in detalle if valor]
    filas += [
        ["Costo + gastos por pieza", r["gran_total"], ""],
        ["", "", ""],
        ["PRECIO", "", ""],
        [f"Margen ({p.get('margen_pct', 0)}% sobre el costo)", r["margen_unitario"], ""],
        ["PVP por pieza (sin IVA)", r["pvp_unitario"], ""],
        [f"IVA ({p.get('iva_pct', 0)}%)", r["iva_unitario"], ""],
        ["Precio por pieza con IVA", r["precio_con_iva"], ""],
        ["", "", ""],
        ["EL PEDIDO", "", ""],
        ["Total sin IVA", r["total_pedido_sin_iva"], ""],
        ["Total con IVA", r["total_pedido_con_iva"], ""],
    ]

    if r.get("advertencias"):
        filas += [["", "", ""], ["OJO", "", ""]]
        filas += [["", a, ""] for a in r["advertencias"]]

    filas += [["", "", ""], ["PARÁMETROS USADOS", "", "para poder reproducir el cálculo"]]
    filas += [[clave, valor, ""] for clave, valor in sorted(p.items())]

    escritura = escribir_rango(_rango(pestana, f"A1:C{len(filas)}"), filas,
                               sheet_id=COTIZACIONES_SHEET_ID)
    if escritura.startswith("Error"):
        return f"❌ No se pudo escribir la hoja: {_motivo(escritura)}"

    # Índice, para verlas todas de un vistazo
    if "creada" in crear_pestana(PESTANA_INDICE, sheet_id=COTIZACIONES_SHEET_ID):
        escribir_rango(_rango(PESTANA_INDICE, "A1:H1"),
                       [["Fecha", "Número", "Producto", "Cantidad", "Tamaño",
                         "PVP sin IVA", "Total pedido con IVA", "Hoja"]],
                       sheet_id=COTIZACIONES_SHEET_ID)
    agregar_fila(_rango(PESTANA_INDICE, "A:H"),
                 [hoy, numero, r.get("producto", ""), r["cantidad"], r["tamano"],
                  r["pvp_unitario"], r["total_pedido_con_iva"], pestana],
                 sheet_id=COTIZACIONES_SHEET_ID)

    return f"📄 Detalle guardado en la pestaña '{pestana}' del Cotizador Interno."


def _motivo(respuesta: str) -> str:
    """El texto de sheets ya viene explicado; solo sobra el prefijo técnico."""
    texto = str(respuesta)
    return texto[7:] if texto.startswith("Error: ") else texto


def _explicar_403(mensaje: str) -> str:
    """Un 403 de Sheets siempre es lo mismo: la hoja no está compartida con el bot.
    Decir con quién hay que compartirla ahorra la adivinanza."""
    if "403" not in str(mensaje):
        return mensaje
    try:
        from sheets import correo_servicio
        correo = correo_servicio()
    except Exception:
        correo = ""
    detalle = (f" Comparte el Cotizador Interno (con permiso de Editor) con "
               f"{correo}." if correo else
               " Hay que compartir el Cotizador Interno con la cuenta de servicio del bot.")
    return mensaje + detalle


def guardar_hoja_pedido(r: dict, numero: str = "") -> str:
    """Deja una pestaña con el pedido completo: una fila por referencia, los totales y
    los parámetros usados. Es la versión de varias líneas de guardar_hoja_cotizacion."""
    from datetime import date
    from sheets import agregar_fila, crear_pestana, escribir_rango

    hoy = date.today().strftime("%d/%m/%Y")
    cond = r["condiciones"]
    etiqueta = {"producto": (r.get("cliente") or "Pedido")}
    pestana = _nombre_pestana(etiqueta, numero)
    respuesta = crear_pestana(pestana, sheet_id=COTIZACIONES_SHEET_ID)
    if respuesta.startswith("Error"):
        return f"❌ No se pudo crear la hoja: {_motivo(_explicar_403(respuesta))}"

    filas = [
        [f"COTIZACIÓN — {r.get('cliente') or 'Interna'}", "", "", "", "", "", ""],
        ["Fecha", hoy, "Número", numero, "", "", ""],
        ["", "", "", "", "", "", ""],
        ["Producto", "Cantidad", "Tamaño", "Acabado", "Min/pieza", "PVP unitario", "Total línea"],
    ]
    for i, l in enumerate(r["lineas"], start=1):
        filas.append([l["producto"] or f"Referencia {i}", l["cantidad"], l["tamano"],
                      l["dificultad"], l["minutos_totales"], l["pvp_unitario"],
                      l["total_linea"]])
        if l.get("notas"):
            filas.append(["", l["notas"], "", "", "", "", ""])

    filas += [
        ["", "", "", "", "", "", ""],
        ["Subtotal", "", "", "", "", "", r["subtotal"]],
        [f"Recargo urgencia ({cond['urgencia_pct']:g}%)", "", "", "", "", "", r["urgencia"]],
        [f"Descuento ({cond['descuento_pct']:g}%)", "", "", "", "", "", -r["descuento"]],
        ["Envío", "", "", "", "", "", r["envio"]],
        ["Molde o desarrollo", "", "", "", "", "", r["desarrollo"]],
        ["IVA", "", "", "", "", "", r["iva"]],
        ["TOTAL", "", "", "", "", "", r["total"]],
        [f"Anticipo ({cond['anticipo_pct']:g}%)", "", "", "", "", "", r["anticipo"]],
    ]

    if r.get("advertencias"):
        filas += [["", "", "", "", "", "", ""], ["OJO", "", "", "", "", "", ""]]
        filas += [["", a, "", "", "", "", ""] for a in r["advertencias"]]

    filas += [["", "", "", "", "", "", ""],
              ["PARÁMETROS USADOS", "", "", "", "", "", "para reproducir el cálculo"]]
    filas += [[c, v, "", "", "", "", ""] for c, v in sorted(r["params_usados"].items())]

    escritura = escribir_rango(_rango(pestana, f"A1:G{len(filas)}"), filas,
                               sheet_id=COTIZACIONES_SHEET_ID)
    if escritura.startswith("Error"):
        return f"❌ No se pudo escribir la hoja: {_motivo(escritura)}"

    if "creada" in crear_pestana(PESTANA_INDICE, sheet_id=COTIZACIONES_SHEET_ID):
        escribir_rango(_rango(PESTANA_INDICE, "A1:H1"),
                       [["Fecha", "Número", "Producto", "Cantidad", "Tamaño",
                         "PVP sin IVA", "Total pedido con IVA", "Hoja"]],
                       sheet_id=COTIZACIONES_SHEET_ID)
    agregar_fila(_rango(PESTANA_INDICE, "A:H"),
                 [hoy, numero, f"{len(r['lineas'])} referencias — {r.get('cliente', '')}".strip(" —"),
                  r["piezas"], "", r["base"], r["total"], pestana],
                 sheet_id=COTIZACIONES_SHEET_ID)

    return f"📄 Detalle guardado en la pestaña '{pestana}' del Cotizador Interno."


def formato_telegram(r: dict) -> str:
    """Desglose legible. Sirve tanto en Telegram como en consola."""
    titulo = r["producto"] or "Pieza"
    lineas = [
        f"💰 {titulo} · {r['tamano']} · acabado {r['dificultad']} · {r['cantidad']} piezas",
        f"Tiempo: {r['minutos_totales']} min/pieza · hora de taller {_fmt(r['valor_hora'])}",
    ]
    if len(r.get("minutos_por_etapa", {})) > 1:
        lineas.append("  (" + " · ".join(f"{k.lower()} {v}"
                                         for k, v in r["minutos_por_etapa"].items()) + ")")
    lineas.append("")
    for titulo, total, detalle in r["grupos"]:
        if not total:
            continue
        peso = round(total / r["gran_total"] * 100) if r["gran_total"] else 0
        lineas.append(f"  {titulo.upper()}: {_fmt(total)} ({peso}%)")
        for etiqueta, valor in detalle:
            if valor and len(detalle) > 1:
                lineas.append(f"     · {etiqueta}: {_fmt(valor)}")
    lineas += [
        "",
        f"Costo + gastos por pieza: {_fmt(r['gran_total'])}",
        f"Margen: {_fmt(r['margen_unitario'])}",
        f"➡️ PVP sugerido: {_fmt(r['pvp_unitario'])} + IVA = {_fmt(r['precio_con_iva'])}",
        "",
        f"Pedido de {r['cantidad']}: {_fmt(r['total_pedido_sin_iva'])} sin IVA · "
        f"{_fmt(r['total_pedido_con_iva'])} con IVA",
    ]
    if r["advertencias"]:
        lineas.append("")
        for a in r["advertencias"]:
            lineas.append(f"⚠️ {a}")
    return "\n".join(lineas)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Calcula el precio sugerido de una pieza")
    ap.add_argument("--cantidad", type=int, required=True)
    ap.add_argument("--tamano", default="M", choices=TAMANOS + [t.lower() for t in TAMANOS])
    ap.add_argument("--dificultad", default="medio", choices=DIFICULTADES)
    ap.add_argument("--minutos", type=float, default=None, help="minutos de acabado a mano")
    ap.add_argument("--producto", default="")
    args = ap.parse_args()

    print(formato_telegram(cotizar(args.cantidad, args.tamano, args.dificultad,
                                   args.minutos, producto=args.producto)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
