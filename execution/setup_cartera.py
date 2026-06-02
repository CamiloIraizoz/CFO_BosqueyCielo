#!/usr/bin/env python3
"""Crea el tab 'Cartera' en el Sheet con headers."""
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=False)
sys.path.insert(0, str(Path(__file__).parent))
from sheets import crear_pestana, escribir_rango

def setup():
    print(crear_pestana("Cartera"))
    headers = [[
        "Sección", "Tipo", "Cliente / Proveedor", "Concepto",
        "Monto Total", "Pagado", "Pendiente", "Fecha Vencimiento",
        "Estado", "Notas"
    ]]
    print(escribir_rango("Cartera!A1:J1", headers))
    print("Tab Cartera lista.")

if __name__ == "__main__":
    setup()
