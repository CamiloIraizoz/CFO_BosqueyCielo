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
from sheets import leer_sheet, agregar_fila, actualizar_celda, listar_pestanas, leer_sheet_numericos, \
    crear_pestana, escribir_rango
from hubspot import buscar_contacto, crear_contacto, crear_deal, actualizar_deal, listar_deals, agregar_nota, \
    registrar_cotizacion as registrar_cotizacion_hs
from email_sender import enviar_cotizacion, enviar_cotizacion_pottery, preparar_cotizacion
from competencia import barrer as _comp_barrer, guardar as _comp_guardar, resumen as _comp_resumen
from jornadas import registrar as _jor_registrar, resumen as _jor_resumen, \
    bitacora as _jor_bitacora, avance_pedido as _jor_avance
from pendientes import agregar as _pend_agregar, leer as _pend_leer, cerrar as _pend_cerrar
from registro_cotizaciones import guardar_fila as _reg_cot_fila, leer as _reg_cot_leer, \
    marcar_estado as _reg_cot_estado
from movimientos import registrar as _mov_registrar, leer as _mov_leer
from proyectos import crear as _proy_crear, pnl as _proy_pnl, por_linea as _proy_lineas, \
    listar as _proy_listar, reconstruir as _proy_reconstruir
from avance import estado as _av_estado, recalcular as _av_recalcular
from cotizador import cotizar as _cotizar, grado_acabado as _grado_acabado, formato_telegram as _cot_formato, \
    guardar_parametro as _cot_guardar_param, parametros_pendientes as _cot_pendientes, PARAMS_PREGUNTABLES as _COT_PREGUNTAS, \
    guardar_hoja_cotizacion as _cot_guardar_hoja, guardar_tiempo as _cot_guardar_tiempo, \
    cotizar_pedido as _cotizar_pedido, formato_telegram_pedido as _cot_formato_pedido, \
    guardar_hoja_pedido as _cot_guardar_hoja_pedido, AJUSTES_LINEA as _COT_AJUSTES
from recordatorio_amphoritas import leer_amphoritas, leer_pagos_mes, ya_pago, enviar_recordatorio as _enviar_recordatorio
from meta_ads import listar_campanas as meta_listar_campanas, obtener_insights as meta_obtener_insights, \
    pausar_campana as meta_pausar_campana, reanudar_campana as meta_reanudar_campana, \
    actualizar_presupuesto as meta_actualizar_presupuesto, crear_campana_completa as meta_crear_campana_completa

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ADMIN_CHAT_ID            = os.getenv("ADMIN_CHAT_ID")
PRODUCTION_GROUP_CHAT_ID = os.getenv("PRODUCTION_GROUP_CHAT_ID")


# ── Quién puede hablarle al bot, y de qué ────────────────────────────────────
# El bot llega a la cartera, al flujo de caja y a Meta Ads. Sin roles, darle el
# contacto a alguien del taller es darle todo eso. El taller no necesita permiso
# en el Sheet: escribe la cuenta de servicio del bot, no la persona.
def _ids(*nombres):
    salida = set()
    for nombre in nombres:
        for x in (os.getenv(nombre) or "").replace(";", ",").split(","):
            x = x.strip()
            if x.lstrip("-").isdigit():
                salida.add(int(x))
    return salida


ADMIN_IDS  = _ids("ADMIN_CHAT_IDS", "ADMIN_CHAT_ID")
TALLER_IDS = _ids("TALLER_CHAT_IDS", "PRODUCTION_GROUP_CHAT_ID")

# Lo único que el taller puede hacer. Todo lo demás —plata, clientes, anuncios—
# ni siquiera se le ofrece al modelo cuando escribe alguien del taller.
HERRAMIENTAS_TALLER = {
    "registrar_jornada", "leer_jornadas", "resumen_tiempos",
    "agregar_pendiente", "leer_pendientes", "cerrar_pendiente",
    "leer_produccion", "actualizar_etapa_produccion",
}


def rol_de(chat_id):
    """admin · taller · None (desconocido)."""
    if chat_id in ADMIN_IDS:
        return "admin"
    if chat_id in TALLER_IDS:
        return "taller"
    # Sin nada configurado el bot queda como estaba: abierto. Apenas exista un
    # ADMIN_CHAT_ID en el entorno, los desconocidos dejan de entrar.
    if not ADMIN_IDS and not TALLER_IDS:
        return "admin"
    return None
TG_API            = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

conversation_history: dict[int, list] = {}
ultima_foto: dict[int, bytes] = {}  # última foto recibida por chat, para usar como imagen de anuncio en Meta Ads

_MESES_ES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
             "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
