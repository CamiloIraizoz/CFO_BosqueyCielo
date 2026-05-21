#!/usr/bin/env python3
"""
Cotizaciones y email para Bosque y Cielo.
Env var requerida: RESEND_API_KEY
"""
import os
import requests as _requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_URL     = "https://api.resend.com/emails"

FROM_EMAIL = "Bosque y Cielo <hola@bosqueycielo.com>"
CC_EMAILS  = ["daniela.sandoval@bosqueycielo.com", "camilo.iraizoz@gmail.com"]


def _send(to_email: str, subject: str, html: str) -> str:
    """Envía un email via Resend API."""
    if not RESEND_API_KEY:
        return "Error: RESEND_API_KEY no configurado."
    resp = _requests.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={"from": FROM_EMAIL, "to": [to_email], "cc": CC_EMAILS, "subject": subject, "html": html},
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id", "ok")
    return f"Error Resend {resp.status_code}: {resp.text}"


def _fmt(value) -> str:
    try:
        return f"${int(float(value)):,}".replace(",", ".")
    except Exception:
        return str(value)


def _numero() -> str:
    import time
    ts = str(int(time.time()))
    return f"BYC-{ts[-6:]}"


def generar_html_cotizacion(datos: dict) -> str:
    """Genera el HTML de la cotización (compatible email)."""
    cliente    = datos.get("cliente", {})
    productos  = datos.get("productos", [])
    envio_val  = int(float(datos.get("envio", 0) or 0))
    notas      = datos.get("notas", "")
    plazo      = datos.get("plazo_entrega", "4-6 semanas hábiles")
    condiciones = datos.get("condiciones_pago", "50% anticipo · 50% contra entrega")
    numero     = datos.get("numero") or _numero()
    fecha      = datos.get("fecha", "")

    subtotal = sum(
        int(float(p.get("precio_unitario", 0))) * int(p.get("cantidad", 1))
        for p in productos
    )
    total = subtotal + envio_val

    # Product rows
    rows = ""
    for p in productos:
        qty   = int(p.get("cantidad", 1))
        price = int(float(p.get("precio_unitario", 0)))
        desc  = f"<br><span style='color:#9a7a74;font-size:11px'>{p['descripcion']}</span>" if p.get("descripcion") else ""
        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #EAE0DC;font-family:Arial,sans-serif;font-size:13px;color:#3a2a27;">
            <strong>{p.get('nombre','')}</strong>{desc}
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #EAE0DC;text-align:center;font-family:Arial,sans-serif;font-size:13px;color:#3a2a27;">{qty}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #EAE0DC;text-align:right;font-family:Arial,sans-serif;font-size:13px;color:#3a2a27;">{_fmt(price)}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #EAE0DC;text-align:right;font-family:Arial,sans-serif;font-size:13px;font-weight:bold;color:#3a2a27;">{_fmt(qty*price)}</td>
        </tr>"""

    envio_row = ""
    if envio_val:
        envio_row = f"""
        <tr>
          <td colspan="3" style="padding:8px 12px;text-align:right;font-family:Arial,sans-serif;font-size:12px;color:#9a7a74;">Envío</td>
          <td style="padding:8px 12px;text-align:right;font-family:Arial,sans-serif;font-size:12px;color:#3a2a27;">{_fmt(envio_val)}</td>
        </tr>"""

    client_rows = ""
    for label, key in [("Contacto","nombre"),("Empresa","empresa"),("Celular","telefono"),("Correo","email")]:
        val = cliente.get(key, "")
        if val:
            client_rows += f'<tr><td style="font-size:10px;color:#9a7a74;text-transform:uppercase;letter-spacing:0.06em;padding:3px 0;width:70px;">{label}</td><td style="font-size:13px;color:#3a2a27;padding:3px 0;">{val}</td></tr>'

    notes_block = ""
    if notas:
        notes_block = f"""
  <tr>
    <td style="padding:10px 32px;">
      <div style="background:#FBF5F3;border-left:3px solid #C07082;border-radius:0 6px 6px 0;padding:10px 14px;">
        <div style="font-size:9px;color:#C07082;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:6px;">Notas y observaciones</div>
        <div style="font-size:12px;color:#3a2a27;line-height:1.6;">{notas}</div>
      </div>
    </td>
  </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f5efe9;font-family:Arial,sans-serif;">
