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
    "lead":              "appointmentscheduled",
    "cotizacion":        "qualifiedtobuy",
    "negociacion":       "presentationscheduled",
    "anticipo_recibido": "decisionmakerboughtin",
    "en_produccion":     "contractsent",
    "listo_entrega":     "stage_0",
    "entregado":         "closedwon",
    "lost":              "closedlost",
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


# ── Registro automático de cotizaciones ────────────────────────────────────────
# Cada cotización enviada queda en HubSpot: contacto + negocio en etapa
# "cotización" con el valor total + nota con el detalle y el PDF adjunto.

ETAPAS_CERRADAS = {"closedwon", "closedlost"}


def _buscar_contacto_id(email: str, nombre: str, empresa: str):
    """ID del contacto existente, o None. Sin email exige coincidencia exacta de nombre."""
    url = f"{BASE_URL}/crm/v3/objects/contacts/search"
    props = ["firstname", "lastname", "email", "company"]
    try:
        if email:
            body = {
                "filterGroups": [{"filters": [
                    {"propertyName": "email", "operator": "EQ", "value": email}
                ]}],
                "properties": props, "limit": 1,
            }
            r = requests.post(url, json=body, headers=_headers(), timeout=15)
            r.raise_for_status()
            resultados = r.json().get("results", [])
            if resultados:
                return resultados[0]["id"]
            return None

        # Sin email: solo aceptamos coincidencia exacta de nombre, para no
        # colgar la cotización del contacto equivocado.
        r = requests.post(url, json={"query": nombre, "properties": props, "limit": 10},
                          headers=_headers(), timeout=15)
        r.raise_for_status()
        objetivo = nombre.strip().lower()
        for c in r.json().get("results", []):
            p = c["properties"]
            completo = f"{p.get('firstname','') or ''} {p.get('lastname','') or ''}".strip().lower()
            if completo == objetivo:
                return c["id"]
        return None
    except Exception as e:
        print(f"[hubspot] Error buscando contacto: {e}")
        return None


def _crear_contacto_id(nombre: str, empresa: str, email: str = "", telefono: str = ""):
    """Crea el contacto y devuelve su ID, o None si falla."""
    partes = nombre.strip().split(" ", 1)
    props = {"firstname": partes[0], "lastname": partes[1] if len(partes) > 1 else ""}
    if empresa:
        props["company"] = empresa
    if email:
        props["email"] = email
    if telefono:
        props["phone"] = telefono
    try:
        r = requests.post(f"{BASE_URL}/crm/v3/objects/contacts",
                          json={"properties": props}, headers=_headers(), timeout=15)
        r.raise_for_status()
        return r.json()["id"]
    except Exception as e:
        print(f"[hubspot] Error creando contacto: {e}")
        return None


def _deal_abierto_de_contacto(contacto_id: str):
    """Negocio abierto más reciente del contacto: {id, etapa, nombre}, o None."""
    try:
        r = requests.get(
            f"{BASE_URL}/crm/v4/objects/contacts/{contacto_id}/associations/deals",
            headers=_headers(), timeout=15)
        r.raise_for_status()
        ids = [str(x["toObjectId"]) for x in r.json().get("results", [])]
        if not ids:
            return None

        r = requests.post(
            f"{BASE_URL}/crm/v3/objects/deals/batch/read",
            json={"inputs": [{"id": i} for i in ids],
                  "properties": ["dealname", "dealstage", "amount", "createdate"]},
            headers=_headers(), timeout=15)
        r.raise_for_status()
        abiertos = [d for d in r.json().get("results", [])
                    if d["properties"].get("dealstage") not in ETAPAS_CERRADAS]
        if not abiertos:
            return None
        abiertos.sort(key=lambda d: d["properties"].get("createdate", ""), reverse=True)
        elegido = abiertos[0]
        return {"id": elegido["id"],
                "etapa": elegido["properties"].get("dealstage", ""),
                "nombre": elegido["properties"].get("dealname", "")}
    except Exception as e:
        print(f"[hubspot] Error buscando negocios del contacto {contacto_id}: {e}")
        return None


def _subir_archivo(nombre_archivo: str, contenido: bytes):
    """Sube el PDF a HubSpot Files y devuelve su ID, o None. Requiere scope 'files'."""
    import json as _json
    try:
        r = requests.post(
            f"{BASE_URL}/files/v3/files",
            headers={"Authorization": f"Bearer {HS_TOKEN}"},   # sin Content-Type: es multipart
            files={"file": (nombre_archivo, contenido, "application/pdf")},
            data={"folderPath": "/cotizaciones",
                  "options": _json.dumps({"access": "PRIVATE",
                                          "overwrite": False,
                                          "duplicateValidationStrategy": "NONE",
                                          "duplicateValidationScope": "EXACT_FOLDER"})},
            timeout=30)
        r.raise_for_status()
        return r.json()["id"]
    except Exception as e:
        print(f"[hubspot] Error subiendo PDF: {e}")
        return None


