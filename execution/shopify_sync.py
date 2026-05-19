#!/usr/bin/env python3
"""
Sincroniza órdenes nuevas de Shopify (bosqueycielo.com) con la pestaña Ecommerce del Google Sheet.
Ejecutar en background: nohup python3 execution/shopify_sync.py >> shopify_sync.log 2>&1 &
Corre cada 15 minutos. Guarda el ID de la última orden en execution/.last_shopify_order.
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
from sheets import agregar_fila
SHOPIFY_TOKEN   = os.getenv("SHOPIFY_TOKEN")
SHOPIFY_STORE   = os.getenv("SHOPIFY_STORE", "bosqueycielo.myshopify.com")
LAST_ORDER_FILE = Path(__file__).parent / ".last_shopify_order"
SYNC_INTERVAL   = 15 * 60  # 15 minutos
SHOPIFY_API_VER = "2024-01"


def shopify_get_orders(since_id: int) -> list:
    url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VER}/orders.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }
    params = {
        "status": "any",
        "limit": 50,
        "order": "id asc",
    }
    if since_id:
        params["since_id"] = since_id

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


def sheets_append(valores: list) -> bool:
    result = agregar_fila("Movimientos!A:J", valores)
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

    nuevas = 0
    for order in orders:
        oid = order.get("id", 0)
        if oid <= last_id:
            continue
        row = order_to_row(order)
        ok  = sheets_append(row)
        num = order.get("order_number", oid)
        if ok:
            print(f"[shopify_sync] Orden #{num} registrada → Ecommerce")
            save_last_order_id(oid)
            nuevas += 1
        else:
            print(f"[shopify_sync] ERROR registrando orden #{num}")

    print(f"[shopify_sync] {nuevas} orden(es) nueva(s) registrada(s).")


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
