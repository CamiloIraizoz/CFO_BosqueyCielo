#!/usr/bin/env python3
"""
Crea en la hoja "Cotizador Interno" las pestañas que lee el motor de cotización:
  · Parámetros Cotizador — tarifas, costos fijos y porcentajes (editables a mano)
  · Tiempos Acabado      — minutos por tamaño y dificultad (Discovery 2026-09)

Requiere que el Sheet esté compartido con la cuenta de servicio del bot.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)
sys.path.insert(0, str(Path(__file__).parent))

from cotizador import (COTIZADOR_SHEET_ID, PARAMS_DEFECTO, PESTANA_PARAMS,
                       TAMANOS, TIEMPOS_ACABADO)
from sheets import crear_pestana, escribir_rango

NOTAS = {
    "salario_mensual":        "Salario mensual del taller — base del valor hora",
    "horas_semanales":        "Horas trabajadas por semana",
    "semanas_mes":            "Semanas por mes",
    "volumen_referencia":     "Piezas/mes entre las que se reparten los fijos. NO es el tamaño del pedido",
    "gastos_admin_mes":       "Contador + gerente + supervisor, por su % de dedicación",
    "arriendo_mes":           "Arriendo mensual del local",
    "servicios_mes":          "Servicios públicos mensuales — INCLUYE la energía de las quemas",
    "pct_uso_local":          "% del local dedicado a producción",
    "pct_uso_servicios":      "% de los servicios que carga producción (las quemas consumen harto)",
    "desperdicio_pct":        "% sobre el costo directo",
    "mercadeo_pct":           "% sobre el costo directo total",
    "margen_pct":             "% de margen",
    "margen_modo":            "markup = costo x (1+m) · sobre_venta = costo / (1-m)",
    "iva_pct":                "IVA",
    "costo_bizcocho":         "El bot lo pregunta — costo del bizcocho por pieza",
    "costo_esmaltes":         "El bot lo pregunta — esmaltes por pieza",
    "costo_vinilo":           "Vinilo/transfer por pieza (0 si no lleva)",
    "costo_quema_bizcocho":   "Dejar en 0: la energía de las quemas ya está en servicios",
    "costo_quema_esmalte":    "Dejar en 0: la energía de las quemas ya está en servicios",
    "costo_quema_transfer":   "Dejar en 0: la energía de las quemas ya está en servicios",
    "costo_empaque":          "El bot lo pregunta — empaque por pieza",
    "minutos_otros_pasos":    "El bot lo pregunta — minutos de los pasos que no son acabado",
}


def setup():
    print(f"Hoja destino: {COTIZADOR_SHEET_ID}")

    print(crear_pestana(PESTANA_PARAMS, sheet_id=COTIZADOR_SHEET_ID))
    filas = [["Parámetro", "Valor", "Notas"]]
    filas += [[clave, valor, NOTAS.get(clave, "")] for clave, valor in PARAMS_DEFECTO.items()]
    print(escribir_rango(f"{PESTANA_PARAMS}!A1:C{len(filas)}", filas,
                         sheet_id=COTIZADOR_SHEET_ID))

    print(crear_pestana("Tiempos Acabado", sheet_id=COTIZADOR_SHEET_ID))
    tiempos = [["Tamaño", "Fácil", "Medio", "Difícil"]]
    for tam in TAMANOS:
        fila = [tam]
        for dif in ["facil", "medio", "dificil"]:
            valor = TIEMPOS_ACABADO[tam][dif]
            fila.append(valor if valor is not None else "")
        tiempos.append(fila)
    tiempos.append([])
    tiempos.append(["Minutos de acabado por pieza (Discovery 2026-09). "
                    "Las celdas vacías son tiempos que todavía no se han medido."])
    print(escribir_rango(f"Tiempos Acabado!A1:D{len(tiempos)}", tiempos,
                         sheet_id=COTIZADOR_SHEET_ID))

    print("\nListo. Las filas marcadas PENDIENTE en Notas son las que hay que llenar "
          "para que el precio salga completo.")


if __name__ == "__main__":
    setup()
