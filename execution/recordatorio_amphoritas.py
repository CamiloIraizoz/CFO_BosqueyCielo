#!/usr/bin/env python3
"""
Recordatorio de mensualidades Amphoritas — Amphora B&C
Lee la lista en la pestaña Amphoritas, cruza con pagos del mes en Studio Amphora,
y envía email vía Resend a las que aún no han pagado.

Uso:
    python3 execution/recordatorio_amphoritas.py [--mes "Mayo 2026"] [--dry-run]
"""
import sys
import os
import requests
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

sys.path.insert(0, str(Path(__file__).parent))
from sheets import leer_sheet_numericos

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL     = os.getenv("AMPHORITAS_FROM_EMAIL", "Amphora B&C <hola@bosqueycielo.com>")

MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


# ── Lectura del Sheet ─────────────────────────────────────────────────────────

def leer_amphoritas() -> list[dict]:
    filas = leer_sheet_numericos("Amphoritas!A:E")
    result = []
    for fila in filas[1:]:
        while len(fila) < 5:
            fila.append("")
        activa = str(fila[3]).strip().lower()
        if activa not in ("sí", "si", "yes", "1", "true"):
            continue
        result.append({
            "nombre":      str(fila[0]).strip(),
            "email":       str(fila[1]).strip().lower(),
            "mensualidad": int(float(fila[2])) if isinstance(fila[2], (int, float)) else 500000,
        })
    return result


def _serial_a_fecha(serial):
    """Convierte número serial de Google Sheets a date."""
    try:
        return date(1899, 12, 30) + timedelta(days=int(serial))
    except Exception:
        return None


def leer_pagos_mes(mes_num: int, anio: int) -> set[str]:
    """Retorna set de nombres (lower) que tienen pago registrado en el mes."""
    filas = leer_sheet_numericos("Studio Amphora!A:I")
    pagados = set()
    for fila in filas[1:]:
        if len(fila) < 3:
            continue
        fecha_val = fila[1] if len(fila) > 1 else ""
        nombre    = str(fila[2]).strip() if len(fila) > 2 else ""
        if not nombre:
            continue

        # Fecha como string "DD/MM/YYYY"
        if isinstance(fecha_val, str) and "/" in fecha_val:
            try:
                parts = fecha_val.split("/")
                m, y = int(parts[1]), int(parts[2])
                if m == mes_num and y == anio:
                    pagados.add(nombre.lower())
            except Exception:
                pass
        # Fecha como número serial de Sheets
        elif isinstance(fecha_val, (int, float)):
            d = _serial_a_fecha(fecha_val)
            if d and d.month == mes_num and d.year == anio:
                pagados.add(nombre.lower())

    return pagados


# ── Matching flexible de nombres ──────────────────────────────────────────────

def ya_pago(nombre: str, pagados: set[str]) -> bool:
    nl = nombre.lower()
    if nl in pagados:
        return True
    partes = [p for p in nl.split() if len(p) > 2]  # ignorar "de", "la", etc.
    for pagado in pagados:
        coincidencias = sum(1 for p in partes if p in pagado)
        if coincidencias >= 2:
            return True
        if nl in pagado or pagado in nl:
            return True
    return False


# ── Envío de email ────────────────────────────────────────────────────────────

def enviar_recordatorio(nombre: str, email: str, mes: str, valor: int,
                        dry_run: bool) -> bool:
    primer_nombre = nombre.split()[0].capitalize()
    subject = f"Un recordatorio con cariño — Studio Amphora B&C 🏺"
    html = f"""
<p>Hola {primer_nombre} 🌿</p>
<p>¡Espero que estés muy bien! Solo paso a recordarte con todo el cariño
que tu mensualidad de <strong>Studio Amphora B&C</strong> de <strong>{mes}</strong>
está pendiente.</p>
<p><strong>Valor:</strong> ${valor:,}</p>
<p>Puedes pagar por Nequi, transferencia bancaria o directamente en el estudio
cuando quieras. Si ya lo hiciste, ¡ignora esto y mil gracias! 🏺</p>
<p>¡Nos vemos pronto entre arcilla y buenos momentos!</p>
<p>Con cariño,<br>
<strong>Daniela y el equipo de Amphora B&C</strong></p>
"""
    if dry_run:
        print(f"    [DRY-RUN] → {nombre} <{email}>  ${valor:,}")
        return True

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from":    FROM_EMAIL,
                "to":      [email],
                "cc":      ["camilo.iraizoz@gmail.com", "daniela.sandoval@gmail.com"],
                "subject": subject,
                "html":    html,
            },
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        detail = ""
        if hasattr(e, "response") and e.response is not None:
            detail = f" — Resend: {e.response.status_code} {e.response.text[:200]}"
        print(f"    Error enviando a {email}: {e}{detail}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv

    now = datetime.now()
    mes_num, anio = now.month, now.year
    mes_str = f"{MESES_ES[mes_num]} {anio}"

    if "--mes" in sys.argv:
        idx = sys.argv.index("--mes")
        mes_str = sys.argv[idx + 1]
        partes = mes_str.split()
        nombres_mes = {m.lower(): i for i, m in enumerate(MESES_ES) if i > 0}
        mes_num = nombres_mes.get(partes[0].lower(), mes_num)
        anio = int(partes[1]) if len(partes) > 1 else anio

    print(f"\nRecordatorios Amphoritas — {mes_str}" + (" [DRY-RUN]" if dry_run else ""))
    print("=" * 55)

    amphoritas = leer_amphoritas()
    print(f"Amphoritas activas : {len(amphoritas)}")

    pagados = leer_pagos_mes(mes_num, anio)
    print(f"Pagos en Sheet     : {len(pagados)}")
    print()

    ya_pagaron = [a for a in amphoritas if ya_pago(a["nombre"], pagados)]
    pendientes = [a for a in amphoritas if not ya_pago(a["nombre"], pagados)]

    print(f"✅ Ya pagaron ({len(ya_pagaron)}):")
    for a in ya_pagaron:
        print(f"   {a['nombre']}")

    print(f"\n⚠️  Pendientes ({len(pendientes)}):")
    enviados = 0
    for a in pendientes:
        ok = enviar_recordatorio(a["nombre"], a["email"], mes_str,
                                 a["mensualidad"], dry_run)
        estado = "✅ email enviado" if ok else "❌ error"
        print(f"   {a['nombre']:<30}  {estado}")
        if ok:
            enviados += 1

    print()
    print(f"Recordatorios enviados: {enviados}/{len(pendientes)}")
    print("=" * 55)


if __name__ == "__main__":
    main()
