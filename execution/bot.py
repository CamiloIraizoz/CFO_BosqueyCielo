#!/usr/bin/env python3
"""
Bot de Telegram CFO para Amphora B&C.
Uso local:  python3 execution/bot.py
Railway:    configura las env vars y haz deploy del repo.
"""
import os
import sys
import time
import base64
import requests
import anthropic
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=False)

sys.path.insert(0, str(Path(__file__).parent))
from sheets import leer_sheet, agregar_fila, actualizar_celda, listar_pestanas

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TG_API            = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

conversation_history: dict[int, list] = {}
REGISTRO_KEYWORDS = ["registré", "registrado", "anotado", "guardado", "agregado", "añadido", "✅"]

# ── Tools para Claude ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "leer_sheet",
        "description": "Lee un rango de celdas del Google Sheet de finanzas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rango": {"type": "string", "description": "Ej: 'Movimientos!A1:J500', 'Resumen!A1:N50'"}
            },
            "required": ["rango"]
        }
    },
    {
        "name": "agregar_fila",
        "description": "Registra un movimiento nuevo en Movimientos. SIEMPRE usar este tool para registrar — nunca solo describir el movimiento sin llamarlo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rango": {"type": "string", "description": "Siempre 'Movimientos!A:J'"},
                "valores": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "10 valores en orden: Fecha, Mes, Año, Tipo, Categoría, Descripción, Cliente/Proveedor, Método, Monto, Estado"
                }
            },
            "required": ["rango", "valores"]
        }
    },
    {
        "name": "actualizar_celda",
        "description": "Actualiza una celda específica. Para marcar Estado='OK' cuando se confirma pago.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rango": {"type": "string", "description": "Celda exacta, ej: 'Movimientos!J15'"},
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

SYSTEM_PROMPT = """Eres el CFO virtual de Amphora B&C (cerámica colombiana). Solo español.

REGLAS ABSOLUTAS DE RESPUESTA:
- Máximo 2 líneas por respuesta. NUNCA tablas. NUNCA listas con guiones.
- Al registrar: UNA sola línea de confirmación. Nada más.
- Al consultar: máximo 5 líneas en formato "Concepto: $monto".
- NUNCA digas que registraste algo sin haber llamado agregar_fila primero.
- NUNCA pidas información que ya tienes del historial o del pantallazo.

PESTAÑA: Movimientos — 10 columnas A:J
A:Fecha(DD/MM/AAAA) B:Mes C:Año D:Tipo E:Categoría F:Descripción G:Cliente/Proveedor H:Método I:Monto(sin$) J:Estado(vacío)

TIPOS: Ingreso / Egreso
MÉTODOS: Shopify | Bold | Efectivo | Transferencia | Nequi | Daviplata
ESTADO: siempre vacío al registrar (salvo pendiente explícito)

CATEGORÍAS INGRESO: Ecommerce | Shop | Studio Amphora | Pottery Lab | Ceramikids | B2B | Personalización | Kintsugi | Otros Ingresos | Ingresos Financieros
CATEGORÍAS EGRESO Producción: Materia Prima | Mano de Obra | Costos Indirectos
CATEGORÍAS EGRESO Venta: Redes Sociales | Publicidad | Eventos | Envíos | Comisiones Pasarela | Fee Shopify | Empaques
CATEGORÍAS EGRESO Admin: Arriendo | Salario Gerente | Aportes | Contadora | Servicios Admin
CATEGORÍAS EGRESO Otros: Devoluciones | Gastos Financieros | Impuesto de Renta

CLASIFICACIÓN:
Jessica/Andrea/Don Jair/honorarios→Mano de Obra | Arcilla/esmalte/insumo→Materia Prima | Horno/equipo→Costos Indirectos
Tienda/Bold/caja→Shop | Mensualidad/amphora/estudiante→Studio Amphora | Pottery Lab/taller adultos→Pottery Lab
Ceramikids/niños→Ceramikids | Shopify/online→Ecommerce | Pedido especial/encargo→Personalización | B2B/empresa→B2B
Redes/community→Redes Sociales | Pauta/ads→Publicidad | Evento/feria→Eventos | Domicilio/envío→Envíos
Pasarela/datáfono→Comisiones Pasarela | Plan Shopify→Fee Shopify | Arriendo/local→Arriendo
Sueldo Camilo/gerente→Salario Gerente | Salud/pensión/ARL→Aportes | Contadora→Contadora | Internet/agua/luz→Servicios Admin

DETECCIÓN EN PANTALLAZO:
- "Transferencia exitosa" + Bancolombia/sucursal virtual → Método=Transferencia, Tipo=Egreso
- "recibiste"/"te pagaron"/"pago exitoso" → Tipo=Ingreso
- Nequi(morado)→Nequi | Daviplata(verde)→Daviplata | Bold→Bold | caja/recibo→Efectivo
- Usuario dice "en efectivo" → Método=Efectivo, no preguntes

FLUJO DE REGISTRO — SIGUE ESTE ORDEN EXACTO:
1. Con el pantallazo + texto, extrae: Monto · Fecha · Tipo · Categoría · Quién · Método
2. Si tienes Monto + Tipo + Categoría → registra AHORA con agregar_fila. No esperes más.
   Si falta solo Quién → usa la descripción disponible y registra igual.
   Si falta Monto → pregunta solo "¿Cuánto?"
   Si falta Categoría → pregunta solo "¿Es [A] o [B]?"
3. Llama agregar_fila con los 10 valores.
4. Responde SOLO: ✅ Categoría · $monto · fecha · método

CUENTAS PENDIENTES:
"¿qué debo?" → leer Movimientos!A1:J500, mostrar Egresos con Estado vacío: "Categoría · $monto · fecha"
"¿me deben?" → leer Movimientos!A1:J500, mostrar Ingresos con Estado vacío: mismo formato
Confirmar pago → actualizar_celda columna J a "OK"

PNL: leer_sheet("Resumen!A1:N50"). Filas 20/39/49=márgenes%. Nunca inventes cifras.

CONTEXTO: COP. Quien usa este bot es Camilo (dueño/CFO). Daniela=gerente operativa, Jessica=talleres, Andrea=Ceramikids, Don Jair=mantenimiento. Amphoras=estudiantes."""


def descargar_foto(file_id: str):
    try:
        path = requests.get(f"{TG_API}/getFile", params={"file_id": file_id}, timeout=10).json()["result"]["file_path"]
        return requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}", timeout=30).content
    except Exception as e:
        print(f"Error descargando foto: {e}")
        return None