_ultima_check_recordatorio = 0.0
_ultima_check_entregas     = 0.0
_ultima_check_semanal      = 0.0
_ultima_check_saldo        = 0.0
_ultima_check_cartera      = 0.0
_recordatorio_mes_enviado: set = set()  # in-memory: evita repetir en el mismo deployment

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
        "name": "crear_pestana",
        "description": (
            "Crea una pestaña nueva en el Sheet de operación (Ventas y Costos B&C). "
            "Úsala cuando una escritura falle porque la pestaña no existe. NUNCA le "
            "pidas al usuario que la cree a mano: puedes hacerlo tú, y pedírselo lo "
            "manda a crearla en el archivo equivocado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Nombre exacto de la pestaña"}
            },
            "required": ["titulo"]
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
        "description": "Genera la cotización en PDF y la envía por email. Si hay correo del cliente, va a él con copia a Camilo y Daniela; si no, va solo a Camilo y Daniela. SOLO llamar después de que el usuario confirme explícitamente el envío. Siempre muestra resumen y espera 'sí, confirmo' antes de llamar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_nombre":   {"type": "string"},
                "cliente_empresa":  {"type": "string"},
                "cliente_email":    {"type": "string", "description": "Email del cliente — OPCIONAL. Si se omite, la cotización se envía solo a Camilo y Daniela."},
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
                "fecha":            {"type": "string", "description": "Fecha formato DD/MM/AAAA"},
                "deal_id":          {"type": "string", "description": "ID del negocio de HubSpot al que pertenece esta cotización — opcional. Si se omite, se usa el negocio abierto del contacto o se crea uno nuevo."}
            },
            "required": ["cliente_nombre", "productos"]
        }
    },
    {
        "name": "enviar_cotizacion_pottery",
        "description": "Genera la cotización Pottery Lab (talleres/experiencias) en PDF y la envía por email. Si hay correo del cliente, va a él con copia a Camilo y Daniela; si no, va solo a Camilo y Daniela. SOLO llamar después de confirmación explícita del usuario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_nombre":   {"type": "string"},
                "cliente_empresa":  {"type": "string"},
                "cliente_email":    {"type": "string", "description": "Email del cliente — OPCIONAL. Si se omite, la cotización se envía solo a Camilo y Daniela."},
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
                "fecha":            {"type": "string", "description": "Fecha de emisión DD/MM/AAAA"},
                "deal_id":          {"type": "string", "description": "ID del negocio de HubSpot al que pertenece esta cotización — opcional. Si se omite, se usa el negocio abierto del contacto o se crea uno nuevo."}
            },
            "required": ["cliente_nombre", "taller_tipo", "taller_participantes", "taller_precio_por_persona"]
        }
    },

    # ── Cotizador ────────────────────────────────────────────────────────────────
    {
        "name": "calcular_precio",
        "description": "Calcula el precio sugerido de una pieza de cerámica según los costos reales del taller (materiales, mano de obra por minutos, quemas, fijos, margen e IVA). Devuelve el desglose completo. Úsalo ANTES de enviar_cotizacion cuando el usuario pregunte cuánto cobrar o pida cotizar algo sin dar precio. NO envía nada: solo calcula.",
        "input_schema": {
            "type": "object",
            "properties": {
                "producto":  {"type": "string", "description": "Nombre de la pieza. Ej: 'Taza cónica 250ml'"},
                "cantidad":  {"type": "integer", "description": "Número de piezas del pedido"},
                "tamano":    {"type": "string", "description": "XS | S | M | L | XL. Por gramaje: XS/S ~0.65kg, M ~1.2kg, L ~2kg, XL 4kg+. Si el usuario no lo dice, deduce por el tipo de pieza (taza/pocillo=S o M, plato 27cm=M, jarra=L, matera grande=XL) y dile qué asumiste."},
                "dificultad": {"type": "string", "description": "facil | medio | dificil (del acabado). Si el usuario describe la decoración, NO lo uses: pasa pct_pintado y num_tintas y se clasifica solo."},
                "pct_pintado": {"type": "number", "description": "% de la superficie que va pintada (0-100). Con num_tintas determina la dificultad."},
                "num_tintas": {"type": "integer", "description": "Número de colores/tintas de la decoración"},
                "solo_relieve": {"type": "boolean", "description": "true si la pintura va únicamente sobre el relieve (baja un grado de dificultad)"},
                "minutos_acabado": {"type": "number", "description": "Minutos de acabado a mano. Solo si no hay estándar medido para ese tamaño/dificultad."},
                "costo_bizcocho": {"type": "number", "description": "Costo del bizcocho de ESTA pieza, si es distinto al normal (un plato grande cuesta más que un pocillo)"},
                "oz_esmalte_por_pieza": {"type": "number", "description": "Onzas de esmalte de ESTA pieza, si son distintas a las normales"},
                "costo_vinilo": {"type": "number", "description": "Vinilo o transfer de ESTA pieza"},
                "minutos_extra": {"type": "number", "description": "Minutos adicionales por trabajo que el estándar no cubre"},
                "descuento_pct": {"type": "number", "description": "Descuento sobre esta referencia, en %"},
                "cliente": {"type": "string", "description": "Nombre del cliente, para el encabezado"},
                "lineas": {
                    "type": "array",
                    "description": "VARIAS referencias en una misma cotización (hasta 20). Úsalo cuando el pedido tenga más de un producto: '40 tazas, 20 platos y 6 materas'. Si lo usas, no llenes los campos de una sola pieza.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "producto":   {"type": "string"},
                            "cantidad":   {"type": "integer"},
                            "tamano":     {"type": "string", "description": "XS | S | M | L | XL"},
                            "dificultad": {"type": "string", "description": "facil | medio | dificil. Mejor pasa pct_pintado y num_tintas."},
                            "pct_pintado": {"type": "number"},
                            "num_tintas":  {"type": "integer"},
                            "solo_relieve": {"type": "boolean"},
                            "modelado": {"type": "boolean", "description": "true si la pieza se modela en el taller en vez de comprarse en bizcocho: suma el tiempo de modelado"},
                            "minutos_acabado": {"type": "number"},
                            "costo_bizcocho": {"type": "number"},
                            "oz_esmalte_por_pieza": {"type": "number"},
                            "costo_vinilo": {"type": "number"},
                            "minutos_extra": {"type": "number"},
                            "descuento_pct": {"type": "number"},
                            "notas": {"type": "string", "description": "Detalle de esa referencia, sale en la cotización"}
                        },
                        "required": ["cantidad", "tamano"]
                    }
                },
                "condiciones": {
                    "type": "object",
                    "description": "Lo que aplica a TODO el pedido, no a una referencia.",
                    "properties": {
                        "empaque":       {"type": "number", "description": "Lo que cuesta empacar TODO el pedido, en pesos. Se reparte entre las piezas, así que entra al costo de cada una."},
                        "descuento_pct": {"type": "number", "description": "Descuento comercial sobre el pedido"},
                        "urgencia_pct":  {"type": "number", "description": "Recargo por entrega más rápida de lo normal"},
                        "envio":         {"type": "number", "description": "Flete en pesos"},
                        "desarrollo":    {"type": "number", "description": "Molde, prueba o diseño: se cobra una sola vez"},
                        "cobrar_iva":    {"type": "boolean"},
                        "anticipo_pct":  {"type": "number"},
                        "validez_dias":  {"type": "integer"},
                        "plazo":         {"type": "string", "description": "Ej: '4-6 semanas hábiles'"}
                    }
                }
            },
            "required": []
        }
    },

    {
        "name": "guardar_hoja_cotizacion",
        "description": "Deja en el Cotizador Interno una pestaña con el desglose completo del último precio calculado, para que Camilo pueda revisar de dónde salió. Llámalo cuando el usuario acepte un precio, pida guardar el detalle, o justo antes de enviar la cotización al cliente. NO lo llames en cada tanteo de precio: solo cuando el precio ya es el bueno.",
        "input_schema": {
            "type": "object",
            "properties": {
                "producto":  {"type": "string"},
                "cantidad":  {"type": "integer"},
                "tamano":    {"type": "string", "description": "XS | S | M | L | XL"},
                "dificultad": {"type": "string", "description": "facil | medio | dificil"},
                "minutos_acabado": {"type": "number"},
                "numero":    {"type": "string", "description": "Número de cotización si ya existe (ej. BYC-604084)"},
                "cliente":   {"type": "string"},
                "lineas":    {"type": "array", "description": "Las mismas líneas que pasaste a calcular_precio, si el pedido tiene varias referencias.",
                              "items": {"type": "object"}},
                "condiciones": {"type": "object", "description": "Las mismas condiciones que pasaste a calcular_precio."}
            },
            "required": []
        }
    },
    {
        "name": "registrar_cotizacion",
        "description": (
            "Deja una cotización registrada en los TRES sitios: la pestaña Cotizaciones "
            "de Ventas y Costos B&C, HubSpot (contacto, negocio y ticket) y —si pasas "
            "`lineas`— el desglose en el Cotizador Interno. Llámalo SIEMPRE que se arme "
            "o se pegue una cotización, aunque no se envíe todavía por correo. Un fallo "
            "en uno no impide los otros dos, así que úsalo aunque sepas que el Cotizador "
            "Interno está bloqueado por permisos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "numero":           {"type": "string", "description": "Ej. BYC-260917-59"},
                "cliente_nombre":   {"type": "string"},
                "cliente_empresa":  {"type": "string"},
                "cliente_email":    {"type": "string"},
                "cliente_telefono": {"type": "string"},
                "tipo":             {"type": "string", "description": "producto | pottery"},
                "piezas":           {"type": "integer"},
                "total":            {"type": "integer", "description": "Total con IVA, en pesos, sin puntos"},
                "detalle":          {"type": "string", "description": "El resumen en texto, para la nota de HubSpot"},
                "fecha":            {"type": "string", "description": "DD/MM/YYYY. Vacío = hoy"},
                "notas":            {"type": "string"},
                "deal_id":          {"type": "string"},
                "lineas":           {"type": "array", "items": {"type": "object"},
                                     "description": "Las referencias, si quieres además el desglose en el Cotizador Interno"},
                "condiciones":      {"type": "object"}
            },
            "required": ["numero", "total"]
        }
    },
    {
        "name": "leer_cotizaciones",
        "description": "Las cotizaciones registradas, con su estado. Para '¿qué cotizaciones van?', '¿qué le cotizamos a X?'.",
        "input_schema": {
            "type": "object",
            "properties": {"cliente": {"type": "string", "description": "Opcional: filtrar"}}
        }
    },
    {
        "name": "marcar_cotizacion",
        "description": "Cambia el estado de una cotización: aceptada, perdida o vencida. Así se sabe cuántas se cierran.",
        "input_schema": {
            "type": "object",
            "properties": {
                "numero": {"type": "string"},
                "estado": {"type": "string", "description": "aceptada | perdida | vencida | enviada"}
            },
            "required": ["numero", "estado"]
        }
    },
    {
        "name": "crear_proyecto",
        "description": (
            "Da de alta un proyecto para poder llevarle su propio PNL. Cada proyecto "
            "pertenece a UNA línea de negocio: 'personalizacion' (pedidos a la medida), "
            "'b2b' (volumen para otro negocio que revende) o 'coleccion' (la colección "
            "propia, tienda y online). Llámalo cuando empiece un pedido o una colección "
            "nueva, o cuando alguien registre plata de algo que todavía no existe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proyecto":   {"type": "string", "description": "Nombre corto y reconocible"},
                "linea":      {"type": "string", "description": "personalizacion | b2b | coleccion"},
                "cliente":    {"type": "string"},
                "cotizacion": {"type": "string", "description": "Total cotizado en pesos, si lo hay"},
                "notas":      {"type": "string"}
            },
            "required": ["proyecto", "linea"]
        }
    },
    {
        "name": "reconstruir_proyectos",
        "description": (
            "Pasa la pestaña Proyectos al formato nuevo (Proyecto · Línea · Cliente · "
            "Estado · Inicio · Cierre · Cotización · Notas). Aparta la vieja como "
            "'Proyectos (v1)' SIN borrar nada. Úsalo solo si crear_proyecto avisa que "
            "la pestaña es la vieja, y confirma con Camilo antes."
        ),
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "pnl_proyecto",
        "description": (
            "El mini PNL de un proyecto: ingresos, costos agrupados (materia prima, mano "
            "de obra, producción indirecta, comercial), margen bruto y contribución, más "
            "el contraste con lo cotizado. Para '¿cuánto me dejó X?', '¿estoy ganando "
            "con X?', '¿cómo va el proyecto de X?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"proyecto": {"type": "string"}},
            "required": ["proyecto"]
        }
    },
    {
        "name": "pnl_lineas",
        "description": (
            "Compara las tres líneas de negocio —Personalización, B2B y Colección "
            "propia— con la contribución de cada una y de cada proyecto dentro. Para "
            "'¿qué línea deja más?', '¿cómo vamos por línea?', '¿dónde estoy perdiendo?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"linea": {"type": "string", "description": "Opcional: una sola línea"}}
        }
    },
    {
        "name": "registrar_movimiento",
        "description": (
            "Registra un ingreso o un egreso en la pestaña Movimientos, atribuido a un "
            "PROYECTO. Es una sola fila que sirve para dos cosas: el PNL del mes (por "
            "categoría) y el PNL del proyecto. Pregunta SIEMPRE a qué proyecto pertenece: "
            "sin eso el movimiento no entra a ningún PNL de proyecto. Los gastos generales "
            "del mes (arriendo, servicios, nómina fija) van sin proyecto, y está bien."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo":        {"type": "string", "description": "ingreso | egreso"},
                "monto":       {"type": "number", "description": "En pesos, sin puntos ni $"},
                "concepto":    {"type": "string", "description": "Ej. 'Anticipo 50%', 'Bizcochos 10 tazas'"},
                "proyecto":    {"type": "string", "description": "A qué proyecto pertenece. PREGÚNTALO si no lo dicen: sin proyecto no entra a ningún PNL."},
                "categoria":   {"type": "string", "description": "Materia Prima · Mano de Obra · Gastos Operativos · Ecommerce · B2B · Personalización …"},
                "fecha":       {"type": "string", "description": "DD/MM/YYYY. Vacío = hoy"},
                "forma_pago":  {"type": "string", "description": "Bold · Efectivo · Transferencia · Shopify"},
                "cliente":     {"type": "string", "description": "Cliente o proveedor"}
            },
            "required": ["tipo", "monto", "concepto"]
        }
    },
    {
        "name": "leer_movimientos",
        "description": (
            "El detalle de movimientos de un proyecto, uno por uno. Para ver el margen "
            "usa pnl_proyecto, que es más útil."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proyecto": {"type": "string", "description": "Vacío = todos"}
            }
        }
    },
    {
        "name": "guardar_tiempo_estandar",
        "description": "Guarda cuántos minutos toma una etapa de producción para un tamaño y dificultad. Las etapas son las del Discovery: 'Modelado' (dar forma a la arcilla; solo si la pieza no se compra en bizcocho), 'Acabado' (decoración y esmalte) y 'Terminado, calidad y empaque' (revisión final, limpieza y empaque). Úsalo cuando el usuario diga cuánto se demora un paso.",
        "input_schema": {
            "type": "object",
            "properties": {
                "etapa":      {"type": "string"},
                "tamano":     {"type": "string", "description": "XS | S | M | L | XL"},
                "dificultad": {"type": "string", "description": "facil | medio | dificil"},
                "minutos":    {"type": "number"}
            },
            "required": ["etapa", "tamano", "dificultad", "minutos"]
        }
    },
    {
        "name": "guardar_parametro_cotizador",
        "description": "Guarda un costo o parámetro del cotizador en la hoja, para no volver a preguntarlo nunca. Úsalo apenas el usuario te diga un valor que falta (ej. 'el bizcocho me cuesta 8000' → guardar_parametro_cotizador('costo_bizcocho', 8000)). Parámetros: costo_bizcocho, costo_esmaltes, costo_vinilo, minutos_otros_pasos, volumen_referencia, margen_pct, salario_mensual, arriendo_mes, servicios_mes, pct_uso_local, pct_uso_servicios, gastos_admin_mes, desperdicio_pct, mercadeo_pct, iva_pct.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parametro": {"type": "string", "description": "Nombre exacto del parámetro"},
                "valor":     {"type": "number", "description": "Valor en pesos, minutos o porcentaje según el parámetro"}
            },
            "required": ["parametro", "valor"]
        }
    },

    # ── Competencia ──────────────────────────────────────────────────────────────
    {
        "name": "barrer_competencia",
        "description": "Consulta los precios públicos de la competencia (productos de cerámica y talleres) en Bogotá, Cali y Medellín, los guarda en la pestaña Competencia del Sheet y devuelve un resumen. TARDA entre 30 segundos y 2 minutos: avisa al usuario antes de llamarlo. Para consultar barridos anteriores sin volver a salir a internet, usa leer_sheet sobre la pestaña Competencia.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo":   {"type": "string", "description": "productos | talleres. Vacío = ambos."},
                "ciudad": {"type": "string", "description": "Bogotá | Medellín | Cali. Vacío = todas."}
            },
            "required": []
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
                "piezas":        {"type": "integer", "description": "Cuántas piezas son. IMPRESCINDIBLE: sin esto no se puede deducir el avance. Si no lo dicen, PREGÚNTALO."},
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
        "description": ("CORRIGE la etapa de un pedido a mano. Normalmente NO hace falta: "
                        "la etapa se deduce sola de las jornadas del taller, y un pedido "
                        "avanza cuando las piezas reportadas alcanzan su cantidad. Usa esto "
                        "solo cuando la etapa deducida esté mal o falten jornadas por anotar."),
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
        "name": "registrar_jornada",
        "description": (
            "Anota una jornada de trabajo del taller y calcula los MINUTOS POR PIEZA. "
            "Llámalo apenas alguien del equipo cuente qué hizo hoy: 'empecé a pintar a "
            "las 10:00 am, terminé a las 2:00 pm, hice 10 platos'. Es la forma en que se "
            "miden los tiempos reales que le faltan al cotizador: cada jornada es una "
            "medición y el promedio de varias es el estándar. Pasa la tarea en las "
            "palabras del taller (pintar, esmaltar, empacar, lijar) — el script la "
            "traduce a la etapa del Discovery. Si no te dicen el tamaño de las piezas, "
            "PREGÚNTALO: sin tamaño la medición no sirve para el estándar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "persona":      {"type": "string", "description": "Quién lo hizo"},
                "tarea":        {"type": "string", "description": "Qué hizo, como lo dijo: 'pintar platos', 'empacar', 'lijar bizcocho'"},
                "piezas":       {"type": "integer", "description": "Cuántas piezas alcanzó a hacer"},
                "hora_inicio":  {"type": "string", "description": "'10:00 am', '8:30', '2 pm'"},
                "hora_fin":     {"type": "string", "description": "'2:00 pm', '12:15'"},
                "minutos":      {"type": "number", "description": "Solo si dan la duración directa en vez de las horas"},
                "pedido":       {"type": "string", "description": "Cliente o pedido al que pertenece, si lo dicen"},
                "tamano":       {"type": "string", "description": "XS | S | M | L | XL"},
                "dificultad":   {"type": "string", "description": "facil | medio | dificil"},
                "fecha":        {"type": "string", "description": "DD/MM/YYYY. Vacío = hoy"},
                "notas":        {"type": "string"},
                "etapa_pedido": {"type": "string", "description": "Solo si además terminaron una etapa del pedido y hay que moverlo en Producción"}
            },
            "required": ["persona", "tarea", "piezas"]
        }
    },
    {
        "name": "agregar_pendiente",
        "description": (
            "Anota algo que hay que hacer y todavía no se hizo: comprar un material, "
            "llamar a un proveedor, revisar una pieza. Llámalo cuando digan 'hay que...', "
            "'recuérdame...', 'falta...'. Si es de un pedido en particular, pásalo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pendiente": {"type": "string", "description": "Qué hay que hacer"},
                "pedido":    {"type": "string", "description": "Cliente o pedido, si aplica"},
                "quien":     {"type": "string", "description": "A quién le toca, si lo dicen"}
            },
            "required": ["pendiente"]
        }
    },
    {
        "name": "leer_pendientes",
        "description": "Lista los pendientes abiertos. Para '¿qué falta?', '¿qué tengo pendiente?', '¿qué falta del pedido de X?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido": {"type": "string", "description": "Opcional: filtrar por cliente o pedido"}
            }
        }
    },
    {
        "name": "cerrar_pendiente",
        "description": "Marca un pendiente como hecho. Acepta el número (#3) o un pedazo del texto ('el esmalte').",
        "input_schema": {
            "type": "object",
            "properties": {
                "referencia": {"type": "string", "description": "Número del pendiente o parte de su texto"}
            },
            "required": ["referencia"]
        }
    },
    {
        "name": "leer_jornadas",
        "description": (
            "Muestra qué hizo el equipo en el taller los últimos días: quién, qué tarea, "
            "cuántas piezas y en cuánto tiempo. Úsalo para '¿cómo va el seguimiento?', "
            "'¿qué se hizo hoy/esta semana?', '¿en qué anda el pedido de X?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias":   {"type": "integer", "description": "Cuántos días hacia atrás. Por defecto 7"},
                "pedido": {"type": "string", "description": "Opcional: filtrar por cliente o pedido"}
            }
        }
    },
    {
        "name": "resumen_tiempos",
        "description": (
            "Muestra los minutos por pieza ya medidos en planta, agrupados por etapa, "
            "tamaño y dificultad, y dice cuáles tienen jornadas suficientes para "
            "cargarse como estándar. Úsalo cuando pregunten cómo van los tiempos, "
            "cuánto nos demoramos en algo, o antes de proponer un estándar nuevo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "etapa": {"type": "string", "description": "Opcional: 'Modelado', 'Acabado' o 'Terminado, calidad y empaque'"}
            }
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
    },
    {
        "name": "registrar_saldo_inicial",
        "description": "Registra el saldo inicial del mes (banco y/o efectivo) en el Sheet. Llamar cuando el usuario diga cuánto hay en banco o efectivo al inicio del mes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "banco":    {"type": "integer", "description": "Saldo en cuenta bancaria en COP"},
                "efectivo": {"type": "integer", "description": "Efectivo en caja en COP"},
                "mes":      {"type": "string",  "description": "Mes formato 'Junio 2026'. Default: mes actual."}
            }
        }
    },

    # ── Cartera ──────────────────────────────────────────────────────────────────
    {
        "name": "leer_cartera",
        "description": "Muestra resumen de cartera: por cobrar (clientes que nos deben) y por pagar (lo que debemos a proveedores).",
        "input_schema": {
            "type": "object",
            "properties": {
                "filtro": {"type": "string", "description": "COBRAR, PAGAR, o vacío para todo"}
            }
        }
    },
    {
        "name": "agregar_cartera",
        "description": "Agrega una entrada nueva a la cartera. Usar para registrar deudas de clientes o pagos pendientes a proveedores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seccion":     {"type": "string", "description": "COBRAR (cliente nos debe) o PAGAR (le debemos a alguien)"},
                "tipo":        {"type": "string", "description": "B2B, Experiencia, Amphoritas, Proveedor, etc."},
                "cliente":     {"type": "string", "description": "Nombre del cliente o proveedor"},
                "concepto":    {"type": "string", "description": "Descripción breve"},
                "monto_total": {"type": "number", "description": "Monto total en COP"},
                "pagado":      {"type": "number", "description": "Cuánto ya pagaron (default 0)"},
                "fecha_vence": {"type": "string", "description": "Fecha límite dd/mm/yyyy"},
                "notas":       {"type": "string", "description": "Notas adicionales"}
            },
            "required": ["seccion", "cliente", "concepto", "monto_total", "fecha_vence"]
        }
    },
    {
        "name": "registrar_cobro_cartera",
        "description": "Registra un pago recibido de un cliente o un pago hecho a proveedor en la cartera.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente": {"type": "string", "description": "Nombre del cliente o proveedor"},
                "monto":   {"type": "number", "description": "Monto pagado en COP"}
            },
            "required": ["cliente", "monto"]
        }
    },

    # ── Meta Ads ─────────────────────────────────────────────────────────────────
    {
        "name": "meta_ads_campanas",
        "description": "Lista las campañas de Meta Ads de Bosque y Cielo con id, estado y presupuesto. Úsalo primero para saber qué campañas existen antes de pedir insights o hacer cualquier acción.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "meta_ads_insights",
        "description": "Métricas de rendimiento de Meta Ads (gasto, alcance, ROAS, CPA) a nivel de cuenta, campaña, ad set o ad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nivel": {"type": "string", "enum": ["account", "campaign", "adset", "ad"]},
                "object_id": {"type": "string", "description": "ID de la cuenta ('act_379796923470762'), campaña, ad set o ad"},
                "date_preset": {"type": "string", "enum": ["today", "yesterday", "last_7d", "last_30d", "this_month", "last_month"], "description": "Default last_7d"}
            },
            "required": ["nivel", "object_id"]
        }
    },
    {
        "name": "meta_ads_pausar_campana",
        "description": "Pausa una campaña de Meta Ads. SIEMPRE confirma con el usuario antes de llamarla, mostrando el nombre de la campaña.",
        "input_schema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"]
        }
    },
    {
        "name": "meta_ads_reanudar_campana",
        "description": "Reanuda una campaña de Meta Ads pausada. SIEMPRE confirma con el usuario antes de llamarla, mostrando el nombre de la campaña.",
        "input_schema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"]
        }
    },
    {
        "name": "meta_ads_actualizar_presupuesto",
        "description": "Cambia el presupuesto diario de una campaña de Meta Ads. SIEMPRE confirma con el usuario antes de llamarla, mostrando presupuesto actual y nuevo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "presupuesto_diario": {"type": "number", "description": "Nuevo presupuesto diario en COP, sin centavos"}
            },
            "required": ["campaign_id", "presupuesto_diario"]
        }
    },
    {
        "name": "meta_ads_crear_campana",
        "description": "Crea una campaña de Meta Ads completa (campaña + ad set + creativo + anuncio) desde cero, SIEMPRE en estado PAUSA — nunca se activa ni gasta automáticamente. SIEMPRE confirma con el usuario antes de llamarla, mostrando nombre, objetivo, presupuesto diario, texto/imagen y destino. Después de crearla, recuérdale al usuario que debe activarla manualmente (o pedir meta_ads_reanudar_campana) cuando esté conforme.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la campaña"},
                "objetivo": {"type": "string", "enum": ["trafico", "ventas", "interaccion", "reconocimiento"]},
                "presupuesto_diario": {"type": "number", "description": "Presupuesto diario en COP, sin centavos"},
                "imagen_url": {"type": "string", "description": "URL pública de la imagen del anuncio (ej. foto de producto de Shopify). No uses esto si el usuario ya envió la foto por Telegram — en ese caso usa usar_foto_enviada."},
                "usar_foto_enviada": {"type": "boolean", "description": "True si el usuario mandó la foto directamente como imagen adjunta en el chat de Telegram (en vez de un link). Usa la última foto que envió."},
                "texto_principal": {"type": "string", "description": "Texto principal del anuncio (primary text)"},
                "titular": {"type": "string", "description": "Titular / headline del anuncio"},
                "link_destino": {"type": "string", "description": "URL a la que lleva el anuncio (ej. producto en bosqueycielo.com)"},
                "descripcion": {"type": "string", "description": "Descripción corta opcional bajo el titular"},
                "cta": {"type": "string", "description": "Texto del botón, ej. SHOP_NOW, LEARN_MORE. Default SHOP_NOW"}
            },
            "required": ["nombre", "objetivo", "presupuesto_diario", "texto_principal", "titular", "link_destino"]
        }
    }
]

