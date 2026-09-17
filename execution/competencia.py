#!/usr/bin/env python3
"""
Análisis de competencia: precios de productos de cerámica y de talleres en
Bogotá, Cali y Medellín.

Tres formas de leer a un competidor, según lo que publique:
  - "shopify": catálogo completo y exacto vía /products.json. Es el ideal.
  - "html":    se baja la página pública y Claude extrae los precios del texto.
               Se usa un modelo y no selectores CSS porque cada competidor tiene
               su web hecha en algo distinto y la rediseña cada tanto.
  - "manual":  el competidor existe pero no publica precios (los da por DM o los
               carga con JavaScript). Queda registrado sin precio, nunca inventado.

Respeta robots.txt y no reintenta contra quien bloquea: si un sitio responde 403
se anota como bloqueado y se sigue.

Uso:
    python3 execution/competencia.py                      # barrido completo → Sheet
    python3 execution/competencia.py --tipo talleres      # solo talleres
    python3 execution/competencia.py --ciudad Medellín
    python3 execution/competencia.py --sin-sheet --json   # prueba sin escribir
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)
sys.path.insert(0, str(Path(__file__).parent))

PESTANA = "Competencia"
UA = "BosqueYCieloBot/1.0 (+https://bosqueycielo.com; analisis de mercado)"
MODELO = os.getenv("MODELO_COMPETENCIA", "claude-haiku-4-5-20251001")
TIMEOUT = 20

# Verificados uno por uno el 2026-09-17: se probó qué publica cada quién y en qué
# URL. Las rutas importan: casi ninguno muestra precios en su página de inicio.
COMPETIDORES = [
    # ── Productos ────────────────────────────────────────────────────────────
    {"nombre": "Cerámicas Carmesí", "ciudad": "El Carmen de Viboral", "tipo": "productos",
     "metodo": "shopify", "url": "https://carmesi.co"},
    {"nombre": "Home Poetry", "ciudad": "Bogotá", "tipo": "productos",
     "metodo": "shopify", "url": "https://www.homepoetry.co"},
    {"nombre": "Amasa Cerámica", "ciudad": "Bogotá", "tipo": "productos",
     "metodo": "html", "url": "https://www.amasaceramica.com/shop"},
    {"nombre": "Tybso", "ciudad": "Bogotá", "tipo": "productos",
     "metodo": "manual", "url": "https://www.tybso.com/",
     "nota": "Tienda online sin precios visibles para lectura automática"},
    {"nombre": "Fray Angélico", "ciudad": "Bogotá", "tipo": "productos",
     "metodo": "manual", "url": "https://www.frayangelicoceramicas.com/vajillas.php",
     "nota": "Vajillas por encargo, cotiza a pedido — no publica precios"},

    # ── Talleres y experiencias ──────────────────────────────────────────────
    {"nombre": "Dos Golondrinas", "ciudad": "Medellín", "tipo": "talleres",
     "metodo": "html", "url": "https://www.dosgolondrinasestudio.com/"},
    {"nombre": "Tornus Cerámica", "ciudad": "Bogotá", "tipo": "talleres",
     "metodo": "html", "url": "https://tornusceramica.com/clases"},
    {"nombre": "KUAN Escuela de Cerámica", "ciudad": "Bogotá", "tipo": "talleres",
     "metodo": "manual", "url": "https://kuanlab.co/",
     "nota": "Publica precios de insumos en /tienda, no de sus clases"},
    {"nombre": "Mama Pottery", "ciudad": "Bogotá", "tipo": "talleres",
     "metodo": "manual", "url": "https://mamapottery.com/talleres",
     "nota": "No publica precios en la web"},
    {"nombre": "Alharaca Taller", "ciudad": "Bogotá", "tipo": "talleres",
     "metodo": "manual", "url": "https://www.alharacataller.com/",
     "nota": "Sitio Wix que carga el contenido por JavaScript — no legible"},
    {"nombre": "Lumbre y Barro", "ciudad": "Medellín", "tipo": "talleres",
     "metodo": "manual", "url": "https://lumbreybarro.shop/cat/experiencias-con-ceramica/",
     "nota": "El sitio bloquea consultas automáticas — revisar a mano"},

    # ── Cali ─────────────────────────────────────────────────────────────────
    # Pendiente: en la búsqueda del 2026-09-17 no apareció ningún taller de Cali
    # con web propia y precios publicados; la competencia local se mueve en
    # Instagram. Agregar aquí los que Camilo y Daniela conozcan de primera mano.
]


# ── Utilidades ──────────────────────────────────────────────────────────────

def _permitido(url: str) -> bool:
    """Respeta robots.txt. Si no se puede leer, se asume permitido (es lo usual)."""
    try:
        partes = urlparse(url)
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{partes.scheme}://{partes.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def _sin_tildes(texto: str) -> str:
    """Para que '--solo carmesi' encuentre a 'Cerámicas Carmesí' y '--ciudad medellin' funcione."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                   if not unicodedata.combining(c))


