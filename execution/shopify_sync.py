#!/usr/bin/env python3
"""
Sincroniza órdenes nuevas de Shopify (bosqueycielo.com) con la pestaña Movimientos.

LA HOJA MANDA, NO EL ARCHIVO. Antes la marca de "hasta dónde llegué" vivía solo en
execution/.last_shopify_order, que está en .gitignore y por lo tanto NO viaja en el
despliegue. El disco de Railway se borra en cada reinicio, así que la marca volvía a
cero, Shopify devolvía las órdenes otra vez y todas se escribían de nuevo: una copia
completa por cada despliegue. Con ocho despliegues en tres días la hoja se llenó de
filas repetidas (2026-09-22).

Ahora, antes de escribir, se leen las órdenes que YA están en la hoja y se salta lo
que ya figura. El archivo se conserva solo como atajo: si se pierde, no pasa nada.
"""
import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=False)

sys.path.insert(0, str(Path(__file__).parent))
from sheets import agregar_fila, leer_sheet_numericos
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_TOKEN")
SHOPIFY_STORE   = os.getenv("SHOPIFY_STORE", "0b8b38.myshopify.com")
LAST_ORDER_FILE = Path(__file__).parent / ".last_shopify_order"
SYNC_INTERVAL   = 15 * 60  # 15 minutos
SHOPIFY_API_VER = "2026-07"


def shopify_get_orders(since_id: int) -> list:
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VER}/orders.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    params = {
        "status": "any",
        "limit": 250,          # el máximo de Shopify
        "order": "id asc",
    }
    if since_id:
        params["since_id"] = since_id
    # Sin since_id esto trae las 250 órdenes más VIEJAS. Con ~50 ventas sobra,
    # pero pasadas las 250 habría que paginar o el sync dejaría de ver lo nuevo.

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("orders", [])
    except Exception as e:
        print(f"[shopify_sync] Error fetching orders: {e}")
        return []


def get_last_order_id() -> int:
    if LAST_ORDER_FILE.exists():
        try:
            return int(LAST_ORDER_FILE.read_text().strip())
        except ValueError:
            pass
    return 0


def save_last_order_id(order_id: int):
    LAST_ORDER_FILE.write_text(str(order_id))


MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}


PESTANA = "Movimientos"


def _clave(fecha, cliente, monto, descripcion):
    """Lo que hace única a una orden dentro de la hoja.

    No hay columna con el ID de Shopify y agregarla ahora tocaría una hoja que
    Camilo usa a diario, así que la clave se arma con lo que ya está escrito."""
    return "|".join([
        str(fecha).strip(),
        str(cliente).strip().lower(),
        str(int(float(str(monto).replace("$", "").replace(".", "").replace(",", ".") or 0))),
        str(descripcion).strip().lower()[:60],
    ])


def ordenes_ya_registradas():
    """Las órdenes de Shopify que ya están en la hoja. None si no se pudo leer.

    `leer_sheet_numericos` devuelve [] tanto si la hoja está vacía como si la
    lectura falló. Confundir las dos cosas es volver a duplicarlo todo, así que
    primero se comprueba que la cabecera esté ahí."""
    if not leer_sheet_numericos(f"{PESTANA}!A1:J1"):
        return None
    claves = set()
    filas = leer_sheet_numericos(f"{PESTANA}!A2:J2000")
    for f in filas:
        if not f or len(f) < 9:
            continue
        if str(f[7]).strip().lower() != "shopify":
            continue
        claves.add(_clave(f[0], f[6], f[8], f[5]))
    return claves


def sheets_append(valores: list) -> bool:
    result = agregar_fila(f"{PESTANA}!A:J", valores)
    return "correctamente" in result


def order_to_row(order: dict) -> list:
    created_at = order.get("created_at", "")
    try:
        dt    = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        fecha = dt.strftime("%d/%m/%Y")
        mes   = MESES[dt.month]
        anio  = str(dt.year)
    except Exception:
        fecha = created_at[:10] if len(created_at) >= 10 else ""
        mes   = ""
        anio  = ""

    customer = order.get("customer") or {}
    nombre   = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    if not nombre:
        nombre = order.get("email", "")

    line_items = order.get("line_items", [])
    total      = int(float(order.get("total_price", 0) or 0))

    if len(line_items) == 1:
        item        = line_items[0]
        descripcion = item.get("sku") or item.get("title", "")
    else:
        descripcion = "; ".join(
            f"{i.get('title', '')} x{i.get('quantity', 1)}" for i in line_items
        )[:100]

    return [
        fecha, mes, anio,
        "Ingreso", "Ecommerce",
        descripcion, nombre,
        "Shopify", str(total), ""   # J: Estado vacío
    ]


def sync_once():
    last_id = get_last_order_id()
    print(f"[shopify_sync] {datetime.now().strftime('%H:%M')} — buscando órdenes desde ID {last_id}...")
    orders = shopify_get_orders(last_id)

    if not orders:
        print("[shopify_sync] Sin órdenes nuevas.")
        return

    # La hoja es la fuente de verdad: si el disco se borró, acá se ve qué falta.
    ya = ordenes_ya_registradas()
    if ya is None:
        print("[shopify_sync] No pude leer la hoja: no escribo nada para no duplicar.")
        return

    nuevas = repetidas = 0
    for order in orders:
        oid = order.get("id", 0)
        num = order.get("order_number", oid)
        if oid <= last_id:
            continue
        row = order_to_row(order)
        if _clave(row[0], row[6], row[8], row[5]) in ya:
            repetidas += 1
            save_last_order_id(oid)
            continue
        if sheets_append(row):
            print(f"[shopify_sync] Orden #{num} registrada")
            ya.add(_clave(row[0], row[6], row[8], row[5]))
            save_last_order_id(oid)
            nuevas += 1
        else:
            print(f"[shopify_sync] ERROR registrando orden #{num}")

    print(f"[shopify_sync] {nuevas} nueva(s) · {repetidas} ya estaban.")


def main():
    if not SHOPIFY_TOKEN:
        print("[shopify_sync] ERROR: SHOPIFY_TOKEN no configurado en .env")
        return
    print(f"[shopify_sync] Iniciado para {SHOPIFY_STORE}. Intervalo: 15 min.")
    while True:
        try:
            sync_once()
        except Exception as e:
            print(f"[shopify_sync] Error inesperado: {e}")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
