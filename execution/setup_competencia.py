#!/usr/bin/env python3
"""Crea el tab 'Competencia' en el Sheet con headers."""
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=False)
sys.path.insert(0, str(Path(__file__).parent))
from sheets import crear_pestana, escribir_rango

def setup():
    print(crear_pestana("Competencia"))
    headers = [[
        "Fecha", "Competidor", "Ciudad", "Tipo",
        "Ítem", "Precio COP", "Unidad", "Detalle", "Fuente"
    ]]
    print(escribir_rango("Competencia!A1:I1", headers))
    print("Tab Competencia lista.")

if __name__ == "__main__":
    setup()
