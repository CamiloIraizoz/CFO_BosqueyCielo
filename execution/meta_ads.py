#!/usr/bin/env python3
"""
Meta Ads (Facebook/Instagram) integration para Bosque y Cielo.
Cuenta publicitaria: act_379796923470762
"""
import os
import json
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
GRAPH_VERSION = "v24.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
ACCOUNT_ID = "act_379796923470762"
PAGE_ID = "260778498124943"
PIXEL_ID = "410038360006367"

# objetivo -> (objective ODAX, optimization_goal, billing_event, promoted_object|None, destination_type|None)
_OBJETIVOS = {
    "trafico":        ("OUTCOME_TRAFFIC", "LINK_CLICKS", "IMPRESSIONS", None, "WEBSITE"),
    "ventas":         ("OUTCOME_SALES", "OFFSITE_CONVERSIONS", "IMPRESSIONS",
                        {"pixel_id": PIXEL_ID, "custom_event_type": "PURCHASE"}, None),
    "interaccion":    ("OUTCOME_ENGAGEMENT", "POST_ENGAGEMENT", "IMPRESSIONS", None, None),
    "reconocimiento": ("OUTCOME_AWARENESS", "REACH", "IMPRESSIONS", None, None),
}


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


def _subir_imagen(imagen_url: str) -> str:
    """Descarga una imagen pública (ej. foto de producto de Shopify) y la sube a Meta. Retorna el image_hash."""
    img = requests.get(imagen_url, timeout=20)
    img.raise_for_status()
    b64 = base64.b64encode(img.content).decode()
    r = requests.post(f"{BASE_URL}/{ACCOUNT_ID}/adimages",
                       data=_params({"bytes": b64}), timeout=30)
    r.raise_for_status()
    imagenes = r.json().get("images", {})
    primera = next(iter(imagenes.values()))
    return primera["hash"]


def crear_campana_completa(nombre: str, objetivo: str, presupuesto_diario: float,
                            imagen_url: str, texto_principal: str, titular: str,
                            link_destino: str, descripcion: str = "",
                            cta: str = "SHOP_NOW") -> str:
    """
    Crea campaña + ad set + creativo + anuncio, TODO en estado PAUSED (nunca gasta sin activación manual).
    objetivo: trafico | ventas | interaccion | reconocimiento
    Targeting por defecto: Colombia, 18-65, sin restricción de género, placements automáticos (Advantage+).
    """
    if objetivo not in _OBJETIVOS:
        return f"Objetivo inválido: {objetivo}. Usa uno de: {', '.join(_OBJETIVOS)}"
    objective, optimization_goal, billing_event, promoted_object, destination_type = _OBJETIVOS[objetivo]

    try:
        # 1. Campaña
        r = requests.post(f"{BASE_URL}/{ACCOUNT_ID}/campaigns", data=_params({
            "name": nombre, "objective": objective, "status": "PAUSED",
            "special_ad_categories": "[]"
        }), timeout=20)
        r.raise_for_status()
        campaign_id = r.json()["id"]

        # 2. Ad set
        adset_body = {
            "name": f"{nombre} — Ad Set",
            "campaign_id": campaign_id,
            "daily_budget": int(round(presupuesto_diario * 100)),
            "billing_event": billing_event,
            "optimization_goal": optimization_goal,
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "status": "PAUSED",
            "targeting": '{"geo_locations":{"countries":["CO"]},"age_min":18,"age_max":65}',
        }
        if promoted_object:
            adset_body["promoted_object"] = json.dumps(promoted_object)
        if destination_type:
            adset_body["destination_type"] = destination_type
        r = requests.post(f"{BASE_URL}/{ACCOUNT_ID}/adsets", data=_params(adset_body), timeout=20)
        r.raise_for_status()
        adset_id = r.json()["id"]

        # 3. Imagen + creativo
        image_hash = _subir_imagen(imagen_url)
        object_story_spec = {
            "page_id": PAGE_ID,
            "link_data": {
                "image_hash": image_hash,
                "link": link_destino,
                "message": texto_principal,
                "name": titular,
                "description": descripcion,
                "call_to_action": {"type": cta, "value": {"link": link_destino}},
            },
        }
        r = requests.post(f"{BASE_URL}/{ACCOUNT_ID}/adcreatives", data=_params({
            "name": f"{nombre} — Creativo",
            "object_story_spec": json.dumps(object_story_spec),
        }), timeout=20)
        r.raise_for_status()
        creative_id = r.json()["id"]

        # 4. Anuncio
        r = requests.post(f"{BASE_URL}/{ACCOUNT_ID}/ads", data=_params({
            "name": f"{nombre} — Anuncio",
            "adset_id": adset_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": "PAUSED",
        }), timeout=20)
        r.raise_for_status()
        ad_id = r.json()["id"]

        return (f"✅ Campaña creada en PAUSA (no gasta hasta que la actives manualmente):\n"
                f"Campaña: {nombre} (id: {campaign_id})\n"
                f"Objetivo: {objetivo} | Presupuesto diario: ${presupuesto_diario:,.0f} COP\n"
                f"Ad set: {adset_id} | Creativo: {creative_id} | Anuncio: {ad_id}\n"
                f"Revísala en Meta Ads Manager y actívala cuando estés list@ (o pídeme reanudar_campana).")
    except requests.HTTPError as e:
        detalle = e.response.text if e.response is not None else str(e)
        return f"Error creando campaña: {detalle}"
    except Exception as e:
        return f"Error creando campaña: {e}"
