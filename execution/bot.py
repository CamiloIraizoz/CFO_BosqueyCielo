#!/usr/bin/env python3
"""
Bot de Telegram para gestión financiera de Amphora B&C.
Uso: python3 execution/bot.py
"""
import os
import json
import time
import base64
import subprocess
import requests
import anthropic
from pathlib import Path
from dotenv import load_dotenv

# Carga .env en local; en Railway las variables vienen del entorno directamente
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=False)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
COMPOSIO = os.path.expanduser("~/.composio/composio")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Google Sheets via Composio ─────────────────────────────────────────────────

def composio_call(tool: str, data: dict) -> dict:
    result = subprocess.run(
        [COMPOSIO, "execute", tool, "-d", json.dumps(data)],
        capture_output=True, text=True, timeout=30
    )
    stdout = "\n".join(
        l for l in result.stdout.splitlines()
        if "Update available" not in l and "composio upgrade" not in l
    ).strip()
    try:
        return json.loads(stdout)
    except Exception:
        return {"successful": False, "error": result.stderr or stdout}

def leer_sheet(rango: str) -> str:
    resp = composio_call("GOOGLESHEETS_VALUES_GET", {
        "spreadsheet_id": SPREADSHEET_ID,
        "range": rango,
        "value_render_option": "FORMATTED_VALUE"
    })
    if resp.get("successful"):
        valores = resp["data"].get("values", [])
        if not valores:
            return f"(rango vacío: {rango})"
        return "\n".join(" | ".join(str(c) for c in fila) for fila in valores if fila)
    return f"Error leyendo {rango}: {resp.get('error', 'desconocido')}"

def agregar_fila(rango: str, valores: list) -> str:
    resp = composio_call("GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND", {
        "spreadsheet_id": SPREADSHEET_ID,
        "range": rango,
        "values": [valores],
        "value_input_option": "USER_ENTERED",
        "insert_data_option": "INSERT_ROWS"
    })
    if resp.get("successful"):
        return "Fila agregada correctamente."
    return f"Error: {resp.get('error', 'desconocido')}"

def actualizar_celda(rango: str, valor: str) -> str:
    resp = composio_call("GOOGLESHEETS_VALUES_UPDATE", {
        "spreadsheet_id": SPREADSHEET_ID,
        "range": rango,
        "values": [[valor]],
        "value_input_option": "USER_ENTERED"
    })
    if resp.get("successful"):
        return f"Celda {rango} actualizada a '{valor}'."
    return f"Error: {resp.get('error', 'desconocido')}"

def listar_pestanas() -> str:
    resp = composio_call("GOOGLESHEETS_GET_SHEET_NAMES", {
        "spreadsheet_id": SPREADSHEET_ID
    })
    if resp.get("successful"):
        return ", ".join(resp["data"].get("sheet_names", []))
    return "Error listando pestañas"

# ── Tools para Claude ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "leer_sheet",
        "description": "Lee un rango de celdas del Google Sheet de finanzas. Úsalo para obtener datos de ingresos, egresos, PNL, flujo de caja, proyectado, etc. Si el nombre de la pestaña tiene espacios, usa comillas simples (ej: \"'Pottery Lab '!A1:F20\").",
        "input_schema": {
            "type": "object",
            "properties": {
                "rango": {
                    "type": "string",
                    "description": "Rango A1, ej: 'PNL!A1:F25', \"'Ingresos/Egresos Consolidados'!A1:J20\", 'Materia Prima!A1:F50'"
                }
            },
            "required": ["rango"]
        }
    },
    {
        "name": "agregar_fila",
        "description": "Agrega una fila nueva al final de una pestaña. Úsalo para registrar un egreso, ingreso, compra de materia prima, pago de mano de obra, etc. Lee primero la pestaña para conocer las columnas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rango": {"type": "string", "description": "Pestaña destino, ej: 'Materia Prima!A:F'"},
                "valores": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Valores por columna. Números sin $ ni puntos (ej: 736500)."
                }
            },
            "required": ["rango", "valores"]
        }
    },
    {
        "name": "actualizar_celda",
        "description": "Actualiza el valor de una celda específica. Para marcar pagos como 'OK Pagado', corregir montos, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rango": {"type": "string", "description": "Celda exacta, ej: 'Mano de Obra!F5'"},
                "valor": {"type": "string", "description": "Nuevo valor"}
            },
            "required": ["rango", "valor"]
        }
    },
    {
        "name": "listar_pestanas",
        "description": "Lista todas las pestañas del Sheet.",
        "input_schema": {"type": "object", "properties": {}}
    }
]