SYSTEM_TALLER = """Eres el asistente del taller de Bosque y Cielo (cerámica, Cali). Solo español.

Hablas con las dos personas que producen. NO eres su jefe ni les pides cuentas: les
ahorras trabajo. Sé breve y cálido; mensajes de dos o tres líneas, sin listas largas.

LO ÚNICO QUE HACES
1. Anotar la jornada del día — lo que hicieron y en cuánto tiempo.
2. Anotar y cerrar pendientes.
3. Decir en qué van los pedidos.

Si te preguntan por plata, precios, clientes, cotizaciones o cualquier otra cosa, di con
naturalidad que de eso no sabes y que le pregunten a Camilo. No inventes ni especules.

LA JORNADA
"empecé a pintar a las 10:00 am, terminé a las 2:00 pm, hice 10 platos"
→ registrar_jornada(persona, tarea, piezas, hora_inicio, hora_fin, pedido, tamano)

De esos partes salen los minutos por pieza reales del taller, así que valen oro. Para que
sirvan necesitas cuatro cosas, y las pides DE A UNA, nunca todas juntas:
- QUIÉN: si no firma, pregunta quién es. Recuerda el nombre durante la conversación.
- TAMAÑO de las piezas (XS a XL): es lo que más se olvida y sin eso la medición no sirve.
- PEDIDO o cliente: como MEZCLAN LOTES, una jornada puede tener piezas de varios pedidos.
  Si mencionan más de uno, registra UNA JORNADA POR PEDIDO repartiendo las piezas y el
  tiempo en proporción, y diles cómo lo repartiste.
- DIFICULTAD (facil/medio/dificil): solo si es trabajo de pintura y no es obvio.

Si no saben algo o dicen "después", anota lo que haya y sigue. Nunca insistas dos veces.

Cuando termines de anotar, confirma en una línea lo que entendiste y los minutos por
pieza que dio. Si alguien reporta algo muy distinto a lo normal, dilo sin regañar:
"ojo, eso da 80 min por pieza y normalmente van 24 — ¿pasó algo?".

PENDIENTES
"hay que comprar esmalte transparente" → agregar_pendiente
"¿qué falta?" → leer_pendientes · "ya lo compré" → cerrar_pendiente

PEDIDOS
"¿en qué vamos?" / "¿qué hay que entregar?" → leer_produccion
Si terminaron una etapa completa de un pedido → actualizar_etapa_produccion.
"""


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