<table width="620" cellpadding="0" cellspacing="0" style="margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr>
    <td style="background:#C07082;padding:24px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td>
          <div style="font-family:Georgia,serif;font-size:22px;color:white;letter-spacing:0.05em;">Bosque y Cielo</div>
          <div style="font-size:10px;color:rgba(255,255,255,0.8);letter-spacing:0.15em;text-transform:uppercase;margin-top:3px;">Cerámica artesanal</div>
        </td>
        <td style="text-align:right;font-size:11px;color:rgba(255,255,255,0.85);line-height:1.7;">
          www.bosqueycielo.com<br>
          KR 34 # 5B-61 LC 103 · Cali, Valle<br>
          Cel: 310 492 5416 &nbsp;·&nbsp; NIT: 901.481.694-2
        </td>
      </tr></table>
    </td>
  </tr>

  <!-- Title bar -->
  <tr>
    <td style="background:#F0E8E5;padding:16px 32px;border-bottom:3px solid #C07082;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="font-family:Georgia,serif;font-size:24px;font-weight:600;color:#3a2a27;">Cotización</td>
        <td style="text-align:right;">
          <table cellpadding="0" cellspacing="4"><tr>
            <td style="padding-left:24px;text-align:right;">
              <div style="font-size:9px;color:#9a7a74;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">N° cotización</div>
              <div style="font-size:13px;font-weight:700;color:#C07082;">{numero}</div>
            </td>
            <td style="padding-left:24px;text-align:right;">
              <div style="font-size:9px;color:#9a7a74;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">Fecha</div>
              <div style="font-size:12px;color:#3a2a27;">{fecha}</div>
            </td>
          </tr></table>
        </td>
      </tr></table>
    </td>
  </tr>

  <!-- Client + Conditions -->
  <tr>
    <td style="padding:20px 32px 10px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr valign="top">
        <td width="48%" style="border:1px solid #EAE0DC;border-radius:8px;padding:12px 16px;">
          <div style="font-family:Georgia,serif;font-size:12px;font-weight:600;color:#C07082;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px;">Cliente</div>
          <table cellpadding="0" cellspacing="0">{client_rows}</table>
        </td>
        <td width="4%"></td>
        <td width="48%" style="border:1px solid #EAE0DC;border-radius:8px;padding:12px 16px;">
          <div style="font-family:Georgia,serif;font-size:12px;font-weight:600;color:#C07082;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px;">Condiciones</div>
          <div style="font-size:10px;color:#9a7a74;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Condiciones de pago</div>
          <div style="font-size:12px;color:#3a2a27;margin-bottom:12px;">{condiciones}</div>
          <div style="font-size:10px;color:#9a7a74;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Plazo de entrega</div>
          <div style="font-size:12px;color:#3a2a27;">{plazo}</div>
        </td>
      </tr></table>
    </td>
  </tr>

  <!-- Products -->
  <tr>
    <td style="padding:10px 32px;">
      <div style="font-family:Georgia,serif;font-size:15px;font-weight:600;color:#3a2a27;margin-bottom:10px;">Productos cotizados</div>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:6px;overflow:hidden;">
        <tr style="background:#C07082;color:white;">
          <td style="padding:8px 12px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;">Producto / Descripción</td>
          <td style="padding:8px 12px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;text-align:center;">Cant.</td>
          <td style="padding:8px 12px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;text-align:right;">P. Unitario</td>
          <td style="padding:8px 12px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;text-align:right;">Total</td>
        </tr>
        {rows}
        {envio_row}
        <tr style="background:#C07082;color:white;">
          <td colspan="3" style="padding:12px;font-family:Georgia,serif;font-size:15px;font-weight:600;">TOTAL</td>
          <td style="padding:12px;font-family:Georgia,serif;font-size:17px;font-weight:600;text-align:right;">{_fmt(total)}</td>
        </tr>
      </table>
    </td>
  </tr>

  {notes_block}

  <!-- Footer -->
  <tr>
    <td style="padding:16px 32px 24px;border-top:1px solid #EAE0DC;">
      <div style="font-family:Georgia,serif;font-size:12px;color:#C07082;font-style:italic;margin-bottom:4px;">Cada pieza es única, hecha a mano con amor.</div>
      <div style="font-size:11px;color:#9a7a74;line-height:1.6;">
        Los precios están expresados en pesos colombianos (COP).<br>
        Para confirmar o resolver dudas: hola@bosqueycielo.com · 310 492 5416
      </div>
    </td>
  </tr>

