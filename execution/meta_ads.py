#!/usr/bin/env python3
"""
Meta Ads (Facebook/Instagram) integration para Bosque y Cielo.
Cuenta publicitaria: act_379796923470762
"""
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
GRAPH_VERSION = "v24.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
ACCOUNT_ID = "act_379796923470762"


def _params(extra: dict = None) -> dict:
    p = {"access_token": META_ACCESS_TOKEN}
    if extra:
        p.update(extra)
    return p


def listar_campanas() -> str:
    """Lista las campañas de la cuenta con estado y presupuesto."""
    url = f"{BASE_URL}/{ACCOUNT_ID}"
    fields = "campaigns{id,name,status,effective_status,daily_budget,lifetime_budget,objective}"
    try:
        r = requests.get(url, params=_params({"fields": fields}), timeout=15)
        r.raise_for_status()
        campanas = r.json().get("campaigns", {}).get("data", [])
        if not campanas:
            return "No hay campañas en la cuenta."
        lineas = []
        for c in campanas:
            presupuesto = ""
            if c.get("daily_budget"):
                presupuesto = f" | presupuesto diario: ${int(c['daily_budget']) / 100:,.0f} COP"
            elif c.get("lifetime_budget"):
                presupuesto = f" | presupuesto total: ${int(c['lifetime_budget']) / 100:,.0f} COP"
            lineas.append(
                f"{c['name']} (id: {c['id']}) | estado: {c.get('effective_status', c.get('status'))} | "
                f"objetivo: {c.get('objective', '')}{presupuesto}"
            )
        return "\n".join(lineas)
    except Exception as e:
        return f"Error listando campañas: {e}"


def obtener_insights(nivel: str, object_id: str, date_preset: str = "last_7d") -> str:
    """Métricas de rendimiento (gasto, alcance, ROAS, CPA) a nivel account/campaign/adset/ad."""
    url = f"{BASE_URL}/{object_id}/insights"
    fields = ("campaign_name,campaign_id,spend,impressions,reach,frequency,"
              "clicks,cpc,cpm,ctr,actions,action_values")
    try:
        r = requests.get(url, params=_params({"level": nivel, "date_preset": date_preset, "fields": fields}), timeout=15)
        r.raise_for_status()
        filas = r.json().get("data", [])
        if not filas:
            return f"Sin datos para {object_id} en el período {date_preset} (puede ser que no hubo actividad)."
        lineas = []
        for f in filas:
            nombre = f.get("campaign_name", object_id)
            acciones = f.get("actions", [])
            valores = f.get("action_values", [])
            acciones_txt = ", ".join(f"{a.get('action_type')}: {a.get('value')}" for a in acciones) or "sin acciones"
            valores_txt = ", ".join(f"{v.get('action_type')}: ${v.get('value')}" for v in valores) or "sin valor"
            lineas.append(
                f"{nombre} | gasto: ${f.get('spend', '0')} | impresiones: {f.get('impressions', '0')} | "
                f"alcance: {f.get('reach', '0')} | frecuencia: {f.get('frequency', '0')} | clics: {f.get('clicks', '0')} | "
                f"cpc: {f.get('cpc', '0')} | cpm: {f.get('cpm', '0')} | ctr: {f.get('ctr', '0')} | "
                f"acciones: {acciones_txt} | valor acciones: {valores_txt}"
            )
        return "\n".join(lineas)
    except Exception as e:
        return f"Error obteniendo insights: {e}"


def pausar_campana(campaign_id: str) -> str:
    """Pausa una campaña. Llamar SIEMPRE después de confirmación explícita del usuario."""
    try:
        r = requests.post(f"{BASE_URL}/{campaign_id}", params=_params({"status": "PAUSED"}), timeout=15)
        r.raise_for_status()
        return f"Campaña {campaign_id} pausada."
    except Exception as e:
        return f"Error pausando campaña: {e}"


def reanudar_campana(campaign_id: str) -> str:
    """Reanuda una campaña pausada. Llamar SIEMPRE después de confirmación explícita del usuario."""
    try:
        r = requests.post(f"{BASE_URL}/{campaign_id}", params=_params({"status": "ACTIVE"}), timeout=15)
        r.raise_for_status()
        return f"Campaña {campaign_id} reanudada."
    except Exception as e:
        return f"Error reanudando campaña: {e}"


def actualizar_presupuesto(campaign_id: str, presupuesto_diario: float) -> str:
    """Cambia el presupuesto diario (en pesos colombianos) de una campaña. Confirmar SIEMPRE antes."""
    try:
        centavos = int(round(presupuesto_diario * 100))
        r = requests.post(f"{BASE_URL}/{campaign_id}", params=_params({"daily_budget": centavos}), timeout=15)
        r.raise_for_status()
        return f"Presupuesto diario de la campaña {campaign_id} actualizado a ${presupuesto_diario:,.0f} COP."
    except Exception as e:
        return f"Error actualizando presupuesto: {e}"