DOS ARCHIVOS DE SHEETS, y confundirlos es el error más fácil del proyecto:
· *Ventas y Costos B&C* — la operación. Producción, Jornadas, Pendientes, Cartera,
  Competencia, flujo de caja. Es donde escriben leer_sheet/agregar_fila/crear_pestana
  y TODAS las herramientas de producción.
· *Cotizador Interno* — el modelo de costos. Parámetros Cotizador, Tiempos Estándar y
  las hojas de cada cotización. Solo lo tocan guardar_parametro_cotizador,
  guardar_tiempo_estandar y guardar_hoja_cotizacion.

Si una escritura falla porque falta una pestaña, **créala tú** con crear_pestana. Nunca
le pidas a Camilo que la cree a mano: termina creándola en el archivo equivocado y el
bot sigue sin encontrarla.
Si una escritura falla por permisos (403), es que *Cotizador Interno* no está compartido
con la cuenta de servicio del bot. Dile el correo exacto que trae el error y sigue: el
cálculo se puede correr igual pasando los valores a mano, solo que no quedan guardados.

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
1. Recopila los datos. El email del cliente es OPCIONAL: NUNCA lo pidas ni bloquees el envío por él.
   - Con email → la cotización va al cliente, con copia a Daniela y Camilo.
   - Sin email → va solo a Daniela y Camilo (asunto "[Interna]"), para revisarla o reenviarla a mano.
   Si el usuario da el correo, úsalo. Si no lo menciona, envía sin él.
2. Muestra resumen antes de enviar:
   "📋 Cotización [Empresa]:
   [Detalle del pedido o taller]
   Total: $[total] · Envío a: [email del cliente | Daniela y Camilo]
   ¿Confirmo envío?"
3. SOLO si el usuario dice "sí" → llamar el tool correspondiente.
4. Confirmar con: ✅ + número generado + a quién llegó + qué quedó en HubSpot.

REGISTRO AUTOMÁTICO EN HUBSPOT (no requiere tool aparte):
Toda cotización enviada se sube sola a HubSpot: crea o reutiliza el contacto, deja el
negocio en etapa "cotizacion" con el valor total, y agrega una nota con el detalle y
el PDF adjunto. El tool devuelve una línea "📊 HubSpot: ..." — muéstrasela al usuario.
- Si ya sabes el ID del negocio (porque lo buscaste o el usuario lo dio), pásalo en deal_id
  para que la cotización se cuelgue de ese negocio en vez de crear uno nuevo.
- Sin deal_id se usa el negocio abierto más reciente del contacto; si no tiene ninguno, se crea.

REGLAS:
- NUNCA enviar sin confirmación explícita.
- Condiciones default productos: "50% anticipo · 50% contra entrega".
- Condiciones default pottery: "50% anticipo para reservar · 50% el día del taller".
- Plazo default productos: "4-6 semanas hábiles".
- La cotización siempre llega a Daniela y Camilo (destinatarios directos si no hay correo del cliente, en copia si lo hay).
- Siempre se adjunta el PDF de la cotización, además del cuerpo del correo.

────────────────────────────────────────
MÓDULO COTIZADOR — CUÁNTO COBRAR
────────────────────────────────────────
calcular_precio(...) → precio sugerido con desglose, según los costos reales del taller.
Ver Directivas/cotizador.md

CUÁNDO USARLO: siempre que pregunten "cuánto cobro por...", o pidan cotizar algo SIN
dar el precio. Primero calcular_precio, después enviar_cotizacion con ese valor.

CÓMO PASAR LA DECORACIÓN: no clasifiques tú la dificultad. Si el usuario describe la
decoración ("pintada a la mitad, 2 colores"), pasa pct_pintado=50 y num_tintas=2 y el
script aplica la regla del Discovery. Solo usa "dificultad" si el usuario dice
textualmente fácil, medio o difícil.