SYSTEM_PROMPT = """Eres el CFO virtual de Amphora B&C, empresa colombiana de cerámica artesanal.
Registras y analizas finanzas en Google Sheets. Respuestas CORTAS. Sin explicaciones innecesarias.

═══ PESTAÑA PRINCIPAL: "Movimientos" ═══
Columnas en orden exacto:
A: Fecha (DD/MM/AAAA)   B: Mes   C: Año   D: Tipo (Ingreso/Egreso)
E: Categoría (nombre EXACTO de la lista)   F: Descripción   G: Cliente/Proveedor
H: Método (Shopify | Bold | Efectivo | Transferencia | Nequi | Daviplata)
I: Monto (entero sin $ ni puntos: 75000)

═══ CATEGORÍAS VÁLIDAS ═══
INGRESOS: Ecommerce | Shop | Studio Amphora | Pottery Lab | Ceramikids | B2B | Personalización | Kintsugi | Otros Ingresos | Ingresos Financieros
EGRESOS Producción: Materia Prima | Mano de Obra | Costos Indirectos
EGRESOS Venta: Redes Sociales | Publicidad | Eventos | Envíos | Comisiones Pasarela | Fee Shopify | Empaques
EGRESOS Admin: Arriendo | Salario Gerente | Aportes | Contadora | Servicios Admin
EGRESOS Otros: Devoluciones | Gastos Financieros | Impuesto de Renta

═══ LECTURA DE PANTALLAZOS ═══
Extrae siempre estos 5 datos del comprobante:
  1. MONTO: valor principal (Total, Valor pagado, Monto). Sin $ ni puntos.
  2. FECHA: DD/MM/AAAA. Si no aparece → usa hoy.
  3. QUIÉN: nombre del negocio, persona o referencia.
  4. MÉTODO — detecta por logo/texto:
       Nequi (morado) → Nequi
       Bancolombia / Sucursal Virtual / transferencia interbancaria → Transferencia
       Daviplata (verde) → Daviplata
       Bold → Bold
       Recibo efectivo / caja registradora → Efectivo
  5. TIPO — busca frases clave:
       "recibiste" / "te pagaron" / "pago exitoso" / "ingreso" → Ingreso
       "pagaste" / "débito" / "cobro" / "salida" → Egreso
Si falta un dato, haz UNA sola pregunta.

═══ CLASIFICACIÓN ═══
Tienda/Bold/caja → Shop | Mensualidad/amphora/estudiante → Studio Amphora
Pottery Lab/taller → Pottery Lab | Ceramikids/niños → Ceramikids
Shopify/online → Ecommerce | Pedido especial/encargo → Personalización
B2B/corporativo/empresa → B2B | Kintsugi → Kintsugi
Arcilla/esmalte/insumo → Materia Prima | Jessica/Andrea/Don Jair/honorarios → Mano de Obra
Horno/mantenimiento equipo → Costos Indirectos
Instagram/redes/community → Redes Sociales | Pauta/ads → Publicidad
Evento/feria/activación → Eventos | Domicilio/envío → Envíos
Comisión/datáfono/pasarela → Comisiones Pasarela | Shopify plan → Fee Shopify
Arriendo/local/bodega → Arriendo | Sueldo gerente/Camilo → Salario Gerente
Aportes/seguridad social/salud/pensión/ARL → Aportes
Contadora/contador → Contadora | Internet/servicios/agua/luz → Servicios Admin
Impuesto/renta → Impuesto de Renta | Intereses deuda → Gastos Financieros

═══ FLUJO ═══
1. Si hay imagen: extrae los 5 datos. Si hay texto: interpreta.
2. Clasifica Tipo + Categoría.
3. agregar_fila en "Movimientos!A:I" con los 9 valores.
4. Responde: ✅ [Categoría] · $[monto con puntos] · [fecha]

═══ CONSULTAS ═══
PnL → leer_sheet("Resumen!A1:N50"). Filas 20/40/50 = márgenes %.
Nunca inventes cifras — siempre lee del Sheet.

═══ CONTEXTO ═══
Moneda COP. Empleados: Daniela (gerente), Jessica (talleres), Andrea (Ceramikids), Don Jair (mantenimiento).
"Amphoras" = estudiantes Studio Amphora. Responde en español."""

def descargar_foto(file_id: str):
    try:
        path = requests.get(f"{TG_API}/getFile", params={"file_id": file_id}, timeout=10).json()["result"]["file_path"]
        return requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}", timeout=30).content
    except Exception as e:
        print(f"Error descargando foto: {e}")
        return None


def procesar_mensaje(texto: str, foto_bytes=None) -> str:
    if foto_bytes:
        img_b64 = base64.standard_b64encode(foto_bytes).decode()
        content = []
        if texto:
            content.append({"type": "text", "text": texto})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}})
        if not texto:
            content.append({"type": "text", "text": "Analiza este pantallazo y registra el movimiento si puedes extraer la información. Si falta info, pregunta qué necesitas."})
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": texto}]

    while True:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    name, inp = block.name, block.input
                    if name == "leer_sheet":
                        resultado = leer_sheet(inp["rango"])
                    elif name == "agregar_fila":
                        resultado = agregar_fila(inp["rango"], inp["valores"])
                    elif name == "actualizar_celda":
                        resultado = actualizar_celda(inp["rango"], inp["valor"])
                    elif name == "listar_pestanas":
                        resultado = listar_pestanas()
                    else:
                        resultado = f"Herramienta desconocida: {name}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": resultado
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "Sin respuesta."

# ── Telegram polling ───────────────────────────────────────────────────────────

def tg_send(chat_id, texto):
    requests.post(f"{TG_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }, timeout=30)

def main():
    print("Bot @IraizozCFO_bot iniciado. Esperando mensajes...")
    offset = None

    while True:
        try:
            params = {"timeout": 20, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset

            resp = requests.get(f"{TG_API}/getUpdates", params=params, timeout=25).json()
            updates = resp.get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                texto = (msg.get("text") or msg.get("caption") or "").strip()

                # Descargar foto si viene adjunta
                foto_bytes = None
                if msg.get("photo"):
                    largest = max(msg["photo"], key=lambda p: p.get("file_size", 0))
                    foto_bytes = descargar_foto(largest["file_id"])

                if not chat_id or (not texto and not foto_bytes):
                    continue

                log_txt = texto if texto else "[foto]"
                print(f"[{chat_id}] {log_txt}")
                tg_send(chat_id, "⏳ Consultando...")

                try:
                    respuesta = procesar_mensaje(texto, foto_bytes)
                    tg_send(chat_id, respuesta)
                except Exception as e:
                    tg_send(chat_id, f"❌ Error: {e}")
                    print(f"Error: {e}")

        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            print(f"Error en polling: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