def _precio_a_entero(valor) -> int:
    """'$135.000', '135000.00', 135000 → 135000. Devuelve 0 si no hay número."""
    if valor is None:
        return 0
    if isinstance(valor, (int, float)):
        return int(valor)
    limpio = re.sub(r"[^\d,.]", "", str(valor))
    if not limpio:
        return 0
    # Formato colombiano: el punto es separador de miles.
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    elif limpio.count(".") == 1 and len(limpio.split(".")[1]) == 2:
        pass  # 50500.00 → decimales de Shopify
    else:
        limpio = limpio.replace(".", "").replace(",", "")
    try:
        return int(float(limpio))
    except ValueError:
        return 0


def _texto_visible(html: str, limite: int = 14000) -> str:
    """Quita scripts, estilos y etiquetas. Lo que queda es lo que ve un cliente."""
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    texto = re.sub(r"(?s)<[^>]+>", " ", html)
    texto = (texto.replace("&nbsp;", " ").replace("&amp;", "&")
                  .replace("&#8217;", "'").replace("&quot;", '"'))
    texto = re.sub(r"[ \t\r\f\v]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n", texto)
    return texto.strip()[:limite]


# ── Lectores por método ─────────────────────────────────────────────────────

def _leer_shopify(comp: dict, limite: int = 250) -> list:
    """Catálogo completo vía products.json. Exacto y estable."""
    url = comp["url"].rstrip("/") + f"/products.json?limit={limite}"
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    resp.raise_for_status()
    filas = []
    for prod in resp.json().get("products", []):
        for variante in prod.get("variants", []):
            precio = _precio_a_entero(variante.get("price"))
            if not precio:
                continue
            nombre = prod.get("title", "")
            if variante.get("title") and variante["title"] != "Default Title":
                nombre += f" — {variante['title']}"
            filas.append({
                "item": nombre[:120],
                "precio": precio,
                "unidad": "pieza",
                "detalle": prod.get("product_type") or "",
                "fuente": f"{comp['url'].rstrip('/')}/products/{prod.get('handle','')}",
            })
            break  # una fila por producto: la primera variante basta para comparar
    return filas


def _leer_html_con_claude(comp: dict) -> list:
    """Baja la página y le pide a Claude los precios que encuentre en el texto."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY no configurado")

    resp = requests.get(comp["url"], headers={"User-Agent": UA}, timeout=TIMEOUT)
    resp.raise_for_status()
    texto = _texto_visible(resp.text)
    if not texto:
        return []

    que_busco = ("productos de cerámica (tazas, platos, vajilla, materas) con su precio"
                 if comp["tipo"] == "productos"
                 else "talleres, clases o experiencias de cerámica con su precio")

    mensaje = anthropic.Anthropic(api_key=api_key).messages.create(
        model=MODELO,
        max_tokens=2000,
        messages=[{"role": "user", "content": f"""Del texto de la página web de {comp['nombre']} ({comp['ciudad']}), extrae {que_busco}.