PEDIDOS CON VARIAS REFERENCIAS: cuando el pedido tenga más de un producto ("40 tazas,
20 platos y 6 materas"), pasa la lista en `lineas` y NO llames calcular_precio tres
veces: así los costos fijos se reparten bien, el descuento y el envío se aplican al
pedido completo y sale un solo total. En `condiciones` van descuento, recargo por
urgencia, envío, molde o desarrollo, anticipo, validez y plazo.

DATOS POR REFERENCIA: cada línea puede traer sus propios materiales y son los que mandan
(costo_bizcocho, oz_esmalte_por_pieza, costo_vinilo), además de
minutos_extra y descuento_pct. Un plato de 27 cm lleva más bizcocho y más esmalte que un
pocillo: si el usuario te lo dice, pásalo en esa línea en vez de cambiar el parámetro
general. El parámetro general es el valor típico; el de la línea es la excepción.

LA PÁGINA: Camilo y Daniela también cotizan desde https://claude.ai/artifact/7tLyDp5hwSXnQLY5rWbM5j
La página es SOLO el cotizador (productos y Pottery Lab) y sus ajustes. Producción vive
entera acá: pedidos, jornadas y pendientes. Si preguntan por el tablero de producción de
la página, di que se movió a Telegram para no tener dos listas distintas.
(la página de Bosque y Cielo). Usa la misma fórmula, así que los precios deben coincidir. Si alguien
pregunta por "la página" o "el cotizador visual", es esa.

PEGADO DESDE LA PÁGINA — POTTERY LAB: si el mensaje empieza con "COTIZACIÓN POTTERY LAB",
es una experiencia armada en la página. Las experiencias NO se costean (el precio por
persona lo pone Camilo): solo confirma los datos y mándala con enviar_cotizacion_pottery.
No la guardes en el Cotizador Interno — esa hoja es de productos.

PEGADO DESDE LA PÁGINA: si el mensaje empieza con "COTIZACIÓN BOSQUE Y CIELO", es una
cotización armada allá. La página guarda en su propia base, no en el Sheet ni en HubSpot:
registrarla es tu trabajo, y se hace con **registrar_cotizacion** — una sola llamada que
la deja en los tres sitios (pestaña Cotizaciones, HubSpot con negocio y ticket, y el
desglose en el Cotizador Interno si le pasas `lineas`).

Lee del texto: el número, el cliente y su contacto, el total, las piezas y las referencias
con sus datos (cantidad, tamaño, acabado, minutos_acabado y los costos de cada una).
Pásalas tal cual como `lineas` y `condiciones`. Después reporta las tres líneas que
devuelve, sin esconder las que fallen.

NUNCA digas que "quedó registrado acá" sin haber llamado a registrar_cotizacion: el chat
no es un registro. Si el Cotizador Interno falla por permisos, los otros dos igual
quedaron — dilo así y sigue.

Si el total que calculas no coincide con el que trae el texto, DILO con los dos valores en
vez de corregirlo callado: significa que la página y la hoja tienen parámetros distintos.

TAMAÑO: si no lo dicen, dedúcelo del tipo de pieza y AVISA qué asumiste
("asumí tamaño M, una taza estándar"). XS/S piezas pequeñas · M taza o plato de 27cm ·
L jarra o pieza de 2kg · XL matera grande de 4kg+.

EL EMPAQUE VA POR PEDIDO, NO POR PIEZA (Camilo, 2026-09-18): se cotiza una sola vez
("empacar todo eso me cuesta $75.000") y va en condiciones.empaque; el motor lo reparte
entre las piezas del pedido, así que entra al costo unitario y lleva margen. NUNCA lo
pidas por pieza ni lo guardes como parámetro del taller: depende del pedido.

COSTOS QUE FALTAN → PREGÚNTALOS, no te quedes con la advertencia:
Cuando el resultado avise "Sin costo cargado: bizcocho, esmaltes...", muestra el precio
y ACTO SEGUIDO pregunta por esos valores, uno por uno, en lenguaje llano:
   "Para que el precio quede completo me falta un dato: ¿cuánto te cuesta el bizcocho
    por pieza?"
Cuando el usuario responda → guardar_parametro_cotizador(parametro, valor) → vuelve a
llamar calcular_precio para mostrar el precio ya corregido. Si el guardado devuelve ❌,
DILO: significa que el dato no quedó guardado y el precio no va a cambiar.
Para el esmalte pregunta las ONZAS por pieza (oz_esmalte_por_pieza): es más fácil de
responder que un valor en pesos, y el galón de 128 oz a $260.000 da $2.031 la onza.

TIEMPOS POR ETAPA: el tiempo de una pieza se arma sumando tres etapas, cada una por
tamaño y dificultad (como las tablas del Discovery):
  · "Modelado" — dar forma a la arcilla. Solo cuenta cuando la pieza NO se compra en
    bizcocho: pásalo con modelado=true en esa línea. De 36 productos que miró el
    Discovery, uno solo llevaba modelado.
  · "Acabado" — decoración y esmalte (ESTA ya está medida)
  · "Terminado, calidad y empaque" — revisión final, ajustes, limpieza y empaque
La QUEMA no es un tiempo por pieza sino una hornada: vive en la capacidad del horno.
Cuando una etapa salga como "sin medir", pregunta por ella nombrando el tamaño
("¿cuántos minutos toma pulir y limpiar un bizcocho mediano?") y guarda la respuesta con
guardar_tiempo_estandar. Cada tamaño y dificultad se pregunta una sola vez. Pregunta de a un dato por
mensaje, no los cuatro de una. Si el usuario no sabe o dice "después", sigue sin
insistir: se pregunta de nuevo en la siguiente cotización.

DEJA CONSTANCIA: cuando el precio ya sea el definitivo (el usuario lo acepta, o vas a
enviar la cotización), llama guardar_hoja_cotizacion con los mismos datos. Eso deja en
el Cotizador Interno una pestaña con todo el desglose y los parámetros usados, para que
Camilo pueda entrar a revisar cómo se calculó. NO lo llames en cada tanteo.

REGLAS:
- El resultado trae ADVERTENCIAS (⚠️). Muéstralas SIEMPRE, sin excepción. Mientras haya
  advertencias el precio sale por DEBAJO del real: nunca lo presentes como definitivo.
- Las QUEMAS no se cobran aparte: su energía ya está dentro de los servicios públicos,
  que se reparten por pieza. Cargarlas como costo sería contarlas dos veces.
- Si no hay tiempo medido para ese tamaño y dificultad (L fácil, XL fácil, XL difícil),
  el script avisa: pídele al usuario los minutos y pásalos en minutos_acabado.
- El precio es SUGERIDO. La decisión de cobrar más o menos es de Camilo.
- Los fijos se reparten entre 150 piezas/mes, no entre el pedido. Si preguntan por qué
  un pedido chico no sale más caro, esa es la razón.

────────────────────────────────────────
MÓDULO COMPETENCIA
────────────────────────────────────────
barrer_competencia(tipo, ciudad) → lee los precios públicos de la competencia y los
guarda en la pestaña Competencia del Sheet, con la fecha. Ver Directivas/analisis_competencia.md

- TARDA 30s-2min. Avisa "voy a consultar, dame un momento" ANTES de llamarlo.
- "¿cómo están los precios de tazas en Bogotá?" → barrer_competencia(tipo="productos", ciudad="Bogotá")
- "revisa la competencia de talleres" → barrer_competencia(tipo="talleres")
- Para mirar barridos pasados SIN salir a internet → leer_sheet("Competencia!A:I")

REGLAS:
- Varios competidores NO publican precios (los dan por WhatsApp o Instagram). Cuando el
  resumen los liste como "No publican precios", dilo tal cual. NUNCA estimes un precio.
- Al comparar con los precios de Bosque y Cielo, usa rango y mediana, y recuerda que
  tamaño, técnica y acabado cambian el precio: no saques conclusiones de un solo número.
- En Cali todavía no hay competidores cargados: si preguntan por Cali, dilo y ofrece
  agregar los que Camilo o Daniela conozcan.

────────────────────────────────────────
MÓDULO PRODUCCIÓN — DOS PROCESOS
────────────────────────────────────────
PROCESO 1 (Clásico):  modelado → secado → primera quema → esmaltado → segunda quema → acabado → empaque → entregado
PROCESO 2 (Bizcocho): esmaltado inicial → pintar bizcocho → primera quema → acabado → empaque → entregado

FLUJO NUEVO PEDIDO:
- Deal pasa a "produccion" o Daniela confirma inicio → agregar_pedido_produccion
- PREGUNTA SIEMPRE CUÁNTAS PIEZAS SON. Sin ese número no se puede deducir el avance
  y el pedido se queda ciego.
- Etapa inicial automática: Proceso 1→modelado | Proceso 2→esmaltado inicial

LA ETAPA SE DEDUCE, NO SE DECLARA
Un pedido de 150 platos no "está en pintar": tiene 60 pintados y 90 sin pintar. La etapa
sale sola de las jornadas — cuando las piezas reportadas en una etapa alcanzan la cantidad
del pedido, el pedido pasa a la siguiente. Nadie tiene que actualizarla.
- La deducción SOLO AVANZA: una jornada vieja nunca echa para atrás una corrección.
- actualizar_etapa_produccion quedó solo para CORREGIR cuando la deducción esté mal.
- Si etapa="entregado" y hay deal_id → también actualizar_deal_hs(deal_id, etapa="entrega")

CONSULTAS:
"¿qué entrega esta semana?" | "¿en qué está [cliente]?" | "¿qué hay en producción?"
→ leer_produccion · muestra etapa, cuántas piezas van de cuántas, y cuántas horas de
taller faltan para cerrar la etapa en curso (al ritmo medido en las jornadas de ESE
pedido, a 12 horas de taller al día: dos personas por seis horas).
Si la proyección se pasa de la fecha de entrega, DILO sin que te pregunten.

REGLAS:
- NUNCA marcar entregado sin confirmación explícita.
- Daniela habla operativamente: mensajes cortos son comandos de producción.

JORNADAS DEL TALLER — el parte diario, y de paso la medición de tiempos
────────────────────────────────────────
Las dos personas que producen reportan por acá lo que hicieron en el día:
  "empecé a pintar a las 10:00 am, terminé de pintar a las 2:00 pm, hice 10 platos"
  "esmalté 20 tazas, de 8 a 12" · "empaqué el pedido de Camilo Rojas, 40 piezas, 35 minutos"
→ registrar_jornada(persona, tarea, piezas, hora_inicio, hora_fin, ...)

Esto NO es solo seguimiento: cada jornada mide MINUTOS POR PIEZA, que es el dato que
al cotizador le falta. 4 horas / 10 platos = 24 min por plato de acabado. Con tres o
cuatro jornadas de lo mismo ya hay un estándar creíble.

Qué hacer para que la medición sirva:
- La PERSONA: si no firma, pregunta quién es (o dedúcelo de quién escribe).
- El TAMAÑO (XS-XL): es lo que más se les olvida y sin él la jornada no entra al
  estándar. Pregúntalo siempre, corto: "¿de qué tamaño eran los platos?".
- La DIFICULTAD (facil/medio/dificil): pregúntala solo si es trabajo de Acabado y no
  es obvio; si no la dan, déjala vacía antes que inventarla.
- Si además cerraron una etapa del pedido, pasa etapa_pedido para moverlo en Producción.
- Una sola pregunta por mensaje. Si no saben o dicen "después", anota lo que haya y sigue.

PENDIENTES: "hay que comprar esmalte" | "recuérdame llamar al proveedor" | "falta..."
→ agregar_pendiente(pendiente, pedido, quien) · "¿qué falta?" → leer_pendientes()
· "ya compré el esmalte" / "listo el #3" → cerrar_pendiente(referencia)

"¿qué se hizo hoy?" | "¿cómo va el seguimiento?" | "¿en qué anda [cliente]?" → leer_jornadas()
"¿cómo vamos con los tiempos?" | "¿cuánto nos demoramos pintando?" → resumen_tiempos()
Cuando una etapa ya tenga 3 o más jornadas, propónselo a Camilo: "el acabado de un plato
M va en 23 min medidos en 5 jornadas, ¿lo cargo como estándar?" y con su sí llama
guardar_tiempo_estandar. Eso reemplaza el dato de respaldo y el precio deja de ser un
estimado.

────────────────────────────────────────
PROYECTOS Y SU PNL
────────────────────────────────────────
Todo lo que se produce pertenece a UN proyecto, y cada proyecto a UNA de tres líneas:
· *personalizacion* — pedidos a la medida para una persona o empresa
· *b2b* — volumen para otro negocio que revende
· *coleccion* — la colección propia, tienda y online

"empieza un pedido de 150 platos para el Café del Valle" → crear_proyecto(nombre, linea)
"pagué $140.000 de bizcochos del pedido del Café" → registrar_movimiento(...)
"¿cuánto me dejó el Café del Valle?" → pnl_proyecto(proyecto)
"¿qué línea deja más?" | "¿dónde estoy perdiendo?" → pnl_lineas()

UN SOLO REGISTRO. `registrar_movimiento` escribe una fila en Movimientos con la columna
Proyecto puesta, y esa misma fila alimenta el PNL del mes (por categoría) y el del
proyecto. No hay segundo libro ni hay que registrar dos veces.

PREGUNTA SIEMPRE EL PROYECTO. Sin él, el movimiento no aparece en ningún PNL de
proyecto. La excepción son los gastos generales del mes —arriendo, servicios, nómina
fija—, que no pertenecen a ninguno y está bien que vayan sin proyecto.

CÓMO SE LEE EL PNL:
  Ingresos − materia prima − mano de obra = *margen bruto*
  menos producción indirecta y comercial  = *contribución*
La contribución es lo que el proyecto deja para pagar los fijos del mes. NO está
descontado el arriendo, los servicios ni la gerencia: un proyecto con contribución
positiva todavía puede no alcanzar si el mes tiene pocos proyectos.

Si un proyecto sale con contribución NEGATIVA, dilo de frente y mira con qué costo se
fue: casi siempre es mano de obra subestimada o un flete que nadie cotizó.

────────────────────────────────────────
MÓDULO FLUJO DE CAJA
────────────────────────────────────────
"flujo de caja" | "¿cómo vamos?" | "proyectado vs real" | "presupuesto" → reporte_flujo_caja()
Muestra ingresos y egresos reales vs proyectados del mes con % de avance por categoría.
El reporte llega automáticamente cada lunes.
Cuando el usuario diga cuánto hay en banco o efectivo → registrar_saldo_inicial(banco, efectivo)
El saldo final = saldo inicial + ingresos - egresos.

────────────────────────────────────────
MÓDULO CARTERA
────────────────────────────────────────
Tab "Cartera" — dos secciones: COBRAR (clientes que nos deben) · PAGAR (lo que debemos a proveedores)

"cartera" | "¿qué me deben?" | "cartera por cobrar" → leer_cartera(filtro="COBRAR")
"¿qué debo?" | "cuentas por pagar" → leer_cartera(filtro="PAGAR")
"ver toda la cartera" → leer_cartera()
"me pagó [cliente] $X" | "pagué a [proveedor] $X" → registrar_cobro_cartera(cliente, monto)
"[cliente] debe $X por [concepto] hasta [fecha]" → agregar_cartera(seccion="COBRAR", ...)
"le debo a [proveedor] $X hasta [fecha]" → agregar_cartera(seccion="PAGAR", ...)

FLUJO AGREGAR:
1. Extrae: quién · cuánto · concepto · fecha límite · si es COBRAR o PAGAR.
2. Si falta fecha → pregunta "¿Fecha límite de pago?"
3. Llama agregar_cartera y confirma: "✅ [Cliente] — $monto — vence [fecha]"

REGLAS:
- Siempre pedir fecha de vencimiento.
- Alertas automáticas cada 12h si hay items vencidos.

────────────────────────────────────────
MÓDULO META ADS
────────────────────────────────────────
Cuenta publicitaria: act_379796923470762 (Bosque y Cielo Homeware).

"campañas" | "cómo van los anuncios" → meta_ads_campanas() primero, para saber qué campañas existen y sus IDs.
Para métricas (ROAS, CPA, gasto, alcance) → meta_ads_insights(nivel, object_id, date_preset). Prioridad al analizar: ROAS > CPA > alcance/frecuencia > gasto vs. presupuesto.
Los campos actions/action_values vienen por action_type (ej. "purchase") — no sumes el array completo a ciegas.

CREAR CAMPAÑA ("crea una campaña", "hazme un anuncio de X"): usa meta_ads_crear_campana. Antes de llamarla, junta con el usuario: nombre, objetivo (trafico/ventas/interaccion/reconocimiento — si duda, "ventas" para vender producto), presupuesto diario, imagen, texto principal, titular, link de destino y opcionalmente descripción/cta. La imagen puede llegar de dos formas: (a) el usuario manda un link → usa imagen_url; (b) el usuario manda la foto directo al chat como adjunto → usa usar_foto_enviada=true (NO le pidas un link si ya te mandó la foto). La función SIEMPRE crea todo en PAUSA — nunca gasta sola. Después de crearla, dile al usuario que la revise en Ads Manager y que la active manualmente o te pida meta_ads_reanudar_campana.

REGLA ABSOLUTA: a diferencia del Sheet, en Meta Ads SIEMPRE confirma con el usuario antes de pausar/reanudar una campaña, cambiar un presupuesto, o crear una campaña nueva — sin excepción, mostrando el cambio exacto (nombre de campaña, estado o presupuesto actual → nuevo, o el detalle completo de la campaña nueva). Es gasto publicitario real en curso."""


def descargar_foto(file_id: str):
    try:
        path = requests.get(f"{TG_API}/getFile", params={"file_id": file_id}, timeout=10).json()["result"]["file_path"]
        return requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}", timeout=30).content
    except Exception as e:
        print(f"Error descargando foto: {e}")
        return None


def procesar_mensaje(chat_id: int, texto: str, foto_bytes=None, rol: str = "admin") -> str:
    history = conversation_history.get(chat_id, [])
    if rol == "taller":
        herramientas = [t for t in TOOLS if t["name"] in HERRAMIENTAS_TALLER]
        sistema = SYSTEM_TALLER
    else:
        herramientas = TOOLS
        sistema = SYSTEM_PROMPT

    if foto_bytes:
        img_b64 = base64.standard_b64encode(foto_bytes).decode()
        content = []
        if texto:
            content.append({"type": "text", "text": texto})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}})
        if not texto:
            content.append({"type": "text", "text": "Analiza esta imagen según el contexto de la conversación (puede ser un movimiento financiero para registrar, o una foto para un anuncio de Meta Ads si eso es lo que se estaba armando)."})
        history_user_text = f"[pantallazo] {texto}".strip()
    else:
        content = texto
        history_user_text = texto

    messages = history + [{"role": "user", "content": content}]
    iteraciones = 0
    last_tool_result = None

    while iteraciones < 6:
        iteraciones += 1

        for retry in range(4):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=512,
                    system=sistema + f"\n\nFECHA HOY: {date.today().strftime('%d/%m/%Y')}",
                    tools=herramientas,
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
                    elif name == "crear_pestana":
                        resultado = crear_pestana(inp["titulo"])
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
                        paquete   = preparar_cotizacion(datos, "productos")
                        resultado = enviar_cotizacion(datos, paquete)
                        if not resultado.startswith("Error"):
                            resultado += "\n" + registrar_cotizacion_hs(
                                datos, paquete, inp.get("deal_id", ""))
                            resultado += "\n" + _reg_cot_fila(
                                paquete["numero"], cliente=datos["cliente"]["nombre"],
                                empresa=datos["cliente"].get("empresa", ""),
                                contacto=datos["cliente"].get("email", "") or datos["cliente"].get("telefono", ""),
                                tipo="producto", total=int(paquete["total"]),
                                fecha=datos.get("fecha", ""), notas=datos.get("notas", ""))
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
                        paquete   = preparar_cotizacion(datos, "pottery")
                        resultado = enviar_cotizacion_pottery(datos, paquete)
                        if not resultado.startswith("Error"):
                            resultado += "\n" + registrar_cotizacion_hs(
                                datos, paquete, inp.get("deal_id", ""))
                            resultado += "\n" + _reg_cot_fila(
                                paquete["numero"], cliente=datos["cliente"]["nombre"],
                                empresa=datos["cliente"].get("empresa", ""),
                                contacto=datos["cliente"].get("email", "") or datos["cliente"].get("telefono", ""),
                                tipo="pottery",
                                piezas=int(inp.get("taller_participantes", 0) or 0),
                                total=int(paquete["total"]),
                                fecha=datos.get("fecha", ""), notas=datos.get("notas", ""))
                    # ── Cotizador ───────────────────────────────────────────
                    elif name == "calcular_precio":
                        try:
                            if inp.get("lineas"):
                                resultado = _cot_formato_pedido(_cotizar_pedido(
                                    inp["lineas"], inp.get("condiciones"),
                                    cliente=inp.get("cliente", "")))
                            elif not inp.get("cantidad") or not inp.get("tamano"):
                                resultado = ("Para cotizar necesito la cantidad y el tamaño "
                                             "(o la lista de referencias del pedido).")
                            else:
                                _dificultad = inp.get("dificultad", "")
                                if not _dificultad and inp.get("pct_pintado") is not None:
                                    _dificultad = _grado_acabado(
                                        inp.get("pct_pintado", 0), inp.get("num_tintas", 1),
                                        inp.get("solo_relieve", False))
                                resultado = _cot_formato(_cotizar(
                                    inp["cantidad"], inp["tamano"], _dificultad or "medio",
                                    inp.get("minutos_acabado"), producto=inp.get("producto", ""),
                                    ajustes={k: inp[k] for k in _COT_AJUSTES if k in inp}))
                        except ValueError as e:
                            resultado = f"No se pudo calcular: {e}"
                    elif name == "guardar_hoja_cotizacion":
                        try:
                            if inp.get("lineas"):
                                _r = _cotizar_pedido(inp["lineas"], inp.get("condiciones"),
                                                     cliente=inp.get("cliente", ""))
                                resultado = _cot_guardar_hoja_pedido(_r, inp.get("numero", ""))
                            elif not inp.get("cantidad") or not inp.get("tamano"):
                                resultado = "Para guardar la hoja necesito la cantidad y el tamaño."
                            else:
                                _r = _cotizar(inp["cantidad"], inp["tamano"],
                                              inp.get("dificultad", "medio"),
                                              inp.get("minutos_acabado"),
                                              producto=inp.get("producto", ""),
                                              ajustes={k: inp[k] for k in _COT_AJUSTES if k in inp})
                                resultado = _cot_guardar_hoja(_r, inp.get("numero", ""))
                        except ValueError as e:
                            resultado = f"No se pudo guardar la hoja: {e}"
                    elif name == "registrar_cotizacion":
                        resultado = _registrar_cotizacion(inp)
                    elif name == "leer_cotizaciones":
                        resultado = _reg_cot_leer(inp.get("cliente", ""))
                    elif name == "marcar_cotizacion":
                        resultado = _reg_cot_estado(inp["numero"], inp["estado"])
                    elif name == "crear_proyecto":
                        resultado = _proy_crear(
                            inp["proyecto"], inp["linea"], inp.get("cliente", ""),
                            inp.get("cotizacion", ""), notas=inp.get("notas", ""))
                    elif name == "reconstruir_proyectos":
                        resultado = _proy_reconstruir()
                    elif name == "pnl_proyecto":
                        resultado = _proy_pnl(inp["proyecto"])
                    elif name == "pnl_lineas":
                        resultado = _proy_lineas(inp.get("linea", ""))
                    elif name == "registrar_movimiento":
                        resultado = _mov_registrar(
                            inp["tipo"], inp["monto"], inp["concepto"],
                            inp.get("proyecto", ""), inp.get("categoria", ""),
                            inp.get("fecha", ""), inp.get("forma_pago", ""),
                            inp.get("cliente", ""))
                    elif name == "leer_movimientos":
                        resultado = _mov_leer(inp.get("proyecto", ""))
                    elif name == "guardar_tiempo_estandar":
                        resultado = _cot_guardar_tiempo(
                            inp["etapa"], inp["tamano"], inp["dificultad"], inp["minutos"])
                    elif name == "guardar_parametro_cotizador":
                        resultado = _cot_guardar_param(inp["parametro"], inp["valor"])
                    # ── Competencia ─────────────────────────────────────────
                    elif name == "barrer_competencia":
                        _filas = _comp_barrer(inp.get("tipo", ""), inp.get("ciudad", ""))
                        resultado = _comp_resumen(_filas)
                        if _filas:
                            resultado += "\n\n" + _comp_guardar(_filas)
                    # ── Producción ───────────────────────────────────────────
                    elif name == "agregar_pedido_produccion":
                        resultado = _prod_agregar(
                            inp["cliente"], inp["descripcion"],
                            inp.get("proceso", 1), inp["fecha_entrega"],
                            inp.get("deal_id", ""), inp.get("notas", ""),
                            inp.get("piezas", 0)
                        )
                    elif name == "registrar_jornada":
                        resultado = _jornada_registrar(inp)
                    elif name == "leer_jornadas":
                        resultado = _jor_bitacora(inp.get("dias", 7), inp.get("pedido", ""))
                    elif name == "resumen_tiempos":
                        resultado = _jor_resumen(inp.get("etapa", ""))
                    elif name == "actualizar_etapa_produccion":
                        resultado = _prod_actualizar(
                            inp["cliente"], inp["etapa"], inp.get("notas", "")
                        )
                    elif name == "leer_produccion":
                        resultado = _prod_leer()
                    elif name == "agregar_pendiente":
                        resultado = _pend_agregar(inp["pendiente"], inp.get("pedido", ""),
                                                  inp.get("quien", ""))
                    elif name == "leer_pendientes":
                        resultado = _pend_leer(inp.get("pedido", ""))
                    elif name == "cerrar_pendiente":
                        resultado = _pend_cerrar(inp["referencia"])
                    elif name == "reporte_flujo_caja":
                        resultado = _generar_reporte_flujo()
                    elif name == "registrar_saldo_inicial":
                        resultado = _registrar_saldo(
                            inp.get("banco"), inp.get("efectivo"),
                            inp.get("mes", "")
                        )
                    elif name == "leer_cartera":
                        resultado = _leer_cartera(inp.get("filtro", ""))
                    elif name == "agregar_cartera":
                        resultado = _cartera_agregar(
                            inp["seccion"], inp.get("tipo", ""), inp["cliente"],
                            inp["concepto"], inp["monto_total"],
                            inp.get("pagado", 0), inp.get("fecha_vence", ""),
                            inp.get("notas", "")
                        )
                    elif name == "registrar_cobro_cartera":
                        resultado = _cartera_registrar_cobro(inp["cliente"], inp["monto"])
                    # ── Meta Ads ─────────────────────────────────────────────
                    elif name == "meta_ads_campanas":
                        resultado = meta_listar_campanas()
                    elif name == "meta_ads_insights":
                        resultado = meta_obtener_insights(inp["nivel"], inp["object_id"], inp.get("date_preset", "last_7d"))
                    elif name == "meta_ads_pausar_campana":
                        resultado = meta_pausar_campana(inp["campaign_id"])
                    elif name == "meta_ads_reanudar_campana":
                        resultado = meta_reanudar_campana(inp["campaign_id"])
                    elif name == "meta_ads_actualizar_presupuesto":
                        resultado = meta_actualizar_presupuesto(inp["campaign_id"], inp["presupuesto_diario"])
                    elif name == "meta_ads_crear_campana":
                        foto = ultima_foto.get(chat_id) if inp.get("usar_foto_enviada") else None
                        resultado = meta_crear_campana_completa(
                            inp["nombre"], inp["objetivo"], inp["presupuesto_diario"], inp.get("imagen_url", ""),
                            inp["texto_principal"], inp["titular"], inp["link_destino"],
                            inp.get("descripcion", ""), inp.get("cta", "SHOP_NOW"), imagen_bytes=foto
                        )
                    else:
                        resultado = f"Herramienta desconocida: {name}"
                    last_tool_result = resultado
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": resultado})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            respuesta = next((b.text for b in response.content if hasattr(b, "text")), None) or last_tool_result or "Sin respuesta."
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

def _saldo_mes_col(mes_num, anio):
    from datetime import timedelta as _td
    presup = leer_sheet_numericos("Presupuesto 2026!A:I")
    if not presup:
        return None, None
    header = presup[0] if presup else []
    meses_short = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,
                   "jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12}
    for i, h in enumerate(header):
        if isinstance(h, (int, float)):
            try:
                d = date(1899, 12, 30) + _td(days=int(h))
                if d.month == mes_num and d.year == anio:
                    return presup, i
            except Exception:
                pass
        elif isinstance(h, str) and str(anio) in h:
            if meses_short.get(h[:3].lower()) == mes_num:
                return presup, i
    return presup, None


def _registrar_saldo(banco, efectivo, mes_str=""):
    hoy = datetime.now()
    if mes_str:
        partes = mes_str.split()
        mes_nombres = {m.lower(): i for i, m in enumerate(_MESES_ES) if i > 0}
        mes_num = mes_nombres.get(partes[0].lower(), hoy.month)
        anio = int(partes[1]) if len(partes) > 1 else hoy.year
    else:
        mes_num, anio = hoy.month, hoy.year

    presup, mes_col = _saldo_mes_col(mes_num, anio)
    if mes_col is None:
        return f"No encontré columna para {_MESES_ES[mes_num]} {anio}."

    col_letra = chr(ord('A') + mes_col)
    msgs = []
    for i, fila in enumerate(presup[1:], start=2):
        cat = str(fila[1]).strip() if len(fila) > 1 else ""
        if cat == "Saldo Banco" and banco is not None:
            actualizar_celda(f"Presupuesto 2026!{col_letra}{i}", str(banco))
            msgs.append(f"Saldo Banco: ${banco:,}")
        elif cat == "Efectivo en Caja" and efectivo is not None:
            actualizar_celda(f"Presupuesto 2026!{col_letra}{i}", str(efectivo))
            msgs.append(f"Efectivo en Caja: ${efectivo:,}")

    if msgs:
        actualizar_celda("Presupuesto 2026!K2", f"{_MESES_ES[mes_num]} {anio}")
        return "✅ " + " · ".join(msgs) + f" registrados para {_MESES_ES[mes_num]} {anio}."
    return "No encontré filas de saldo en el Sheet."


def _fmt_cop(n):
    return f"${n/1_000_000:.1f}M" if abs(n) >= 1_000_000 else f"${n:,.0f}"


def _leer_cartera(filtro=""):
    filas = leer_sheet_numericos("Cartera!A:J")
    if not filas or len(filas) <= 1:
        return "Cartera vacía."
    hoy = datetime.now().date()
    cobrar, pagar = [], []
    total_c = total_p = 0
    for fila in filas[1:]:
        if len(fila) < 5:
            continue
        seccion = str(fila[0]).strip().upper()
        tipo    = str(fila[1]).strip() if len(fila) > 1 else ""
        cliente = str(fila[2]).strip() if len(fila) > 2 else ""
        concepto = str(fila[3]).strip() if len(fila) > 3 else ""
        try: monto_total = float(fila[4] or 0)
        except: monto_total = 0
        try: pagado = float(fila[5] or 0)
        except: pagado = 0
        pendiente = monto_total - pagado
        fecha_str = str(fila[7]).strip() if len(fila) > 7 else ""
        estado = str(fila[8]).strip().lower() if len(fila) > 8 else ""
        if estado == "pagado" or pendiente <= 0:
            continue
        vencido = False
        if fecha_str:
            try:
                fv = datetime.strptime(fecha_str, "%d/%m/%Y").date()
                vencido = fv < hoy
                fecha_fmt = fv.strftime("%d/%m")
            except:
                fecha_fmt = fecha_str
        else:
            fecha_fmt = "sin fecha"
        ico = "🔴" if vencido else "⚠️"
        linea = f"  {ico} {cliente} — {concepto}: {_fmt_cop(pendiente)} (vence {fecha_fmt})"
        if seccion == "COBRAR":
            cobrar.append(linea); total_c += pendiente
        elif seccion == "PAGAR":
            pagar.append(linea); total_p += pendiente
    if filtro.upper() == "COBRAR": pagar, total_p = [], 0
    elif filtro.upper() == "PAGAR": cobrar, total_c = [], 0
    msg = "📋 *CARTERA*\n\n"
    msg += f"💰 *POR COBRAR* — {_fmt_cop(total_c)}\n" + ("\n".join(cobrar) if cobrar else "  (nada pendiente)") + "\n\n"
    msg += f"💸 *POR PAGAR* — {_fmt_cop(total_p)}\n" + ("\n".join(pagar) if pagar else "  (nada pendiente)")
    return msg


def _cartera_agregar(seccion, tipo, cliente, concepto, monto_total, pagado=0, fecha_vence="", notas=""):
    try: pagado = float(pagado or 0)
    except: pagado = 0
    pendiente = float(monto_total) - pagado
    estado = "Pagado" if pendiente <= 0 else ("Parcial" if pagado > 0 else "Pendiente")
    row = [seccion.upper(), tipo, cliente, concepto, monto_total, pagado, pendiente, fecha_vence, estado, notas]
    r = agregar_fila("Cartera!A:J", row)
    return f"✅ Cartera: {cliente} — {concepto} — {_fmt_cop(monto_total)} — vence {fecha_vence}"


def _cartera_registrar_cobro(cliente, monto):
    filas = leer_sheet_numericos("Cartera!A:J")
    for i, fila in enumerate(filas[1:], start=2):
        if len(fila) < 5: continue
        nombre = str(fila[2]).strip().lower()
        if cliente.lower() in nombre or nombre in cliente.lower():
            try: pagado_actual = float(fila[5] or 0)
            except: pagado_actual = 0
            try: monto_total = float(fila[4] or 0)
            except: monto_total = 0
            nuevo_pagado    = pagado_actual + float(monto)
            nuevo_pendiente = monto_total - nuevo_pagado
            nuevo_estado    = "Pagado" if nuevo_pendiente <= 0 else "Parcial"
            actualizar_celda(f"Cartera!F{i}", nuevo_pagado)
            actualizar_celda(f"Cartera!G{i}", nuevo_pendiente)
            actualizar_celda(f"Cartera!I{i}", nuevo_estado)
            return f"✅ {str(fila[2]).strip()}: +{_fmt_cop(monto)} registrado. Pendiente: {_fmt_cop(max(nuevo_pendiente, 0))}"
    return f"No encontré '{cliente}' en la cartera."


def verificar_cartera_vencida():
    global _ultima_check_cartera
    ahora = time.time()
    if ahora - _ultima_check_cartera < 43200:
        return
    _ultima_check_cartera = ahora
    if not ADMIN_CHAT_ID:
        return
    try:
        filas = leer_sheet_numericos("Cartera!A:J")
        hoy = datetime.now().date()
        vencidos = []
        for fila in filas[1:]:
            if len(fila) < 8: continue
            estado = str(fila[8]).strip().lower() if len(fila) > 8 else ""
            if estado == "pagado": continue
            try: pendiente = float(fila[6] or 0)
            except: pendiente = 0
            if pendiente <= 0: continue
            fecha_str = str(fila[7]).strip()
            if not fecha_str: continue
            try:
                fv = datetime.strptime(fecha_str, "%d/%m/%Y").date()
                if fv < hoy:
                    seccion = str(fila[0]).strip().upper()
                    ico = "🔴" if seccion == "COBRAR" else "💸"
                    vencidos.append(f"{ico} {str(fila[2]).strip()} — {str(fila[3]).strip()}: {_fmt_cop(pendiente)} (venció {fv.strftime('%d/%m')})")
            except:
                continue
        if vencidos:
            tg_send(int(ADMIN_CHAT_ID), "⚠️ *Cartera vencida:*\n" + "\n".join(vencidos))
    except Exception as e:
        print(f"[Cartera] Error: {e}")


def verificar_saldo_inicial():
    global _ultima_check_saldo
    ahora = time.time()
    if ahora - _ultima_check_saldo < 43200:  # máximo una vez cada 12h
        return
    hoy = datetime.now()
    if not ADMIN_CHAT_ID:
        return
    try:
        ultimo = leer_sheet("Presupuesto 2026!K2").strip()
        mes_actual = f"{_MESES_ES[hoy.month]} {hoy.year}"
        if ultimo.lower() == mes_actual.lower():
            _ultima_check_saldo = ahora
            return
        if hoy.day <= 5 or not ultimo:
            # Marcar K2 antes de enviar para no repetir si el loop vuelve a correr
            actualizar_celda("Presupuesto 2026!K2", mes_actual)
            _ultima_check_saldo = ahora
            tg_send(int(ADMIN_CHAT_ID),
                    f"💰 ¡Nuevo mes! Para arrancar el flujo de caja de *{mes_actual}*, "
                    f"dime:\n1. ¿Cuánto hay en el banco?\n2. ¿Cuánto hay en efectivo en caja?")
    except Exception as e:
        print(f"[Saldo inicial] Error: {e}")


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
    meses_full  = {m.lower(): i for i, m in enumerate(_MESES_ES) if i > 0}
    for i, h in enumerate(header):
        if isinstance(h, (int, float)):
            try:
                d = date(1899, 12, 30) + _td(days=int(h))
                if d.month == mes_num and d.year == anio:
                    mes_col = i; break
            except Exception:
                pass
        elif isinstance(h, str):
            h_low = h.strip().lower()
            # "Junio 2026" o "Jun 2026"
            if str(anio) in h_low:
                if meses_short.get(h_low[:3]) == mes_num or meses_full.get(h_low.split()[0]) == mes_num:
                    mes_col = i; break
            # "Junio" o "Jun" sin año
            elif meses_full.get(h_low) == mes_num or meses_short.get(h_low[:3]) == mes_num:
                mes_col = i; break

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
            proyectado[(tipo, cat)] = proyectado.get((tipo, cat), 0.0) + float(fila[mes_col] or 0)
        except (ValueError, TypeError):
            pass

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

    # Saldo inicial (banco + efectivo)
    saldo_banco = saldo_efectivo = 0
    for fila in presup[1:]:
        if len(fila) <= mes_col:
            continue
        cat = str(fila[1]).strip()
        try:
            v = float(fila[mes_col] or 0)
        except (ValueError, TypeError):
            v = 0
        if cat == "Saldo Banco":
            saldo_banco = v
        elif cat == "Efectivo en Caja":
            saldo_efectivo = v

    saldo_inicial = saldo_banco + saldo_efectivo
    saldo_final_r = saldo_inicial + total_ing_r - total_egr_r
    saldo_final_p = saldo_inicial + total_ing_p - total_egr_p

    semana = (hoy.day - 1) // 7 + 1
    msg  = f"📊 *Flujo de Caja — {_MESES_ES[mes_num]} {anio}* (semana {semana})\n\n"
    if saldo_inicial:
        msg += f"🏦 Banco: {fmt(saldo_banco)} · Caja: {fmt(saldo_efectivo)} → *Disponible: {fmt(saldo_inicial)}*\n\n"
    msg += f"💰 *INGRESOS* {fmt(total_ing_r)} / {fmt(total_ing_p)}\n"
    msg += "\n".join(lines_ing) + "\n\n"
    msg += f"💸 *EGRESOS* {fmt(total_egr_r)} / {fmt(total_egr_p)}\n"
    msg += "\n".join(lines_egr) + "\n\n"
    ico_neto = "✅" if flujo_r >= flujo_p * 0.9 else ("⚠️" if flujo_r >= 0 else "🔴")
    msg += f"{ico_neto} *Flujo neto: {fmt(flujo_r)}* (proy: {fmt(flujo_p)})\n"
    if saldo_inicial:
        ico_sf = "✅" if saldo_final_r >= 0 else "🔴"
        msg += f"{ico_sf} *Saldo final estimado: {fmt(saldo_final_r)}* (proy: {fmt(saldo_final_p)})"
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


def _jornada_registrar(inp):
    """Anota la jornada y, si además cerraron una etapa, mueve el pedido."""
    salida = _jor_registrar(
        inp["persona"], inp["tarea"], inp["piezas"],
        hora_inicio=inp.get("hora_inicio", ""), hora_fin=inp.get("hora_fin", ""),
        minutos=inp.get("minutos"), pedido=inp.get("pedido", ""),
        tamano=inp.get("tamano", ""), dificultad=inp.get("dificultad", ""),
        fecha=inp.get("fecha", ""), notas=inp.get("notas", ""))
    etapa = inp.get("etapa_pedido", "")
    if etapa and inp.get("pedido"):
        nota = f"{inp['persona']}: {inp['tarea']}, {inp['piezas']} piezas"
        salida += "\n" + _prod_actualizar(inp["pedido"], etapa, nota)
    elif inp.get("pedido"):
        # La etapa se deduce sola: si con esta jornada el pedido terminó una,
        # avanza sin que nadie lo declare.
        movidos = _av_recalcular(inp["pedido"])
        if movidos:
            salida += "\n" + movidos
    return salida


PROD_CABECERA = ["#", "Cliente", "Descripción", "Deal ID", "Proceso", "Inicio",
                 "Entrega", "Etapa", "Actualizado", "Notas", "Piezas"]


def _registrar_cotizacion(inp):
    """Una cotización va a TRES sitios y ninguno puede tumbar a los otros.

    Antes el pegado desde la página solo intentaba el Cotizador Interno, que
    está bloqueado por permisos: si eso fallaba, la cotización no quedaba
    registrada en ninguna parte."""
    numero = str(inp.get("numero", "")).strip()
    if not numero:
        return "❌ Falta el número de la cotización."
    total  = int(inp.get("total", 0) or 0)
    piezas = int(inp.get("piezas", 0) or 0)
    tipo   = inp.get("tipo", "producto")
    nombre = inp.get("cliente_nombre", "")
    empresa = inp.get("cliente_empresa", "")
    fecha  = inp.get("fecha", "") or datetime.now().strftime("%d/%m/%Y")
    partes = []

    # 1. Registro de operación — es el que siempre funciona
    partes.append(_reg_cot_fila(
        numero, cliente=nombre, empresa=empresa,
        contacto=inp.get("cliente_email", "") or inp.get("cliente_telefono", ""),
        tipo=tipo, piezas=piezas, total=total, fecha=fecha,
        notas=inp.get("notas", "")))

    # 2. HubSpot — contacto, negocio, ticket y nota
    datos = {"cliente": {"nombre": nombre, "empresa": empresa,
                         "email": inp.get("cliente_email", ""),
                         "telefono": inp.get("cliente_telefono", "")},
             "fecha": fecha, "notas": inp.get("notas", "")}
    paquete = {"numero": numero, "total": total, "empresa": empresa,
               "etiqueta": "Pottery Lab" if tipo == "pottery" else "Productos",
               "detalle": inp.get("detalle", "")}
    partes.append(registrar_cotizacion_hs(datos, paquete, inp.get("deal_id", "")))

    # 3. Cotizador Interno — el desglose. Puede fallar por permisos sin arrastrar
    #    a los dos anteriores.
    if inp.get("lineas"):
        try:
            _r = _cotizar_pedido(inp["lineas"], inp.get("condiciones"),
                                 cliente=nombre or empresa)
            partes.append(_cot_guardar_hoja_pedido(_r, numero))
        except Exception as e:
            partes.append(f"⚠️ Sin desglose en el Cotizador Interno: {e}")

    return "\n".join(str(x) for x in partes if x)


def _prod_asegurar():
    """La pestaña se crea sola la primera vez. Pedírsela al usuario es mandarlo a
    hacer trabajo manual que el bot puede hacer — y a equivocarse de archivo, que
    es lo que pasó el 2026-09-20."""
    if leer_sheet_numericos("Producción!A1:K1"):
        return ""
    r = crear_pestana("Producción")
    if str(r).startswith("Error") or str(r).startswith("❌"):
        return str(r)
    escribir_rango("Producción!A1:K1", [PROD_CABECERA])
    return ""


def _prod_agregar(cliente, descripcion, proceso, fecha_entrega, deal_id="", notas="",
                  piezas=0):
    fallo = _prod_asegurar()
    if fallo:
        return "❌ No pude crear la pestaña Producción: " + fallo
    filas = leer_sheet_numericos("Producción!A:A")
    num = max(len(filas), 1)
    etapa_inicial = "modelado" if int(proceso) == 1 else "esmaltado inicial"
    hoy = datetime.now().strftime("%d/%m/%Y")
    row = [num, cliente, descripcion, deal_id, proceso, hoy, fecha_entrega,
           etapa_inicial, hoy, notas, int(piezas or 0)]
    r = agregar_fila("Producción!A:K", row)
    if str(r).startswith(("Error", "❌")):
        return str(r)
    aviso = ("" if int(piezas or 0) else
             "\n⚠️ Sin la cantidad de piezas no puedo deducir el avance. ¿Cuántas son?")
    return f"✅ Pedido de {cliente} registrado · entrega {fecha_entrega}." + aviso


def _prod_leer():
    """El tablero: la etapa sale de las jornadas, no de lo que alguien declaró."""
    _av_recalcular()
    return _av_estado()


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
        # Prefijo ' fuerza texto en Sheets (evita que interprete "Junio 2026" como fecha serial)
        actualizar_celda("Amphoritas!B17", "'" + mes_str)
    except Exception as e:
        print(f"[Recordatorio] Error guardando estado: {e}")

def verificar_recordatorios():
    global _ultima_check_recordatorio, _recordatorio_mes_enviado
    ahora = time.time()
    if ahora - _ultima_check_recordatorio < 3600:
        return
    _ultima_check_recordatorio = ahora

    hoy = datetime.now()
    if hoy.day < 10:
        return

    mes_str = f"{_MESES_ES[hoy.month]} {hoy.year}"

    # Guardia en memoria (persiste dentro del mismo deployment)
    if mes_str in _recordatorio_mes_enviado:
        return

    if _leer_ultimo_recordatorio() == mes_str:
        _recordatorio_mes_enviado.add(mes_str)
        return

    # Marcar ANTES de enviar para no repetir aunque falle el Sheet
    _recordatorio_mes_enviado.add(mes_str)

    print(f"[Recordatorio] Iniciando envío {mes_str}...")
    try:
        amphoritas = leer_amphoritas()
        pagados    = leer_pagos_mes(hoy.month, hoy.year)
        pendientes = [a for a in amphoritas if not ya_pago(a["nombre"], pagados)]

        enviados = 0
        fallidos = []
        for a in pendientes:
            ok = _enviar_recordatorio(a["nombre"], a["email"], mes_str,
                                      a["mensualidad"], dry_run=False)
            if ok:
                enviados += 1
            else:
                fallidos.append(f"{a['nombre']} ({a['email']})")

        _guardar_ultimo_recordatorio(mes_str)
        print(f"[Recordatorio] {enviados}/{len(pendientes)} enviados — {mes_str}")

        if ADMIN_CHAT_ID and pendientes:
            lista = "\n".join(f"• {a['nombre']}" for a in pendientes)
            msg = f"📧 Recordatorios {mes_str}: {enviados}/{len(pendientes)} enviados.\n{lista}"
            if fallidos:
                msg += f"\n\n⚠️ Falló envío a:\n" + "\n".join(f"• {f}" for f in fallidos)
            tg_send(int(ADMIN_CHAT_ID), msg)
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
            if not resp.get("ok"):
                print(f"Error de Telegram en getUpdates: {resp}")
                time.sleep(5)
                continue
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
                    if foto_bytes:
                        ultima_foto[chat_id] = foto_bytes

                if not chat_id or (not texto and not foto_bytes):
                    continue

                rol = rol_de(chat_id)
                if not rol:
                    print(f"[{chat_id}] RECHAZADO: {texto[:60]}")
                    tg_send(chat_id,
                            "Hola. Este bot es interno de Bosque y Cielo y tu número no "
                            f"está autorizado.\n\nSi trabajas acá, pásale este código a "
                            f"Camilo para que te dé acceso: `{chat_id}`")
                    continue

                print(f"[{chat_id}/{rol}] {texto or '[foto]'}")
                tg_send(chat_id, "⏳")
                try:
                    respuesta = procesar_mensaje(chat_id, texto, foto_bytes, rol)
                    tg_send(chat_id, respuesta)
                except Exception as e:
                    tg_send(chat_id, f"❌ Error: {e}")
                    print(f"Error procesando: {e}")

        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            print(f"Error en polling: {e}")
            time.sleep(5)

        try:
            verificar_recordatorios()
            verificar_entregas_proximas()
            verificar_reporte_semanal()
            verificar_saldo_inicial()
            verificar_cartera_vencida()
        except Exception as e:
            print(f"Error en tareas programadas: {e}")


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
