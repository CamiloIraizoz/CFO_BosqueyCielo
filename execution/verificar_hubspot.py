#!/usr/bin/env python3
"""
Verifica que el token privado de HubSpot tenga los permisos que necesita el bot
para registrar cotizaciones (contactos, negocios, notas y archivos).

Uso:
    python3 execution/verificar_hubspot.py              # solo lectura
    python3 execution/verificar_hubspot.py --escritura  # además sube y borra un PDF de prueba

El modo --escritura es el único que comprueba de verdad el scope 'files' (subir
el PDF de la cotización). Crea un archivo temporal en /cotizaciones y lo borra.
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

HS_TOKEN = os.getenv("HUBSPOT_TOKEN", "")
BASE_URL = "https://api.hubapi.com"

# PDF mínimo válido, para probar la subida sin depender de una cotización real.
PDF_PRUEBA = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
              b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
              b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 99 99]>>endobj\n"
              b"trailer<</Root 1 0 R>>\n%%EOF\n")


def _headers():
    return {"Authorization": f"Bearer {HS_TOKEN}"}


def _scopes_faltantes(resp) -> str:
    """HubSpot devuelve en el 403 qué scopes exige el endpoint."""
    try:
        ctx = resp.json().get("context", {})
        req = ctx.get("requiredScopes") or ctx.get("requiredGranularScopes") or []
        if req:
            return " → falta alguno de: " + ", ".join(sorted({s for g in req for s in str(g).split(",")}))
    except Exception:
        pass
    return ""


def _probar(etiqueta: str, metodo: str, url: str, **kwargs) -> bool:
    try:
        resp = requests.request(metodo, url, headers=_headers(), timeout=30, **kwargs)
    except Exception as e:
        print(f"  ✗ {etiqueta}: error de red ({e})")
        return False
    if resp.status_code < 400:
        print(f"  ✓ {etiqueta}")
        return True
    if resp.status_code in (401, 403):
        print(f"  ✗ {etiqueta}: sin permiso ({resp.status_code}){_scopes_faltantes(resp)}")
    else:
        print(f"  ✗ {etiqueta}: HTTP {resp.status_code} — {resp.text[:200]}")
    return False


def main() -> int:
    if not HS_TOKEN:
        print("✗ HUBSPOT_TOKEN no está definido.")
        print("  Localmente: agrégalo al archivo .env (está en .gitignore).")
        print("  En Railway: railway run python3 execution/verificar_hubspot.py")
        return 1

    print(f"Token: ...{HS_TOKEN[-6:]}\n")
    print("Lectura:")
    ok = [
        _probar("contactos", "GET", f"{BASE_URL}/crm/v3/objects/contacts?limit=1"),
        _probar("negocios",  "GET", f"{BASE_URL}/crm/v3/objects/deals?limit=1"),
        _probar("notas",     "GET", f"{BASE_URL}/crm/v3/objects/notes?limit=1"),
    ]
    archivos_ok = _probar("archivos (scope files)", "GET", f"{BASE_URL}/files/v3/files?limit=1")
    ok.append(archivos_ok)

    if "--escritura" in sys.argv:
        print("\nEscritura (sube un PDF de prueba y lo borra):")
        try:
            resp = requests.post(
                f"{BASE_URL}/files/v3/files",
                headers=_headers(),
                files={"file": ("_prueba_permisos.pdf", PDF_PRUEBA, "application/pdf")},
                data={"folderPath": "/cotizaciones",
                      "options": json.dumps({"access": "PRIVATE",
                                             "overwrite": True,
                                             "duplicateValidationStrategy": "NONE",
                                             "duplicateValidationScope": "EXACT_FOLDER"})},
                timeout=30)
            if resp.status_code < 400:
                file_id = resp.json()["id"]
                print(f"  ✓ subida de PDF (id {file_id})")
                borrado = requests.delete(f"{BASE_URL}/files/v3/files/{file_id}",
                                          headers=_headers(), timeout=30)
                print("  ✓ archivo de prueba borrado" if borrado.status_code < 400
                      else f"  ⚠ no se pudo borrar el archivo de prueba {file_id} — bórralo a mano en HubSpot")
            else:
                ok.append(False)
                print(f"  ✗ subida de PDF: HTTP {resp.status_code}{_scopes_faltantes(resp)}")
                print(f"    {resp.text[:200]}")
        except Exception as e:
            ok.append(False)
            print(f"  ✗ subida de PDF: {e}")

    print()
    if all(ok):
        print("✅ El token tiene todo lo que necesita el registro de cotizaciones.")
        if "--escritura" not in sys.argv:
            print("   Corre con --escritura para confirmar que el PDF se puede subir de verdad.")
        return 0

    print("❌ Faltan permisos. En HubSpot:")
    print("   Configuración (engranaje) → Integraciones → Aplicaciones privadas →")
    print("   abre la app del bot → pestaña Ámbitos/Scopes → marca los que aparecen arriba →")
    print("   Guardar → Generar token nuevo si HubSpot lo pide → actualiza HUBSPOT_TOKEN en Railway.")
    if not archivos_ok:
        print("\n   Para adjuntar el PDF a la nota hace falta el scope 'files'.")
        print("   Sin él la cotización igual se registra, pero la nota va sin adjunto.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
