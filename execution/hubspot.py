#!/usr/bin/env python3
"""
HubSpot CRM integration para Amphora B&C.
Pipeline: Prospecto → Cotización → Negociación → Anticipo Recibido
          → En Producción → Listo para Entrega → Entregado | Perdido
"""
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

HS_TOKEN = os.getenv("HUBSPOT_TOKEN")
BASE_URL  = "https://api.hubapi.com"

PIPELINE_ID = "default"
STAGES = {
    "prospecto":         "appointmentscheduled",
    "cotizacion":        "qualifiedtobuy",
    "negociacion":       "presentationscheduled",
    "anticipo_recibido": "decisionmakerboughtin",
    "en_produccion":     "contractsent",
    "listo_entrega":     "stage_0",
    "entregado":         "closedwon",
    "perdido":           "closedlost",
}
STAGE_LABELS = {v: k for k, v in STAGES.items()}


def _headers():
    return {"Authorization": f"Bearer {HS_TOKEN}", "Content-Type": "application/json"}


# ── Contactos ──────────────────────────────────────────────────────────────────

def buscar_contacto(query: str) -> str:
    """Busca contactos por nombre, empresa o email."""
    url = f"{BASE_URL}/crm/v3/objects/contacts/search"
    body = {
        "query": query,
        "limit": 5,
        "properties": ["firstname", "lastname", "email", "phone", "company"]
    }
    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return f"No se encontraron contactos para '{query}'."
        lines = []
        for c in results:
            p = c["properties"]
            nombre = f"{p.get('firstname','')} {p.get('lastname','')}".strip()
            empresa = p.get("company", "")
            email = p.get("email", "")
            lines.append(f"ID:{c['id']} | {nombre} | {empresa} | {email}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error buscando contacto: {e}"


def crear_contacto(nombre: str, empresa: str, email: str = "", telefono: str = "") -> str:
    """Crea un nuevo contacto en HubSpot."""
    partes = nombre.strip().split(" ", 1)
    firstname = partes[0]
    lastname  = partes[1] if len(partes) > 1 else ""
    props = {"firstname": firstname, "lastname": lastname, "company": empresa}
    if email:
        props["email"] = email
    if telefono:
        props["phone"] = telefono
    try:
        r = requests.post(f"{BASE_URL}/crm/v3/objects/contacts",
                          json={"properties": props}, headers=_headers(), timeout=15)
        r.raise_for_status()
        cid = r.json()["id"]
        return f"Contacto creado. ID:{cid} | {nombre} | {empresa}"
    except requests.HTTPError as e:
        if e.response.status_code == 409:
            return "Contacto ya existe en HubSpot (email duplicado)."
        return f"Error creando contacto: {e.response.text}"
    except Exception as e:
        return f"Error creando contacto: {e}"


# ── Deals ──────────────────────────────────────────────────────────────────────

def crear_deal(nombre_deal: str, contacto_id: str, etapa: str,
               valor: int = 0, descripcion: str = "") -> str:
    """Crea un nuevo negocio en el pipeline."""
    stage_id = STAGES.get(etapa.lower(), "appointmentscheduled")
    props = {
        "dealname":   nombre_deal,
        "pipeline":   PIPELINE_ID,
        "dealstage":  stage_id,
        "amount":     str(valor),
        "description": descripcion,
    }
    body = {"properties": props}
    if contacto_id:
        body["associations"] = [{
            "to": {"id": contacto_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]
        }]
    try:
        r = requests.post(f"{BASE_URL}/crm/v3/objects/deals",
                          json=body, headers=_headers(), timeout=15)
        r.raise_for_status()
        did = r.json()["id"]
        return f"Negocio creado. ID:{did} | {nombre_deal} | Etapa:{etapa} | ${valor:,}"
    except Exception as e:
        return f"Error creando negocio: {e}"


def actualizar_deal(deal_id: str, etapa: str = "", valor: int = None,
                    notas: str = "") -> str:
    """Actualiza etapa, valor o notas de un negocio."""
    props = {}
    if etapa:
        props["dealstage"] = STAGES.get(etapa.lower(), etapa)
    if valor is not None:
        props["amount"] = str(valor)
    if notas:
        props["description"] = notas
    if not props:
        return "Nada que actualizar."
    try:
        r = requests.patch(f"{BASE_URL}/crm/v3/objects/deals/{deal_id}",
                           json={"properties": props}, headers=_headers(), timeout=15)
        r.raise_for_status()
        return f"Negocio {deal_id} actualizado. Etapa:{etapa or 'sin cambio'}"
    except Exception as e:
        return f"Error actualizando negocio: {e}"


def listar_deals(etapa: str = "") -> str:
    """Lista negocios del pipeline, opcionalmente filtrados por etapa."""
    url = f"{BASE_URL}/crm/v3/objects/deals/search"
    filters = [{"propertyName": "pipeline", "operator": "EQ", "value": PIPELINE_ID}]
    if etapa:
        stage_id = STAGES.get(etapa.lower(), etapa)
        filters.append({"propertyName": "dealstage", "operator": "EQ", "value": stage_id})
    body = {
        "filterGroups": [{"filters": filters}],
        "properties": ["dealname", "dealstage", "amount", "closedate"],
        "limit": 20,
        "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]
    }
    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return "No hay negocios" + (f" en etapa '{etapa}'." if etapa else ".")
        lines = []
        for d in results:
            p  = d["properties"]
            sl = STAGE_LABELS.get(p.get("dealstage", ""), p.get("dealstage", ""))
            monto = int(float(p.get("amount") or 0))
            lines.append(f"ID:{d['id']} | {p.get('dealname','')} | {sl} | ${monto:,}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listando negocios: {e}"


def agregar_nota(deal_id: str, nota: str) -> str:
    """Agrega una nota de actividad a un negocio."""
    body = {
        "properties": {
            "hs_note_body": nota,
            "hs_timestamp": str(int(__import__("time").time() * 1000))
        },
        "associations": [{
            "to": {"id": deal_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 214}]
        }]
    }
    try:
        r = requests.post(f"{BASE_URL}/crm/v3/objects/notes",
                          json=body, headers=_headers(), timeout=15)
        r.raise_for_status()
        return f"Nota agregada al negocio {deal_id}."
    except Exception as e:
        return f"Error agregando nota: {e}"
