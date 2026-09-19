#!/usr/bin/env python3
"""
Arma la versión publicable de la página: mete jsPDF DENTRO del HTML.

Por qué: el artifact se sirve desde una URL sin carpeta propia, así que un
`<script src="vendor/...">` relativo no siempre resuelve — y cuando no resuelve,
el botón de PDF no hace nada. Incrustarla es la única forma de que la página no
dependa de cómo esté montada.

    python3 web/build.py          →  .tmp/bosque-y-cielo.build.html

Ese es el archivo que se publica; el del repo se queda legible.
"""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "web" / "bosque-y-cielo.html"
LIBRERIA = RAIZ / "web" / "vendor" / "jspdf.umd.min.js"
SALIDA = RAIZ / ".tmp" / "bosque-y-cielo.build.html"
MARCA = '<script src="vendor/jspdf.umd.min.js"></script>'


def main() -> int:
    html = FUENTE.read_text()
    if MARCA not in html:
        print(f"❌ No encontré {MARCA} en {FUENTE.name}")
        return 1
    libreria = LIBRERIA.read_text()
    if "</script" in libreria:
        print("❌ La librería contiene '</script': habría que escaparla")
        return 1
    html = html.replace(MARCA, "<script>\n" + libreria + "\n</script>")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html)
    print(f"✅ {SALIDA.relative_to(RAIZ)} — {len(html) / 1024:.0f} KB "
          f"(página {FUENTE.stat().st_size / 1024:.0f} KB + jsPDF "
          f"{LIBRERIA.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
