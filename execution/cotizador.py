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

 1. Los costos fijos se reparten entre un VOLUMEN DE REFERENCIA fijo (300
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

# Valores leídos de la hoja el 2026-09-17. Son el respaldo si la pestaña de
# parámetros todavía no existe o el bot aún no tiene acceso al archivo.
PARAMS_DEFECTO = {
    # Mano de obra
    "salario_mensual":        4_000_000,
    "horas_semanales":        48,
    "semanas_mes":            4,
    # Reparto de fijos
    "volumen_referencia":     300,        # piezas/mes — producción real (Camilo, 2026-09-17)
    "gastos_admin_mes":       1_230_000,  # contador 10% + gerente 20% + supervisor 30%
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
    "costo_esmaltes":         0,
    "costo_vinilo":           0,
    "costo_empaque":          0,
    # Las quemas NO son costo directo: su energía ya está dentro de servicios
    # públicos, que se prorratea arriba (Camilo, 2026-09-17). Cargarlas aquí
    # sería contarlas dos veces. Solo se llenan si algún día se mide el consumo
    # por hornada y se saca de servicios.
    "costo_quema_bizcocho":   0,
    "costo_quema_esmalte":    0,
    "costo_quema_transfer":   0,
    # Minutos de los pasos que no son acabado (preparación, pulido, cargue…)
    "minutos_otros_pasos":    0.0,
}

# Lo que el bot puede preguntar y guardar solo. El texto es la pregunta literal.
PARAMS_PREGUNTABLES = {
    "costo_bizcocho":      "¿Cuánto te cuesta el bizcocho por pieza?",
    "costo_esmaltes":      "¿Cuánto cuestan los esmaltes por pieza?",
    "costo_empaque":       "¿Cuánto cuesta el empaque por pieza?",
    "costo_vinilo":        "¿Cuánto cuesta el vinilo o transfer por pieza? (0 si no lleva)",
    "minutos_otros_pasos": "Además del acabado, ¿cuántos minutos por pieza se van en "
                           "preparación, pulido, cargue de horno y empaque?",
    "volumen_referencia":  "¿Cuántas piezas al mes está produciendo el taller?",
    "margen_pct":          "¿Qué margen quieres aplicar sobre el costo? (en %)",
}

# Discovery 2026-09: minutos de ACABADO por pieza. None = no medido todavía.
# XS fácil viene estimado en el propio Discovery a partir de los tamaños vecinos.
TIEMPOS_ACABADO = {
    "XS": {"facil": 4.0,  "medio": 10.0, "dificil": 20.0},
    "S":  {"facil": 6.5,  "medio": 12.6, "dificil": 23.0},
    "M":  {"facil": 9.5,  "medio": 14.7, "dificil": 23.0},
    "L":  {"facil": None, "medio": 18.3, "dificil": 26.2},
    "XL": {"facil": None, "medio": 26.0, "dificil": None},
}

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
    orden = ["costo_bizcocho", "costo_esmaltes", "costo_empaque", "minutos_otros_pasos"]
    return [c for c in orden if float(params.get(c, 0) or 0) == 0]


def cargar_parametros() -> dict:
    """Lee la pestaña de parámetros. Si no se puede, usa los valores de respaldo."""
    params = dict(PARAMS_DEFECTO)
    try:
        from sheets import leer_sheet_numericos
        filas = leer_sheet_numericos(f"{PESTANA_PARAMS}!A2:B60", sheet_id=COTIZADOR_SHEET_ID)
        for fila in filas:
            if len(fila) < 2 or not str(fila[0]).strip():
                continue
            clave = str(fila[0]).strip()
            if clave not in params:
                continue
            valor = fila[1]
            params[clave] = valor if clave == "margen_modo" else float(valor or 0)
    except Exception as e:
        print(f"[cotizador] Usando parámetros de respaldo ({e})")
    return params


def asegurar_pestana_parametros() -> str:
    """Crea la pestaña de parámetros con los valores actuales si todavía no existe."""
    from sheets import crear_pestana, escribir_rango
    respuesta = crear_pestana(PESTANA_PARAMS, sheet_id=COTIZADOR_SHEET_ID)
    if "creada" not in respuesta:
        return respuesta
    filas = [["Parámetro", "Valor", "Notas"]]
    filas += [[c, v, PARAMS_PREGUNTABLES.get(c, "")] for c, v in PARAMS_DEFECTO.items()]
    escribir_rango(f"{PESTANA_PARAMS}!A1:C{len(filas)}", filas, sheet_id=COTIZADOR_SHEET_ID)
    return respuesta


def guardar_parametro(clave: str, valor) -> str:
    """Escribe un parámetro en la hoja para que quede guardado de una vez por todas."""
    if clave not in PARAMS_DEFECTO:
        return (f"'{clave}' no es un parámetro del cotizador. "
                f"Los que se pueden guardar: {', '.join(sorted(PARAMS_DEFECTO))}")
    try:
        from sheets import leer_sheet_numericos, escribir_rango
        asegurar_pestana_parametros()
        filas = leer_sheet_numericos(f"{PESTANA_PARAMS}!A1:A60", sheet_id=COTIZADOR_SHEET_ID)
        fila_destino = None
        for i, fila in enumerate(filas, start=1):
            if fila and str(fila[0]).strip() == clave:
                fila_destino = i
                break
        if fila_destino is None:
            fila_destino = len(filas) + 1
            escribir_rango(f"{PESTANA_PARAMS}!A{fila_destino}", [[clave]],
                           sheet_id=COTIZADOR_SHEET_ID)
        escribir_rango(f"{PESTANA_PARAMS}!B{fila_destino}", [[valor]],
                       sheet_id=COTIZADOR_SHEET_ID)
        return f"✅ Guardado: {clave} = {valor}"
    except Exception as e:
        return f"No se pudo guardar {clave}: {e}"


def cotizar(cantidad: int, tamano: str, dificultad: str = "medio",
            minutos_acabado: float = None, params: dict = None,
            producto: str = "") -> dict:
    """Calcula el precio de una pieza y del pedido. Devuelve el desglose completo."""
    params = params or cargar_parametros()
    advertencias = []

    tamano = (tamano or "M").upper()
    if tamano not in TIEMPOS_ACABADO:
        raise ValueError(f"Tamaño '{tamano}' no válido. Usa: {', '.join(TAMANOS)}")
    dificultad = (dificultad or "medio").lower()
    if dificultad not in DIFICULTADES:
        raise ValueError(f"Dificultad '{dificultad}' no válida. Usa: {', '.join(DIFICULTADES)}")

    # ── Tiempo ──────────────────────────────────────────────────────────────
    if minutos_acabado is None:
        minutos_acabado = TIEMPOS_ACABADO[tamano][dificultad]
    if minutos_acabado is None:
        raise ValueError(
            f"No hay tiempo de acabado medido para {tamano} / {dificultad}. "
            f"Pásalo a mano con minutos_acabado, o mídelo en planta.")

    minutos_otros = float(params["minutos_otros_pasos"])
    if minutos_otros == 0:
        advertencias.append(
            "Solo se está costeando el ACABADO. Preparación, pulido, cargue de horno "
            "y demás pasos están en cero: el tiempo real por pieza es mayor.")
    minutos_totales = float(minutos_acabado) + minutos_otros

    horas_mes   = float(params["horas_semanales"]) * float(params["semanas_mes"])
    valor_hora  = float(params["salario_mensual"]) / horas_mes if horas_mes else 0
    costo_mo    = (minutos_totales / 60.0) * valor_hora

    # ── Materiales y proceso ────────────────────────────────────────────────
    materiales = (float(params["costo_bizcocho"]) + float(params["costo_esmaltes"])
                  + float(params["costo_vinilo"]))
    quemas = (float(params["costo_quema_bizcocho"]) + float(params["costo_quema_esmalte"])
              + float(params["costo_quema_transfer"]))
    empaque = float(params["costo_empaque"])

    # Las quemas no se listan: su energía ya va dentro de servicios públicos.
    faltantes = [n for n, v in [
        ("bizcocho", params["costo_bizcocho"]),
        ("esmaltes", params["costo_esmaltes"]),
        ("empaque", params["costo_empaque"])] if float(v) == 0]
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
    admin     = float(params["gastos_admin_mes"]) / volumen
    gran_total = directo_total + mercadeo + arriendo + admin

    if cantidad < volumen * 0.2:
        advertencias.append(
            f"El pedido ({cantidad} piezas) es chico frente al volumen de referencia "
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

    return {
        "producto": producto, "cantidad": int(cantidad),
        "tamano": tamano, "dificultad": dificultad,
        "minutos_acabado": round(float(minutos_acabado), 1),
        "minutos_totales": round(minutos_totales, 1),
        "valor_hora": round(valor_hora),
        "desglose": [
            ("Materiales (bizcocho, esmaltes, vinilo)", materiales),
            ("Mano de obra", costo_mo),
            ("Quemas", quemas),
            ("Empaque", empaque),
            ("Desperdicio", desperdicio),
            ("Mercadeo", mercadeo),
            ("Arriendo y servicios (incluye quemas)", arriendo),
            ("Gastos administrativos", admin),
        ],
        "costo_directo": round(costo_directo),
        "directo_total": round(directo_total),
        "gran_total":    round(gran_total),
        "pvp_unitario":  round(pvp),
        "iva_unitario":  round(iva),
        "precio_con_iva": round(con_iva),
        "margen_unitario": round(pvp - gran_total),
        "total_pedido_sin_iva": round(pvp * cantidad),
        "total_pedido_con_iva": round(con_iva * cantidad),
        "volumen_referencia": int(volumen),
        "advertencias": advertencias,
    }


def formato_telegram(r: dict) -> str:
    """Desglose legible. Sirve tanto en Telegram como en consola."""
    titulo = r["producto"] or "Pieza"
    lineas = [
        f"💰 {titulo} · {r['tamano']} · acabado {r['dificultad']} · {r['cantidad']} piezas",
        f"Tiempo: {r['minutos_totales']} min/pieza · hora de taller {_fmt(r['valor_hora'])}",
        "",
    ]
    for etiqueta, valor in r["desglose"]:
        if valor:
            lineas.append(f"  {etiqueta}: {_fmt(valor)}")
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
