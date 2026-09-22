"""
Cliente de Google Sheets API. Reemplaza Composio CLI.
Usa GOOGLE_CREDENTIALS (JSON string del service account) o el archivo de credenciales local.
"""
import os
import json
from pathlib import Path
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
# El proyecto tiene DOS archivos de Sheets y confundirlos es el error más fácil:
# la operación diaria vive en uno y el modelo de costos en el otro.
COTIZADOR_SHEET_ID = os.getenv(
    "COTIZADOR_SHEET_ID", "1SRji5gNT85HPLOXBgUhQdIRG7WZvTTWx6eDPEu6exKE")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_service_cache = None

def _service():
    global _service_cache
    if _service_cache:
        return _service_cache

    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        info = json.loads(creds_json)
    else:
        # fallback: archivo local (desarrollo)
        creds_file = Path(__file__).parent.parent / "google_credentials.json"
        info = json.loads(creds_file.read_text())

    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    _service_cache = build("sheets", "v4", credentials=creds)
    return _service_cache


def correo_servicio() -> str:
    """El correo de la cuenta de servicio del bot. Es el que hay que invitar a una
    hoja para que el bot pueda leerla o escribirla; sin eso, Google responde 403."""
    try:
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if creds_json:
            info = json.loads(creds_json)
        else:
            info = json.loads((Path(__file__).parent.parent / "google_credentials.json").read_text())
        return info.get("client_email", "")
    except Exception:
        return ""


def nombre_hoja(sheet_id: str = "") -> str:
    """Cuál de los dos archivos es, para poder nombrarlo en los errores."""
    sid = sheet_id or SPREADSHEET_ID
    if sid == COTIZADOR_SHEET_ID:
        return "Cotizador Interno"
    if sid == SPREADSHEET_ID:
        return "Ventas y Costos B&C"
    return "el Sheet"


def explicar(error, rango: str = "", sheet_id: str = "") -> str:
    """Traduce un error de la API a algo que se pueda arreglar.

    Los dos que se repiten son siempre los mismos y los dos se ven igual de
    opacos: la hoja no está compartida con el bot, o la pestaña no existe en
    ESE archivo (casi siempre porque se creó en el otro). En el segundo caso
    lo más útil es listar las pestañas que sí hay."""
    texto = str(error)
    cual = nombre_hoja(sheet_id)
    bajo = texto.lower()

    if "403" in texto or "permission" in bajo or "caller does not have" in bajo:
        correo = correo_servicio()
        if correo:
            return (f"El bot no tiene permiso de escritura en *{cual}*. "
                    f"Compártelo como Editor con {correo}.")
        return f"El bot no tiene permiso de escritura en *{cual}*."

    if "unable to parse range" in bajo or "not found" in bajo:
        pestana = rango.split("!")[0].strip("'") if "!" in rango else rango
        hay = listar_pestanas(sheet_id)
        extra = f" Las que sí hay: {hay}." if hay and not hay.startswith("Error") else ""
        return (f"No existe la pestaña *{pestana}* en *{cual}*.{extra} "
                f"Ojo: el proyecto tiene dos archivos de Sheets y puede estar creada en el otro.")

    return f"Error en {cual}: {texto}"


def leer_sheet(rango: str, sheet_id: str = "") -> str:
    try:
        result = _service().spreadsheets().values().get(
            spreadsheetId=sheet_id or SPREADSHEET_ID,
            range=rango,
            valueRenderOption="FORMATTED_VALUE"
        ).execute()
        valores = result.get("values", [])
        if not valores:
            return f"(rango vacío: {rango})"
        return "\n".join(" | ".join(str(c) for c in fila) for fila in valores if fila)
    except Exception as e:
        return f"Error leyendo {rango}: {e}"


def agregar_fila(rango: str, valores: list, sheet_id: str = "") -> str:
    try:
        _service().spreadsheets().values().append(
            spreadsheetId=sheet_id or SPREADSHEET_ID,
            range=rango,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [valores]}
        ).execute()
        return "Fila agregada correctamente."
    except Exception as e:
        return "Error: " + explicar(e, rango, sheet_id)


def actualizar_celda(rango: str, valor: str) -> str:
    try:
        _service().spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=rango,
            valueInputOption="USER_ENTERED",
            body={"values": [[valor]]}
        ).execute()
        return f"Celda {rango} actualizada a '{valor}'."
    except Exception as e:
        return "Error: " + explicar(e, rango)


def listar_pestanas(sheet_id: str = "") -> str:
    try:
        result = _service().spreadsheets().get(
            spreadsheetId=sheet_id or SPREADSHEET_ID
        ).execute()
        names = [s["properties"]["title"] for s in result.get("sheets", [])]
        return ", ".join(names)
    except Exception as e:
        return f"Error: {e}"


def crear_pestana(titulo: str, sheet_id: str = "") -> str:
    try:
        _service().spreadsheets().batchUpdate(
            spreadsheetId=sheet_id or SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": titulo}}}]}
        ).execute()
        return f"Pestaña '{titulo}' creada."
    except Exception as e:
        if "already exists" in str(e):
            return f"Pestaña '{titulo}' ya existe."
        return f"Error: {e}"


def id_pestana(titulo: str, sheet_id: str = ""):
    """El sheetId interno que pide batchUpdate (no es el nombre)."""
    try:
        r = _service().spreadsheets().get(spreadsheetId=sheet_id or SPREADSHEET_ID).execute()
        for h in r.get("sheets", []):
            if h["properties"]["title"] == titulo:
                return h["properties"]["sheetId"]
        return None
    except Exception:
        return None


def borrar_filas(titulo: str, filas: list, sheet_id: str = "") -> str:
    """Borra filas por número (1-indexado, como las ve la gente en la hoja).

    Se borran de abajo hacia arriba: borrar la fila 10 corre la 11 al lugar 10,
    y hacerlo al revés elimina filas equivocadas."""
    hid = id_pestana(titulo, sheet_id)
    if hid is None:
        return f"Error: no encontré la pestaña {titulo}."
    peticiones = [{"deleteDimension": {"range": {
                      "sheetId": hid, "dimension": "ROWS",
                      "startIndex": n - 1, "endIndex": n}}}
                  for n in sorted(set(int(x) for x in filas), reverse=True)]
    if not peticiones:
        return "No había filas que borrar."
    try:
        _service().spreadsheets().batchUpdate(
            spreadsheetId=sheet_id or SPREADSHEET_ID,
            body={"requests": peticiones}).execute()
        return f"{len(peticiones)} filas borradas de {titulo}."
    except Exception as e:
        return "Error: " + explicar(e, titulo, sheet_id)


def leer_sheet_numericos(rango: str, sheet_id: str = "") -> list:
    """Retorna valores crudos (números como float/int, texto como string) — UNFORMATTED_VALUE."""
    try:
        result = _service().spreadsheets().values().get(
            spreadsheetId=sheet_id or SPREADSHEET_ID,
            range=rango,
            valueRenderOption="UNFORMATTED_VALUE"
        ).execute()
        return result.get("values", [])
    except Exception as e:
        return []


def escribir_rango(rango: str, filas: list, sheet_id: str = "") -> str:
    """Escribe múltiples filas de una vez (más eficiente que agregar_fila en loop)."""
    try:
        _service().spreadsheets().values().update(
            spreadsheetId=sheet_id or SPREADSHEET_ID,
            range=rango,
            valueInputOption="USER_ENTERED",
            body={"values": filas}
        ).execute()
        return f"{len(filas)} filas escritas en {rango}."
    except Exception as e:
        return "Error: " + explicar(e, rango, sheet_id)
