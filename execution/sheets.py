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


def leer_sheet(rango: str) -> str:
    try:
        result = _service().spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=rango,
            valueRenderOption="FORMATTED_VALUE"
        ).execute()
        valores = result.get("values", [])
        if not valores:
            return f"(rango vacío: {rango})"
        return "\n".join(" | ".join(str(c) for c in fila) for fila in valores if fila)
    except Exception as e:
        return f"Error leyendo {rango}: {e}"


def agregar_fila(rango: str, valores: list) -> str:
    try:
        _service().spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=rango,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [valores]}
        ).execute()
        return "Fila agregada correctamente."
    except Exception as e:
        return f"Error: {e}"


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
        return f"Error: {e}"


def listar_pestanas() -> str:
    try:
        result = _service().spreadsheets().get(
            spreadsheetId=SPREADSHEET_ID
        ).execute()
        names = [s["properties"]["title"] for s in result.get("sheets", [])]
        return ", ".join(names)
    except Exception as e:
        return f"Error: {e}"