</table>
</body>
</html>"""


def generar_html_cotizacion_pottery(datos: dict) -> str:
    """Genera HTML de cotización Pottery Lab (experiencias/talleres)."""
    cliente    = datos.get("cliente", {})
    taller     = datos.get("taller", {})
    notas      = datos.get("notas", "")
    condiciones = datos.get("condiciones_pago", "50% anticipo para confirmar la reserva · 50% restante el día del taller")
    inclusiones = datos.get("inclusiones", "Materiales · piezas en bizcocho listas · horneada · entrega de piezas terminadas aprox. 2 semanas después")
    numero     = datos.get("numero") or f"PL-{str(__import__('time').time_ns())[-6:]}"
    fecha      = datos.get("fecha", "")

    participantes  = int(taller.get("participantes", 1))
    precio_persona = int(float(taller.get("precio_por_persona", 0)))
    total          = participantes * precio_persona
    anticipo       = total // 2

    client_rows = ""
    for label, key in [("Contacto","nombre"),("Empresa","empresa"),("Celular","telefono"),("Correo","email")]:
        val = cliente.get(key, "")
        if val:
            client_rows += f'<tr><td style="font-size:10px;color:#7A6E64;text-transform:uppercase;letter-spacing:0.06em;padding:3px 0;min-width:70px;">{label}</td><td style="font-size:13px;color:#3D332C;padding:3px 0;">{val}</td></tr>'

    taller_rows = ""
    for label, key in [
        ("Tipo de evento","tipo"), ("Ejercicio","ejercicio"), ("Lugar","lugar"),
        ("Fecha del taller","fecha_taller"), ("Duración","duracion"),
    ]:
        val = taller.get(key, "")
        if val:
            taller_rows += f'<tr><td style="font-size:10px;color:#7A6E64;text-transform:uppercase;letter-spacing:0.06em;padding:4px 0;min-width:100px;">{label}</td><td style="font-size:13px;color:#3D332C;padding:4px 0;">{val}</td></tr>'

    notes_block = ""
    if notas:
        notes_block = f"""
  <tr>
    <td style="padding:10px 32px;">
      <div style="background:#EFE8DD;border-left:3px solid #A89A8D;border-radius:0 6px 6px 0;padding:10px 14px;">
        <div style="font-size:9px;color:#8E8275;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:6px;">Notas y observaciones</div>
        <div style="font-size:12px;color:#3D332C;line-height:1.6;">{notas}</div>
      </div>
    </td>
  </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#C5BDB5;font-family:Arial,sans-serif;">