def _nota_con_adjunto(deal_id: str, contacto_id: str, texto: str, file_id=None) -> bool:
    """Nota asociada al negocio (y al contacto), con el PDF adjunto si se subió."""
    props = {"hs_note_body": texto,
             "hs_timestamp": str(int(__import__("time").time() * 1000))}
    if file_id:
        props["hs_attachment_ids"] = str(file_id)

    asociaciones = [{
        "to": {"id": deal_id},
        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 214}]
    }]
    if contacto_id:
        asociaciones.append({
            "to": {"id": contacto_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]
        })
    try:
        r = requests.post(f"{BASE_URL}/crm/v3/objects/notes",
                          json={"properties": props, "associations": asociaciones},
                          headers=_headers(), timeout=20)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[hubspot] Error creando nota: {e}")
        return False


def registrar_cotizacion(datos: dict, paquete: dict, deal_id: str = "") -> str:
    """Sube la cotización recién enviada a HubSpot.

    - Contacto: lo busca por email (o por nombre exacto) y lo crea si no existe.
    - Negocio: usa el deal_id dado; si no, el negocio abierto más reciente del
      contacto; si no hay ninguno, crea uno nuevo. Nunca retrocede de etapa:
      solo mueve a "cotización" un negocio que siga en "lead".
    - Nota: detalle de la cotización + PDF adjunto.

    Devuelve una línea de resumen para Telegram. Nunca lanza excepción: el correo
    ya salió y un fallo aquí no debe romper la respuesta al usuario.
    """
    if not HS_TOKEN:
        return "⚠️ HubSpot: HUBSPOT_TOKEN no configurado, la cotización no se registró."

    try:
        cliente  = datos.get("cliente", {})
        nombre   = cliente.get("nombre", "").strip()
        empresa  = paquete.get("empresa", "")
        email    = cliente.get("email", "").strip()
        telefono = cliente.get("telefono", "").strip()
        numero   = paquete["numero"]
        total    = int(paquete["total"])

        # 1. Contacto
        contacto_id = _buscar_contacto_id(email, nombre, empresa)
        contacto_nuevo = False
        if not contacto_id and nombre:
            contacto_id = _crear_contacto_id(nombre, empresa, email, telefono)
            contacto_nuevo = bool(contacto_id)

        # 2. Negocio
        etiqueta_deal = f"Cotización {numero} — {empresa or nombre}"
        deal_nuevo = False
        ya_actualizado = False
        if not deal_id and contacto_id:
            existente = _deal_abierto_de_contacto(contacto_id)
            if existente:
                deal_id = existente["id"]
                # Solo avanzamos desde "lead"; no bajamos un negocio ya avanzado.
                etapa_nueva = "cotizacion" if existente["etapa"] == STAGES["lead"] else ""
                actualizar_deal(deal_id, etapa=etapa_nueva, valor=total)
                ya_actualizado = True

        if not deal_id:
            respuesta = crear_deal(etiqueta_deal, contacto_id or "", "cotizacion", total)
            if respuesta.startswith("Error"):
                return f"⚠️ HubSpot: no se pudo crear el negocio ({respuesta})"
            deal_id = respuesta.split("ID:")[1].split(" ")[0].strip()
            deal_nuevo = True
        elif not ya_actualizado:
            # deal_id que vino del usuario: solo actualizamos el valor.
            actualizar_deal(deal_id, valor=total)

        # 3. Nota con el PDF
        file_id = _subir_archivo(paquete["archivo"], paquete["pdf"]) if paquete.get("pdf") else None
        cuerpo = (f"<b>{etiqueta_deal}</b><br>"
                  f"Enviada el {datos.get('fecha','')} · {paquete.get('etiqueta','')}<br><br>"
                  + paquete.get("detalle", "").replace("\n", "<br>")
                  + f"<br><br><b>Total: ${total:,}</b>".replace(",", ".")
                  + (f"<br>Condiciones: {datos.get('condiciones_pago','')}"
                     if datos.get("condiciones_pago") else "")
                  + (f"<br>Correo del cliente: {email}" if email
                     else "<br>Sin correo del cliente: la cotización se envió solo a Daniela y Camilo."))
        nota_ok = _nota_con_adjunto(deal_id, contacto_id or "", cuerpo, file_id)

        # 4. Resumen para Telegram
        partes = [f"📊 HubSpot: negocio {deal_id}"]
        partes.append("creado en etapa cotización" if deal_nuevo else "actualizado")
        if contacto_nuevo:
            partes.append("contacto nuevo creado")
        if not contacto_id:
            partes.append("⚠️ sin contacto asociado")
        if nota_ok:
            partes.append("nota con PDF adjunto" if file_id else "nota agregada (PDF no se pudo adjuntar)")
        else:
            partes.append("⚠️ la nota no se pudo crear")
        return " · ".join(partes)
    except Exception as e:
        return f"⚠️ HubSpot: la cotización se envió pero no se registró ({e})"
