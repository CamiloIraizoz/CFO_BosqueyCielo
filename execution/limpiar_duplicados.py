#!/usr/bin/env python3
"""Encuentra —y solo si se lo pides, borra— filas repetidas en Movimientos.

El 2026-09-22 la hoja apareció con las mismas ventas de Shopify escritas decenas
de veces. La causa está explicada en `shopify_sync.py`: la marca de "hasta dónde
llegué" vivía en un archivo del disco de Railway, que se borra en cada
despliegue, así que cada despliegue reescribía todas las órdenes.

Ese bug ya está arreglado. Esto limpia lo que quedó.

    python3 execution/limpiar_duplicados.py            # solo informa
    python3 execution/limpiar_duplicados.py --borrar   # borra de verdad

Conserva SIEMPRE la primera aparición de cada movimiento y borra las copias.
Por defecto solo mira las filas de Shopify, que son las que se duplicaron.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sheets import borrar_filas, leer_sheet_numericos

PESTANA = "Movimientos"


def _clave(f):
    return "|".join(str(f[i]).strip().lower() if i < len(f) else ""
                    for i in (0, 3, 4, 5, 6, 7, 8))


def duplicados(solo_shopify=True):
    """(filas a borrar, cuántas quedan, total revisadas)."""
    filas = leer_sheet_numericos(f"{PESTANA}!A2:J5000")
    vistas, repetidas, conservadas = set(), [], 0
    for i, f in enumerate(filas, start=2):     # la 1 es la cabecera
        if not f or len(f) < 9:
            continue
        if solo_shopify and str(f[7]).strip().lower() != "shopify":
            continue
        k = _clave(f)
        if k in vistas:
            repetidas.append((i, f))
        else:
            vistas.add(k)
            conservadas += 1
    return repetidas, conservadas, len(filas)


def main():
    borrar = "--borrar" in sys.argv
    todas = "--todas" in sys.argv
    repetidas, conservadas, total = duplicados(solo_shopify=not todas)

    print(f"Revisadas {total} filas de {PESTANA}"
          f"{'' if todas else ' (solo las de Shopify)'}.")
    print(f"Movimientos distintos: {conservadas}")
    print(f"Filas repetidas: {len(repetidas)}")
    if not repetidas:
        print("Nada que limpiar. 🎉")
        return

    print("\nSe conservaría la PRIMERA aparición de cada uno. Ejemplos a borrar:")
    for n, f in repetidas[:10]:
        print(f"  fila {n}: {f[0]} · {f[6]} · ${f[8]}")
    if len(repetidas) > 10:
        print(f"  … y {len(repetidas) - 10} más")

    if not borrar:
        print("\nEsto fue solo un informe: no se tocó nada.")
        print("Para borrarlas de verdad: python3 execution/limpiar_duplicados.py --borrar")
        print("Antes de hacerlo, saca una copia de la hoja (Archivo → Hacer una copia).")
        return

    print(f"\nBorrando {len(repetidas)} filas…")
    print(borrar_filas(PESTANA, [n for n, _ in repetidas]))


if __name__ == "__main__":
    main()