<table width="620" cellpadding="0" cellspacing="0" style="margin:0 auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.10);">

  <!-- Header -->
  <tr>
    <td style="background:#8E8275;padding:24px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td>
          <div style="font-family:Arial,sans-serif;font-size:13px;color:#F5F0E8;letter-spacing:0.2em;text-transform:uppercase;font-weight:700;">POTTERY LAB</div>
          <div style="font-family:Georgia,serif;font-size:18px;color:#F5F0E8;font-style:italic;margin-top:2px;">Bosque &amp; Cielo</div>
        </td>
        <td style="text-align:right;font-size:11px;color:rgba(245,240,232,0.85);line-height:1.7;">
          www.bosqueycielo.com<br>
          Cel: 310 492 5416 &nbsp;·&nbsp; NIT: 901.481.694-2
        </td>
      </tr></table>
    </td>
  </tr>

  <!-- Title bar -->
  <tr>
    <td style="background:#F5F0E8;padding:16px 32px;border-bottom:3px solid #A89A8D;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="font-family:Georgia,serif;font-size:22px;font-weight:600;color:#3D332C;">Cotización</td>
        <td style="text-align:right;">
          <table cellpadding="0" cellspacing="4"><tr>
            <td style="padding-left:24px;text-align:right;">
              <div style="font-size:9px;color:#7A6E64;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">N° cotización</div>
              <div style="font-size:13px;font-weight:700;color:#8E8275;">{numero}</div>
            </td>
            <td style="padding-left:24px;text-align:right;">
              <div style="font-size:9px;color:#7A6E64;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px;">Fecha</div>
              <div style="font-size:12px;color:#3D332C;">{fecha}</div>
            </td>
          </tr></table>
        </td>
      </tr></table>
    </td>
  </tr>

  <!-- Client + Workshop details -->
  <tr>
    <td style="padding:20px 32px 10px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr valign="top">
        <td width="48%" style="border:1px solid #DDD5CC;border-radius:8px;padding:12px 16px;">
          <div style="font-family:Georgia,serif;font-size:12px;font-weight:600;color:#8E8275;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px;">Cliente</div>
          <table cellpadding="0" cellspacing="0">{client_rows}</table>
        </td>
        <td width="4%"></td>
        <td width="48%" style="border:1px solid #DDD5CC;border-radius:8px;padding:12px 16px;">
          <div style="font-family:Georgia,serif;font-size:12px;font-weight:600;color:#8E8275;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:10px;">Detalle del taller</div>
          <table cellpadding="0" cellspacing="0">{taller_rows}</table>
        </td>
      </tr></table>
    </td>
  </tr>

  <!-- Pricing block -->
  <tr>
    <td style="padding:10px 32px;">
      <div style="font-family:Georgia,serif;font-size:15px;font-weight:600;color:#3D332C;margin-bottom:10px;">Inversión</div>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:6px;overflow:hidden;">
        <tr style="background:#8E8275;color:#F5F0E8;">
          <td style="padding:8px 16px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;">Concepto</td>
          <td style="padding:8px 16px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;text-align:center;">Participantes</td>
          <td style="padding:8px 16px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;text-align:right;">P. por persona</td>
          <td style="padding:8px 16px;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;text-align:right;">Total</td>
        </tr>
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #DDD5CC;font-family:Arial,sans-serif;font-size:13px;color:#3D332C;">
            <strong>{taller.get('tipo','Taller')}</strong>
            {f"<br><span style='color:#7A6E64;font-size:11px'>{taller['ejercicio']}</span>" if taller.get('ejercicio') else ''}
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #DDD5CC;text-align:center;font-size:13px;color:#3D332C;">{participantes}</td>
          <td style="padding:12px 16px;border-bottom:1px solid #DDD5CC;text-align:right;font-size:13px;color:#3D332C;">{_fmt(precio_persona)}</td>
          <td style="padding:12px 16px;border-bottom:1px solid #DDD5CC;text-align:right;font-size:13px;font-weight:bold;color:#3D332C;">{_fmt(total)}</td>
        </tr>
        <tr style="background:#EFE8DD;">
          <td colspan="3" style="padding:8px 16px;font-size:12px;color:#7A6E64;font-style:italic;">Anticipo para reservar (50%)</td>
          <td style="padding:8px 16px;text-align:right;font-size:13px;color:#8E8275;font-weight:bold;">{_fmt(anticipo)}</td>
        </tr>
        <tr style="background:#8E8275;color:#F5F0E8;">
          <td colspan="3" style="padding:12px 16px;font-family:Georgia,serif;font-size:15px;font-weight:600;">TOTAL</td>
          <td style="padding:12px 16px;font-family:Georgia,serif;font-size:17px;font-weight:600;text-align:right;">{_fmt(total)}</td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Inclusions + Conditions -->
  <tr>
    <td style="padding:10px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr valign="top">
        <td width="48%" style="border:1px solid #DDD5CC;border-radius:8px;padding:12px 16px;">
          <div style="font-size:9px;color:#8E8275;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:6px;">Incluye</div>
          <div style="font-size:12px;color:#3D332C;line-height:1.7;">{inclusiones}</div>
        </td>
        <td width="4%"></td>
        <td width="48%" style="border:1px solid #DDD5CC;border-radius:8px;padding:12px 16px;">
          <div style="font-size:9px;color:#8E8275;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:6px;">Condiciones de pago</div>
          <div style="font-size:12px;color:#3D332C;line-height:1.7;">{condiciones}</div>
        </td>
      </tr></table>
    </td>
  </tr>

  {notes_block}

  <!-- Footer -->
  <tr>
    <td style="padding:16px 32px 24px;border-top:1px solid #DDD5CC;">
      <div style="font-family:Georgia,serif;font-size:12px;color:#A89A8D;font-style:italic;margin-bottom:4px;">Cada taller es una experiencia única, hecha con amor.</div>
      <div style="font-size:11px;color:#7A6E64;line-height:1.6;">
        Los precios están expresados en pesos colombianos (COP).<br>
        Para confirmar o resolver dudas: hola@bosqueycielo.com · 310 492 5416
      </div>
    </td>
  </tr>