Devuelve SOLO un array JSON, sin explicaciones ni ```. Cada elemento:
{{"item": "nombre del producto o taller", "precio": 135000, "unidad": "pieza|persona|clase|hora", "detalle": "duración, tamaño o qué incluye"}}

Reglas estrictas:
- "precio" es un número entero en pesos colombianos, sin puntos ni símbolos.
- Solo incluye lo que tenga un precio explícito en el texto. Si no hay precio, NO lo inventes ni lo estimes: omítelo.
- Si la página no muestra ningún precio, devuelve [].
- Máximo 30 elementos, los más representativos.

TEXTO DE LA PÁGINA:
{texto}"""}],
    )

    crudo = mensaje.content[0].text.strip()
    crudo = re.sub(r"^```(?:json)?|```$", "", crudo, flags=re.MULTILINE).strip()
    try:
        items = json.loads(crudo)
    except json.JSONDecodeError:
        print(f"  [aviso] {comp['nombre']}: respuesta no parseable, se omite")
        return []

    filas = []
    for item in items if isinstance(items, list) else []:
        precio = _precio_a_entero(item.get("precio"))
        if not precio:
            continue
        filas.append({
            "item": str(item.get("item", ""))[:120],
            "precio": precio,
            "unidad": str(item.get("unidad", ""))[:20],
            "detalle": str(item.get("detalle", ""))[:150],
            "fuente": comp["url"],
        })
    return filas


# ── Barrido ─────────────────────────────────────────────────────────────────

def barrer(tipo: str = "", ciudad: str = "", solo: str = "") -> list:
    """Recorre los competidores y devuelve las filas listas para el Sheet."""
    hoy = date.today().strftime("%d/%m/%Y")
    filas = []

    objetivo = [c for c in COMPETIDORES
                if (not tipo or c["tipo"] == tipo)
                and (not ciudad or _sin_tildes(ciudad) in _sin_tildes(c["ciudad"]))
                and (not solo or _sin_tildes(solo) in _sin_tildes(c["nombre"]))]

    if not objetivo:
        print("Ningún competidor coincide con los filtros. Registrados: "
              + ", ".join(c["nombre"] for c in COMPETIDORES))
        return []

    for comp in objetivo:
        etiqueta = f"{comp['nombre']} ({comp['ciudad']}, {comp['tipo']})"
        if comp["metodo"] == "manual":
            print(f"○ {etiqueta}: sin precios públicos")
            filas.append([hoy, comp["nombre"], comp["ciudad"], comp["tipo"],
                          "(sin precios públicos)", "", "",
                          comp.get("nota", "No publica precios en la web"), comp["url"]])
            continue

        if not _permitido(comp["url"]):
            print(f"○ {etiqueta}: robots.txt no lo permite, se omite")
            filas.append([hoy, comp["nombre"], comp["ciudad"], comp["tipo"],
                          "(no consultado)", "", "", "robots.txt no lo permite", comp["url"]])
            continue

        try:
            encontrados = (_leer_shopify(comp) if comp["metodo"] == "shopify"
                           else _leer_html_con_claude(comp))
        except requests.HTTPError as e:
            codigo = e.response.status_code if e.response is not None else "?"
            motivo = "el sitio bloquea consultas automáticas" if codigo in (401, 403, 429) \
                     else f"HTTP {codigo}"
            print(f"✗ {etiqueta}: {motivo}")
            filas.append([hoy, comp["nombre"], comp["ciudad"], comp["tipo"],
                          "(no se pudo leer)", "", "", motivo, comp["url"]])
            continue
        except Exception as e:
            print(f"✗ {etiqueta}: {e}")
            filas.append([hoy, comp["nombre"], comp["ciudad"], comp["tipo"],
                          "(no se pudo leer)", "", "", str(e)[:120], comp["url"]])
            continue

        if not encontrados:
            print(f"○ {etiqueta}: la página no muestra precios")
            filas.append([hoy, comp["nombre"], comp["ciudad"], comp["tipo"],
                          "(sin precios en la página)", "", "",
                          "Los precios no están publicados", comp["url"]])
            continue

        print(f"✓ {etiqueta}: {len(encontrados)} precios")
        for f in encontrados:
            filas.append([hoy, comp["nombre"], comp["ciudad"], comp["tipo"],
                          f["item"], f["precio"], f["unidad"], f["detalle"], f["fuente"]])
        time.sleep(1)   # sin apuro: no atropellamos los sitios ajenos

    return filas


ENCABEZADOS = ["Fecha", "Competidor", "Ciudad", "Tipo",
               "Ítem", "Precio COP", "Unidad", "Detalle", "Fuente"]


def guardar(filas: list) -> str:
    from sheets import crear_pestana, agregar_fila, escribir_rango
    if not filas:
        return "Nada que guardar."
    # La pestaña se crea sola en el primer barrido, con sus encabezados.
    if "creada" in crear_pestana(PESTANA):
        escribir_rango(f"{PESTANA}!A1:I1", [ENCABEZADOS])
    for fila in filas:
        agregar_fila(f"{PESTANA}!A:I", fila)
    return f"{len(filas)} filas guardadas en la pestaña {PESTANA}."


def resumen(filas: list) -> str:
    """Resumen corto para Telegram: rango de precios por competidor."""
    if not filas:
        return "No se consultó ningún competidor."

    # Separado a propósito: "no publica" es información de mercado, "no se pudo
    # leer" es un problema nuestro que hay que arreglar.
    no_publica = {f[1] for f in filas if str(f[4]).startswith("(sin precios")}
    fallo      = {f[1] for f in filas if str(f[4]).startswith(("(no se pudo", "(no consultado"))}

    con_precio = [f for f in filas if isinstance(f[5], int) and f[5] > 0]
    if not con_precio:
        partes = [f"🔍 Competencia — {filas[0][0]}", "", "No se encontró ningún precio público."]
        if no_publica:
            partes.append("No publican precios: " + ", ".join(sorted(no_publica)))
        if fallo:
            partes.append("⚠️ No se pudieron leer: " + ", ".join(sorted(fallo)))
        return "\n".join(partes)

    por_competidor = {}
    for f in con_precio:
        por_competidor.setdefault((f[1], f[2], f[3]), []).append(f[5])

    lineas = [f"🔍 Competencia — {filas[0][0]}", ""]
    for (nombre, ciudad, tipo), precios in sorted(por_competidor.items(), key=lambda x: x[0][2]):
        fmt = lambda n: f"${n:,}".replace(",", ".")
        lineas.append(f"• {nombre} ({ciudad}, {tipo}): {len(precios)} ítems · "
                      f"{fmt(min(precios))} – {fmt(max(precios))} · "
                      f"promedio {fmt(sum(precios)//len(precios))}")

    if no_publica:
        lineas.append("")
        lineas.append("No publican precios: " + ", ".join(sorted(no_publica)))
    if fallo:
        lineas.append("⚠️ No se pudieron leer: " + ", ".join(sorted(fallo)))
    return "\n".join(lineas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Barrido de precios de la competencia")
    ap.add_argument("--tipo", default="", choices=["", "productos", "talleres"])
    ap.add_argument("--ciudad", default="")
    ap.add_argument("--solo", default="", help="un competidor por nombre")
    ap.add_argument("--sin-sheet", action="store_true", help="no escribe en el Sheet")
    ap.add_argument("--json", action="store_true", help="imprime las filas en JSON")
    args = ap.parse_args()

    filas = barrer(args.tipo, args.ciudad, args.solo)
    print()
    print(resumen(filas))
    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2))
    if not args.sin_sheet:
        print()
        print(guardar(filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
