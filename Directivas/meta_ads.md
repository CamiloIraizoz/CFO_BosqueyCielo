# Directiva: Meta Ads (Bosque y Cielo)

## Objetivo
Analizar y, cuando se pida, ejecutar acciones sobre las campañas de Meta Ads (Facebook/Instagram) de Bosque y Cielo — vía Composio, toolkit `metaads`.

## Cuenta publicitaria
`act_379796923470762` — "Bosque y Cielo Homeware - Cuenta publicitaria"

(Existe también `act_1287506706483550`, cuenta personal de Camilo — nunca usarla, es de otra marca.)

## Regla de oro: escrituras SIEMPRE con confirmación
A diferencia de las escrituras en el Sheet (donde se confirma "si no está 100% claro"), en Meta Ads **se confirma SIEMPRE, sin excepción**, antes de:
- Pausar o reanudar una campaña
- Cambiar un presupuesto
- Cualquier otra escritura

Es gasto publicitario real en curso — un cambio no solicitado puede costar dinero o parar ventas. Mostrar claramente qué se va a cambiar (nombre de campaña, estado/presupuesto actual → nuevo) antes de ejecutar.

## Herramientas Meta Ads (ver `execution/bot.py`)

- `meta_ads_campanas()` — lista todas las campañas de la cuenta con id, nombre, status, effective_status, objetivo y presupuesto. Úsalo primero para saber qué campañas existen y sus IDs antes de cualquier otra acción.
- `meta_ads_insights(nivel, object_id, date_preset)` — métricas de rendimiento. `nivel` es "account", "campaign", "adset" o "ad"; `object_id` es la cuenta (`act_379796923470762`) o el ID de la campaña/adset/ad; `date_preset` acepta "today", "yesterday", "last_7d", "last_30d", "this_month", "last_month" (default "last_7d" si no se especifica).
- `meta_ads_pausar_campana(campaign_id)` — pausa una campaña (requiere confirmación previa).
- `meta_ads_reanudar_campana(campaign_id)` — reanuda una campaña pausada (requiere confirmación previa).
- `meta_ads_actualizar_presupuesto(campaign_id, presupuesto_diario)` — cambia el presupuesto diario en pesos colombianos (requiere confirmación previa; leer el presupuesto actual con `meta_ads_campanas()` antes de cambiarlo, para poder mostrar "de $X a $Y").

## Métricas prioritarias al analizar
En este orden de importancia para el negocio:
1. **ROAS** (retorno de inversión) — `action_values` (compras) / `spend`. Cruzar con ventas reales del Sheet cuando sea posible (Shopify + Meta Pixel ya conectados, 2026-08-05).
2. **CPA** (costo por conversión) — `spend` / número de compras en `actions`.
3. **Alcance y frecuencia** (`reach`, `frequency`) — relevante sobre todo para campañas de awareness/branding.
4. **Gasto vs. presupuesto** — que no se sobre-ejecute ni sub-ejecute el presupuesto diario/total planeado.

Nota técnica: en `actions`/`action_values` los resultados vienen como array por `action_type` (ej. `purchase`, `link_click`, `landing_page_view`) — filtrar por el tipo relevante, no sumar todo el array a ciegas. Los valores numéricos pueden venir como string.

## Resumen diario (6:00 p.m., Telegram)
Rutina programada aparte (no corre dentro de `bot.py`) que manda por Telegram (toolkit `telegram` de Composio, bot @IraizozCFO_bot) un resumen de:
- Gasto del día por campaña activa
- ROAS y CPA del día (o últimos 7 días si el día trae poco dato)
- Alertas si alguna campaña activa lleva 0 conversiones con gasto significativo, o si el gasto del día se disparó vs. el promedio de los últimos 7 días

## Casos extremos
- Si `meta_ads_campanas()` no trae ninguna campaña activa, decirlo explícitamente — no inventar datos.
- Si insights devuelve filas vacías para el rango pedido, puede ser que la campaña no tuvo actividad ese período — no asumir error.
- Los presupuestos se ingresan en pesos colombianos (COP), sin signos ni puntos, igual que en el Sheet.