def procesar_mensaje(chat_id: int, texto: str, foto_bytes=None) -> str:
    history = conversation_history.get(chat_id, [])

    if foto_bytes:
        img_b64 = base64.standard_b64encode(foto_bytes).decode()
        content = []
        if texto:
            content.append({"type": "text", "text": texto})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}})
        if not texto:
            content.append({"type": "text", "text": "Registra este movimiento."})
        history_user_text = f"[pantallazo] {texto}".strip()
    else:
        content = texto
        history_user_text = texto

    messages = history + [{"role": "user", "content": content}]
    agregar_fila_llamado = False
    intentos = 0
    iteraciones = 0

    while iteraciones < 6:
        iteraciones += 1
        tool_choice = {"type": "any"} if intentos > 0 else {"type": "auto"}

        for retry in range(4):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=512,
                    system=SYSTEM_PROMPT + f"\n\nFECHA HOY: {date.today().strftime('%d/%m/%Y')}",
                    tools=TOOLS,
                    tool_choice=tool_choice,
                    messages=messages
                )
                break
            except anthropic.RateLimitError:
                if retry == 3:
                    raise
                wait = 15 * (retry + 1)
                print(f"Rate limit — esperando {wait}s...")
                time.sleep(wait)

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    name, inp = block.name, block.input
                    if name == "leer_sheet":
                        resultado = leer_sheet(inp["rango"])
                    elif name == "agregar_fila":
                        resultado = agregar_fila(inp["rango"], inp["valores"])
                        agregar_fila_llamado = True
                    elif name == "actualizar_celda":
                        resultado = actualizar_celda(inp["rango"], inp["valor"])
                    elif name == "listar_pestanas":
                        resultado = listar_pestanas()
                    else:
                        resultado = f"Herramienta desconocida: {name}"
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": resultado})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            respuesta = next((b.text for b in response.content if hasattr(b, "text")), "Sin respuesta.")

            parece_registro = any(k in respuesta.lower() for k in REGISTRO_KEYWORDS)
            if parece_registro and not agregar_fila_llamado and intentos == 0:
                print(f"[{chat_id}] Alucinación detectada — forzando agregar_fila")
                intentos += 1
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": [{
                    "type": "text",
                    "text": "IMPORTANTE: Dijiste que registraste pero NO llamaste agregar_fila. Llama agregar_fila ahora."
                }]})
                continue

            new_history = history + [
                {"role": "user", "content": history_user_text},
                {"role": "assistant", "content": respuesta}
            ]
            conversation_history[chat_id] = new_history[-10:]
            return respuesta

    return "⚠️ No pude completar la operación. Intenta de nuevo."


def tg_send(chat_id, texto):
    requests.post(f"{TG_API}/sendMessage", json={
        "chat_id": chat_id, "text": texto, "parse_mode": "Markdown"
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

                if texto.lower() in ("/reset", "reset", "nuevo"):
                    conversation_history.pop(chat_id, None)
                    tg_send(chat_id, "Historial borrado. ¿Qué necesitas?")
                    continue

                foto_bytes = None
                if msg.get("photo"):
                    largest = max(msg["photo"], key=lambda p: p.get("file_size", 0))
                    foto_bytes = descargar_foto(largest["file_id"])

                if not chat_id or (not texto and not foto_bytes):
                    continue

                print(f"[{chat_id}] {texto or '[foto]'}")
                tg_send(chat_id, "⏳")
                try:
                    respuesta = procesar_mensaje(chat_id, texto, foto_bytes)
                    tg_send(chat_id, respuesta)
                except Exception as e:
                    tg_send(chat_id, f"❌ Error: {e}")
                    print(f"Error procesando: {e}")

        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            print(f"Error en polling: {e}")
            time.sleep(5)


if __name__ == "__main__":
    lockfile = Path(__file__).parent.parent / ".tmp" / "bot.lock"
    lockfile.parent.mkdir(exist_ok=True)
    if lockfile.exists():
        existing_pid = lockfile.read_text().strip()
        try:
            os.kill(int(existing_pid), 0)
            print(f"Bot ya está corriendo (PID {existing_pid}). Saliendo.")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass
    lockfile.write_text(str(os.getpid()))
    try:
        main()
    finally:
        lockfile.unlink(missing_ok=True)