</table>
</body>
</html>"""


def enviar_cotizacion_pottery(datos: dict) -> str:
    """Envía cotización Pottery Lab (experiencias) por email."""
    if not SMTP_PASS:
        return "Error: SMTP_PASS no configurado en .env"

    cliente  = datos.get("cliente", {})
    to_email = cliente.get("email", "").strip()
    if not to_email:
        return "Error: falta el correo del cliente."

    numero = datos.get("numero") or f"PL-{str(__import__('time').time_ns())[-6:]}"
    datos["numero"] = numero

    taller  = datos.get("taller", {})
    total   = int(taller.get("participantes", 1)) * int(float(taller.get("precio_por_persona", 0)))
    empresa = cliente.get("empresa") or cliente.get("nombre", "")
    asunto  = f"Cotización Pottery Lab — {empresa} ({numero})"

    result = _send(to_email, asunto, generar_html_cotizacion_pottery(datos))
    if result.startswith("Error"):
        return result
    return f"✅ Cotización Pottery Lab {numero} enviada a {to_email} · Total: {_fmt(total)}"


def enviar_cotizacion(datos: dict) -> str:
    """Envía cotización Bosque y Cielo (productos) por email via Resend."""
    cliente  = datos.get("cliente", {})
    to_email = cliente.get("email", "").strip()
    if not to_email:
        return "Error: falta el correo del cliente."

    numero = datos.get("numero") or _numero()
    datos["numero"] = numero

    productos = datos.get("productos", [])
    total = sum(
        int(float(p.get("precio_unitario", 0))) * int(p.get("cantidad", 1))
        for p in productos
    ) + int(float(datos.get("envio", 0) or 0))
    empresa = cliente.get("empresa") or cliente.get("nombre", "")
    asunto  = f"Cotización Bosque y Cielo — {empresa} ({numero})"

    result = _send(to_email, asunto, generar_html_cotizacion(datos))
    if result.startswith("Error"):
        return result
    return f"✅ Cotización {numero} enviada a {to_email} · Total: {_fmt(total)}"
