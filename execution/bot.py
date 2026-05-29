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
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=False)

sys.path.insert(0, str(Path(__file__).parent))
from sheets import leer_sheet, agregar_fila, actualizar_celda, listar_pestanas, leer_sheet_numericos
from hubspot import buscar_contacto, crear_contacto, crear_deal, actualizar_deal, listar_deals, agregar_nota
from email_sender import enviar_cotizacion, enviar_cotizacion_pottery
from recordatorio_amphoritas import leer_amphoritas, leer_pagos_mes, ya_pago, enviar_recordatorio as _enviar_recordatorio

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ADMIN_CHAT_ID            = os.getenv("ADMIN_CHAT_ID")
PRODUCTION_GROUP_CHAT_ID = os.getenv("PRODUCTION_GROUP_CHAT_ID")
TG_API            = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

conversation_history: dict[int, list] = {}

_MESES_ES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
             "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
_ultima_check_recordatorio = 0.0
_ultima_check_entregas     = 0.0
_ultima_check_semanal      = 0.0

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
    },

    # ── HubSpot CRM ──────────────────────────────────────────────────────────────
    {
        "name": "buscar_contacto_hs",
        "description": "Busca contactos en HubSpot por nombre, empresa o email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nombre, empresa o email a buscar"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "crear_contacto_hs",
        "description": "Crea un nuevo contacto en HubSpot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre":   {"type": "string"},
                "empresa":  {"type": "string"},
                "email":    {"type": "string"},
                "telefono": {"type": "string"}
            },
            "required": ["nombre", "empresa"]
        }
    },
    {
        "name": "crear_deal_hs",
        "description": "Crea un negocio en el pipeline de HubSpot. Etapas: analisis, conceptualizacion, propuesta, ajustes, aprobacion, produccion, entrega, perdido.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre_deal": {"type": "string", "description": "Ej: 'Pedido B2B — Empresa XYZ'"},
                "contacto_id": {"type": "string", "description": "ID del contacto en HubSpot"},
                "etapa":       {"type": "string", "description": "lead | cotizacion | negociacion | anticipo_recibido | en_produccion | listo_entrega | entregado | lost"},
                "valor":       {"type": "integer", "description": "Valor estimado en COP"},
                "descripcion": {"type": "string"}
            },
            "required": ["nombre_deal", "etapa"]
        }
    },
    {
        "name": "actualizar_deal_hs",
        "description": "Actualiza etapa, valor o notas de un negocio en HubSpot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "etapa":   {"type": "string"},
                "valor":   {"type": "integer"},
                "notas":   {"type": "string"}
            },
            "required": ["deal_id"]
        }
    },
    {
        "name": "listar_deals_hs",
        "description": "Lista negocios del pipeline de HubSpot, opcionalmente filtrados por etapa.",
        "input_schema": {
            "type": "object",
            "properties": {
                "etapa": {"type": "string", "description": "Filtro opcional: analisis | propuesta | aprobacion | etc."}
            }
        }
    },
    {
        "name": "agregar_nota_hs",
        "description": "Agrega una nota de actividad a un negocio en HubSpot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "nota":    {"type": "string"}
            },
            "required": ["deal_id", "nota"]
        }
    },

    # ── Cotizaciones / Email ──────────────────────────────────────────────────────
    {
        "name": "enviar_cotizacion",
        "description": "Genera y envía cotización por email al cliente. SOLO llamar después de que el usuario confirme explícitamente el envío. Siempre muestra resumen y espera 'sí, confirmo' antes de llamar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_nombre":   {"type": "string"},
                "cliente_empresa":  {"type": "string"},
                "cliente_email":    {"type": "string", "description": "Email del cliente — requerido"},
                "cliente_telefono": {"type": "string"},
                "productos": {
                    "type": "array",
                    "description": "Lista de productos cotizados",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre":          {"type": "string"},
                            "descripcion":     {"type": "string"},
                            "cantidad":        {"type": "integer"},
                            "precio_unitario": {"type": "integer"}
                        },
                        "required": ["nombre", "cantidad", "precio_unitario"]
                    }
                },
                "envio":            {"type": "integer", "description": "Costo de envío en COP (0 si incluido)"},
                "notas":            {"type": "string"},
                "plazo_entrega":    {"type": "string", "description": "Ej: '4-6 semanas hábiles'"},
                "condiciones_pago": {"type": "string", "description": "Ej: '50% anticipo · 50% contra entrega'"},
                "fecha":            {"type": "string", "description": "Fecha formato DD/MM/AAAA"}
            },
            "required": ["cliente_nombre", "cliente_email", "productos"]
        }
    },
    {
        "name": "enviar_cotizacion_pottery",
        "description": "Genera y envía cotización Pottery Lab (talleres/experiencias) por email. SOLO llamar después de confirmación explícita del usuario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_nombre":   {"type": "string"},
                "cliente_empresa":  {"type": "string"},
                "cliente_email":    {"type": "string"},
                "cliente_telefono": {"type": "string"},
                "taller_tipo":      {"type": "string", "description": "Tipo de evento: Cumpleaños | Team building | Despedida | Corporativo | etc."},
                "taller_ejercicio": {"type": "string", "description": "Ej: 'Esmaltado — 1 pieza', 'Torno — pieza libre'"},
                "taller_lugar":     {"type": "string", "description": "Ubicación: 'Estudio Amphora' o dirección del cliente"},
                "taller_fecha":     {"type": "string", "description": "Fecha del taller DD/MM/AAAA"},
                "taller_duracion":  {"type": "string", "description": "Ej: '1.5 horas', '2 horas'"},
                "taller_participantes":    {"type": "integer"},
                "taller_precio_por_persona": {"type": "integer", "description": "Precio por persona en COP"},
                "inclusiones":      {"type": "string", "description": "Qué incluye. Default: materiales + piezas + horneada + entrega"},
                "condiciones_pago": {"type": "string"},
                "notas":            {"type": "string"},
                "fecha":            {"type": "string", "description": "Fecha de emisión DD/MM/AAAA"}
            },
            "required": ["cliente_nombre", "cliente_email", "taller_tipo", "taller_participantes", "taller_precio_por_persona"]
        }
    },

    # ── Producción ───────────────────────────────────────────────────────────────
    {
        "name": "agregar_pedido_produccion",
        "description": "Registra un nuevo pedido en la pestaña Producción. Llamar cuando un deal pasa a producción o Daniela confirma inicio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente":       {"type": "string"},
                "descripcion":   {"type": "string", "description": "Ej: '20 tazas logo empresa'"},
                "proceso":       {"type": "integer", "description": "1=Clásico (modelado→entregado) | 2=Bizcocho (esmaltado inicial→entregado)"},
                "fecha_entrega": {"type": "string", "description": "DD/MM/YYYY"},
                "deal_id":       {"type": "string"},
                "notas":         {"type": "string"}
            },
            "required": ["cliente", "descripcion", "proceso", "fecha_entrega"]
        }
    },
    {
        "name": "actualizar_etapa_produccion",
        "description": "Actualiza la etapa de producción de un pedido. Llamar cuando Daniela informa avance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente": {"type": "string"},
                "etapa":   {"type": "string", "description": "Proceso 1: modelado|secado|primera quema|esmaltado|segunda quema|acabado|empaque|entregado · Proceso 2: esmaltado inicial|pintar bizcocho|primera quema|acabado|empaque|entregado"},
                "notas":   {"type": "string"}
            },
            "required": ["cliente", "etapa"]
        }
    },
    {
        "name": "leer_produccion",
        "description": "Lee el estado actual de todos los pedidos en producción.",
        "input_schema": {"type": "object", "properties": {}}
    },

    # ── Flujo de caja ────────────────────────────────────────────────────────────
    {
        "name": "reporte_flujo_caja",
        "description": "Genera reporte de flujo de caja: proyectado vs real del mes actual. Llamar ante cualquier pregunta sobre cómo van las finanzas, el presupuesto o el flujo.",
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

CONTEXTO: COP. Quien usa este bot es Camilo (dueño/CFO). Daniela=gerente operativa, Jessica=talleres, Andrea=Ceramikids, Don Jair=mantenimiento. Amphoras=estudiantes.

────────────────────────────────────────
MÓDULO HUBSPOT — PIPELINE B2B
────────────────────────────────────────
ETAPAS (en orden): lead → cotizacion → negociacion → anticipo_recibido → en_produccion → listo_entrega → entregado | lost

FLUJO LEAD NUEVO:
1. Si el cliente no existe → crear_contacto_hs(nombre, empresa, email, telefono)
2. crear_deal_hs(nombre_deal, contacto_id, etapa="lead", valor_estimado)
3. Confirmar: "Lead [Empresa] creado. Deal ID:[id]"

CONSULTAS HUBSPOT:
"¿qué leads hay?" / "pipeline" → listar_deals_hs()
"leads en cotizacion" → listar_deals_hs(etapa="cotizacion")
"busca [nombre/empresa]" → buscar_contacto_hs(query)
"avanza deal [id] a [etapa]" → actualizar_deal_hs(deal_id, etapa)
Cuando deal llega a "anticipo_recibido" → recordar crear pedido en producción con agregar_pedido_produccion

REGLAS HUBSPOT:
- NUNCA inventes IDs. Busca primero con buscar_contacto_hs si no tienes el ID.
- Al crear deal sin contacto_id, pasa contacto_id="" (el deal queda sin asociar).
- Usa agregar_nota_hs para registrar reuniones, llamadas o acuerdos relevantes.

────────────────────────────────────────
MÓDULO COTIZACIONES — DOS PLANTILLAS
────────────────────────────────────────
HAY DOS TIPOS DE COTIZACIÓN. Detecta cuál usar por el contexto:

🏺 enviar_cotizacion → Bosque y Cielo PRODUCTOS (cerámica, homeware, B2B, personalización)
   Datos: nombre, empresa, email cliente + lista de productos (nombre, cantidad, precio_unitario) + plazo + condiciones

🎨 enviar_cotizacion_pottery → Pottery Lab EXPERIENCIAS (talleres, cumpleaños, team building, corporativos)
   Datos: nombre, empresa, email cliente + taller (tipo, ejercicio, lugar, fecha, duración, participantes, precio_por_persona)
   Total = participantes × precio_por_persona. Anticipo = Total / 2.

FLUJO COTIZACIÓN (aplica a ambas):
1. Recopila todos los datos. Si falta email → pregunta solo "¿Email del cliente?".
2. Muestra resumen antes de enviar:
   "📋 Cotización [Empresa]:
   [Detalle del pedido o taller]
   Total: $[total] · Envío a: [email]
   ¿Confirmo envío?"
3. SOLO si el usuario dice "sí" → llamar el tool correspondiente.
4. Confirmar con: ✅ + número generado.

REGLAS:
- NUNCA enviar sin confirmación explícita.
- Condiciones default productos: "50% anticipo · 50% contra entrega".
- Condiciones default pottery: "50% anticipo para reservar · 50% el día del taller".
- Plazo default productos: "4-6 semanas hábiles".
- La cotización llega CC a Daniela y Camilo automáticamente.

────────────────────────────────────────
MÓDULO PRODUCCIÓN — DOS PROCESOS
────────────────────────────────────────
PROCESO 1 (Clásico):  modelado → secado → primera quema → esmaltado → segunda quema → acabado → empaque → entregado
PROCESO 2 (Bizcocho): esmaltado inicial → pintar bizcocho → primera quema → acabado → empaque → entregado

FLUJO NUEVO PEDIDO:
- Deal pasa a "produccion" o Daniela confirma inicio → agregar_pedido_produccion
- Etapa inicial automática: Proceso 1→modelado | Proceso 2→esmaltado inicial
- Confirmar: "Pedido [cliente] registrado · Proceso [N] · Entrega [fecha]"

ACTUALIZAR (comandos de Daniela):
"avanza [cliente] a [etapa]" | "[cliente] ya está en [etapa]" | "listo el [etapa] de [cliente]"
→ actualizar_etapa_produccion(cliente, etapa)
Si etapa="entregado" y hay deal_id → también actualizar_deal_hs(deal_id, etapa="entrega")

CONSULTAS:
"¿qué entrega esta semana?" | "¿en qué está [cliente]?" | "¿qué hay en producción?"
→ leer_produccion + filtrar según pregunta · mostrar: cliente · etapa · fecha entrega

REGLAS:
- NUNCA marcar entregado sin confirmación explícita.
- Daniela habla operativamente: mensajes cortos son comandos de producción.

────────────────────────────────────────
MÓDULO FLUJO DE CAJA
────────────────────────────────────────
"flujo de caja" | "¿cómo vamos?" | "proyectado vs real" | "presupuesto" → reporte_flujo_caja()
Muestra ingresos y egresos reales vs proyectados del mes con % de avance por categoría.
El reporte llega automáticamente cada lunes."""


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
    iteraciones = 0

    while iteraciones < 6:
        iteraciones += 1

        for retry in range(4):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=512,
                    system=SYSTEM_PROMPT + f"\n\nFECHA HOY: {date.today().strftime('%d/%m/%Y')}",
                    tools=TOOLS,
                    tool_choice={"type": "auto"},
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
                    elif name == "actualizar_celda":
                        resultado = actualizar_celda(inp["rango"], inp["valor"])
                    elif name == "listar_pestanas":
                        resultado = listar_pestanas()
                    # ── HubSpot ──────────────────────────────────────────────
                    elif name == "buscar_contacto_hs":
                        resultado = buscar_contacto(inp["query"])
                    elif name == "crear_contacto_hs":
                        resultado = crear_contacto(
                            inp["nombre"], inp["empresa"],
                            inp.get("email", ""), inp.get("telefono", "")
                        )
                    elif name == "crear_deal_hs":
                        resultado = crear_deal(
                            inp["nombre_deal"], inp.get("contacto_id", ""),
                            inp["etapa"], inp.get("valor", 0), inp.get("descripcion", "")
                        )
                    elif name == "actualizar_deal_hs":
                        resultado = actualizar_deal(
                            inp["deal_id"], inp.get("etapa", ""),
                            inp.get("valor"), inp.get("notas", "")
                        )
                    elif name == "listar_deals_hs":
                        resultado = listar_deals(inp.get("etapa", ""))
                    elif name == "agregar_nota_hs":
                        resultado = agregar_nota(inp["deal_id"], inp["nota"])
                    # ── Cotizaciones / Email ──────────────────────────────────
                    elif name == "enviar_cotizacion":
                        datos = {
                            "cliente": {
                                "nombre":   inp.get("cliente_nombre", ""),
                                "empresa":  inp.get("cliente_empresa", ""),
                                "email":    inp.get("cliente_email", ""),
                                "telefono": inp.get("cliente_telefono", ""),
                            },
                            "productos":        inp.get("productos", []),
                            "envio":            inp.get("envio", 0),
                            "notas":            inp.get("notas", ""),
                            "plazo_entrega":    inp.get("plazo_entrega", "4-6 semanas hábiles"),
                            "condiciones_pago": inp.get("condiciones_pago", "50% anticipo · 50% contra entrega"),
                            "fecha":            inp.get("fecha", date.today().strftime("%d/%m/%Y")),
                        }
                        resultado = enviar_cotizacion(datos)
                    elif name == "enviar_cotizacion_pottery":
                        datos = {
                            "cliente": {
                                "nombre":   inp.get("cliente_nombre", ""),
                                "empresa":  inp.get("cliente_empresa", ""),
                                "email":    inp.get("cliente_email", ""),
                                "telefono": inp.get("cliente_telefono", ""),
                            },
                            "taller": {
                                "tipo":             inp.get("taller_tipo", ""),
                                "ejercicio":        inp.get("taller_ejercicio", ""),
                                "lugar":            inp.get("taller_lugar", ""),
                                "fecha_taller":     inp.get("taller_fecha", ""),
                                "duracion":         inp.get("taller_duracion", ""),
                                "participantes":    inp.get("taller_participantes", 1),
                                "precio_por_persona": inp.get("taller_precio_por_persona", 0),
                            },
                            "inclusiones":      inp.get("inclusiones", ""),
                            "condiciones_pago": inp.get("condiciones_pago", "50% anticipo para reservar · 50% el día del taller"),
                            "notas":            inp.get("notas", ""),
                            "fecha":            inp.get("fecha", date.today().strftime("%d/%m/%Y")),
                        }
                        resultado = enviar_cotizacion_pottery(datos)
                    # ── Producción ───────────────────────────────────────────
                    elif name == "agregar_pedido_produccion":
                        resultado = _prod_agregar(
                            inp["cliente"], inp["descripcion"],
                            inp.get("proceso", 1), inp["fecha_entrega"],
                            inp.get("deal_id", ""), inp.get("notas", "")
                        )
                    elif name == "actualizar_etapa_produccion":
                        resultado = _prod_actualizar(
                            inp["cliente"], inp["etapa"], inp.get("notas", "")
                        )
                    elif name == "leer_produccion":
                        resultado = leer_sheet("Producción!A:J")
                    elif name == "reporte_flujo_caja":
                        resultado = _generar_reporte_flujo()
                    else:
                        resultado = f"Herramienta desconocida: {name}"
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": resultado})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            respuesta = next((b.text for b in response.content if hasattr(b, "text")), "Sin respuesta.")
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


# ── Recordatorios programados ─────────────────────────────────────────────────

def _generar_reporte_flujo(mes_num=None, anio=None):
    from datetime import timedelta as _td
    hoy = datetime.now()
    if mes_num is None: mes_num = hoy.month
    if anio is None:    anio    = hoy.year

    presup = leer_sheet_numericos("Presupuesto 2026!A:I")
    if not presup:
        return "Sin datos en Presupuesto 2026."

    header = presup[0] if presup else []
    mes_col = None
    meses_short = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,
                   "jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12}
    for i, h in enumerate(header):
        if isinstance(h, (int, float)):
            try:
                d = date(1899, 12, 30) + _td(days=int(h))
                if d.month == mes_num and d.year == anio:
                    mes_col = i
                    break
            except Exception:
                pass
        elif isinstance(h, str) and str(anio) in h:
            if meses_short.get(h[:3].lower()) == mes_num:
                mes_col = i
                break

    if mes_col is None:
        return f"No encontré columna para {_MESES_ES[mes_num]} {anio} en Presupuesto 2026."

    proyectado = {}
    for fila in presup[1:]:
        if len(fila) <= mes_col:
            continue
        tipo = str(fila[0]).strip().upper()
        cat  = str(fila[1]).strip()
        if tipo not in ("INGRESO", "EGRESO") or not cat:
            continue
        if "TOTAL" in cat.upper() or "──" in cat:
            continue
        try:
            proyectado[(tipo, cat)] = float(fila[mes_col] or 0)
        except (ValueError, TypeError):
            proyectado[(tipo, cat)] = 0.0

    movs = leer_sheet_numericos("Movimientos!A:J")
    real = {}
    mes_nombres = {m.lower(): i for i, m in enumerate(_MESES_ES) if i > 0}
    for fila in movs[1:]:
        if len(fila) < 9:
            continue
        try:
            mes_v = mes_nombres.get(str(fila[1]).strip().lower(), 0)
            año_v = int(float(fila[2])) if fila[2] else 0
            if mes_v != mes_num or año_v != anio:
                continue
            tipo  = str(fila[3]).strip().upper()
            cat   = str(fila[4]).strip()
            monto = float(fila[8]) if fila[8] else 0
            real[(tipo, cat)] = real.get((tipo, cat), 0) + monto
        except Exception:
            continue

    def fmt(n):
        return f"${n/1_000_000:.1f}M" if abs(n) >= 1_000_000 else f"${n:,.0f}"

    total_ing_p = total_ing_r = 0
    total_egr_p = total_egr_r = 0
    lines_ing = []
    lines_egr = []

    for (tipo, cat), proy in sorted(proyectado.items(), key=lambda x: x[0][1]):
        act = real.get((tipo, cat), 0)
        if proy == 0 and act == 0:
            continue
        pct = int(act / proy * 100) if proy > 0 else (100 if act > 0 else 0)
        ico = "✅" if pct >= 90 else ("⚠️" if pct >= 50 else "🔴")
        line = f"  {ico} {cat}: {fmt(act)} / {fmt(proy)} ({pct}%)"
        if tipo == "INGRESO":
            lines_ing.append(line)
            total_ing_p += proy
            total_ing_r += act
        else:
            lines_egr.append(line)
            total_egr_p += proy
            total_egr_r += act

    flujo_r = total_ing_r - total_egr_r
    flujo_p = total_ing_p - total_egr_p
    semana  = (hoy.day - 1) // 7 + 1

    msg  = f"📊 *Flujo de Caja — {_MESES_ES[mes_num]} {anio}* (semana {semana})\n\n"
    msg += f"💰 *INGRESOS* {fmt(total_ing_r)} / {fmt(total_ing_p)}\n"
    msg += "\n".join(lines_ing) + "\n\n"
    msg += f"💸 *EGRESOS* {fmt(total_egr_r)} / {fmt(total_egr_p)}\n"
    msg += "\n".join(lines_egr) + "\n\n"
    ico_neto = "✅" if flujo_r >= flujo_p * 0.9 else ("⚠️" if flujo_r >= 0 else "🔴")
    msg += f"{ico_neto} *Flujo neto: {fmt(flujo_r)}* (proy: {fmt(flujo_p)})"
    return msg


def verificar_reporte_semanal():
    global _ultima_check_semanal
    ahora = time.time()
    if ahora - _ultima_check_semanal < 3600 * 6:
        return
    _ultima_check_semanal = ahora
    hoy = datetime.now()
    if hoy.weekday() != 0:  # Solo lunes
        return
    if not ADMIN_CHAT_ID:
        return
    try:
        reporte = _generar_reporte_flujo()
        tg_send(int(ADMIN_CHAT_ID), reporte)
        print(f"[Reporte semanal] Enviado — {hoy.strftime('%d/%m/%Y')}")
    except Exception as e:
        print(f"[Reporte semanal] Error: {e}")


def _prod_agregar(cliente, descripcion, proceso, fecha_entrega, deal_id="", notas=""):
    filas = leer_sheet_numericos("Producción!A:A")
    num = max(len(filas), 1)
    etapa_inicial = "modelado" if int(proceso) == 1 else "esmaltado inicial"
    hoy = datetime.now().strftime("%d/%m/%Y")
    row = [num, cliente, descripcion, deal_id, proceso, hoy, fecha_entrega, etapa_inicial, hoy, notas]
    return agregar_fila("Producción!A:J", row)


def _prod_actualizar(cliente, etapa, notas=""):
    filas = leer_sheet_numericos("Producción!A:J")
    for i, fila in enumerate(filas[1:], start=2):
        nombre = str(fila[1]).strip().lower() if len(fila) > 1 else ""
        if cliente.lower() in nombre or nombre in cliente.lower():
            hoy = datetime.now().strftime("%d/%m/%Y")
            actualizar_celda(f"Producción!H{i}", etapa)
            actualizar_celda(f"Producción!I{i}", hoy)
            if notas:
                actualizar_celda(f"Producción!J{i}", notas)
            return f"✅ {str(fila[1]).strip()} actualizado a '{etapa}'."
    return f"No encontré pedido de '{cliente}' en producción."


def verificar_entregas_proximas():
    global _ultima_check_entregas
    ahora = time.time()
    if ahora - _ultima_check_entregas < 3600 * 6:
        return
    _ultima_check_entregas = ahora

    if not PRODUCTION_GROUP_CHAT_ID:
        return

    try:
        filas = leer_sheet_numericos("Producción!A:J")
        hoy = datetime.now().date()
        alertas_entrega = []
        alertas_stall   = []

        for fila in filas[1:]:
            if len(fila) < 8:
                continue
            cliente = str(fila[1]).strip() if len(fila) > 1 else "?"
            etapa   = str(fila[7]).strip().lower() if len(fila) > 7 else ""
            if etapa in ("entregado", ""):
                continue

            # Entrega próxima (≤3 días)
            fecha_str = str(fila[6]).strip() if len(fila) > 6 else ""
            if "/" in fecha_str:
                try:
                    p = fecha_str.split("/")
                    fecha_e = date(int(p[2]), int(p[1]), int(p[0]))
                    dias = (fecha_e - hoy).days
                    if 0 <= dias <= 3:
                        alertas_entrega.append(f"• {cliente} — {dias}d ({fecha_str}) · {fila[7]}")
                except Exception:
                    pass

            # Stall: +14 días sin actualización
            ult_str = str(fila[8]).strip() if len(fila) > 8 else ""
            if "/" in ult_str:
                try:
                    p = ult_str.split("/")
                    ult = date(int(p[2]), int(p[1]), int(p[0]))
                    if (hoy - ult).days >= 14:
                        alertas_stall.append(f"• {cliente} · sin actualizar hace {(hoy - ult).days}d · {fila[7]}")
                except Exception:
                    pass

        msg = ""
        if alertas_entrega:
            msg += "⚠️ *Entregas próximas (≤3 días):*\n" + "\n".join(alertas_entrega) + "\n\n"
        if alertas_stall:
            msg += "🔴 *Pedidos sin actualizar (+14 días):*\n" + "\n".join(alertas_stall)
        if msg:
            tg_send(int(PRODUCTION_GROUP_CHAT_ID), msg.strip())
    except Exception as e:
        print(f"[Entregas] Error: {e}")


def _leer_ultimo_recordatorio() -> str:
    try:
        val = leer_sheet("Amphoritas!B17")
        return val.strip() if not val.startswith("(rango") else ""
    except Exception:
        return ""

def _guardar_ultimo_recordatorio(mes_str: str):
    try:
        actualizar_celda("Amphoritas!A17", "_ultimo_recordatorio")
        actualizar_celda("Amphoritas!B17", mes_str)
    except Exception as e:
        print(f"[Recordatorio] Error guardando estado: {e}")

def verificar_recordatorios():
    global _ultima_check_recordatorio
    ahora = time.time()
    if ahora - _ultima_check_recordatorio < 3600:
        return
    _ultima_check_recordatorio = ahora

    hoy = datetime.now()
    if hoy.day < 10:
        return

    mes_str = f"{_MESES_ES[hoy.month]} {hoy.year}"
    if _leer_ultimo_recordatorio() == mes_str:
        return

    print(f"[Recordatorio] Iniciando envío {mes_str}...")
    try:
        amphoritas = leer_amphoritas()
        pagados    = leer_pagos_mes(hoy.month, hoy.year)
        pendientes = [a for a in amphoritas if not ya_pago(a["nombre"], pagados)]

        enviados = 0
        for a in pendientes:
            if _enviar_recordatorio(a["nombre"], a["email"], mes_str,
                                    a["mensualidad"], dry_run=False):
                enviados += 1

        _guardar_ultimo_recordatorio(mes_str)
        print(f"[Recordatorio] {enviados}/{len(pendientes)} enviados — {mes_str}")

        if ADMIN_CHAT_ID and pendientes:
            lista = "\n".join(f"• {a['nombre']}" for a in pendientes)
            tg_send(int(ADMIN_CHAT_ID),
                    f"📧 Recordatorios {mes_str}: {enviados} emails enviados.\n{lista}")
    except Exception as e:
        print(f"[Recordatorio] Error: {e}")


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

                if texto.lower() == "/chatid":
                    tg_send(chat_id, f"Tu chat ID es: `{chat_id}`")
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
            pass
        except Exception as e:
            print(f"Error en polling: {e}")
            time.sleep(5)

        verificar_recordatorios()
        verificar_entregas_proximas()
        verificar_reporte_semanal()


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
