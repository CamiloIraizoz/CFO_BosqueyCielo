#!/usr/bin/env python3
"""
Generación de cotizaciones en PDF (Bosque y Cielo / Pottery Lab).

Usa xhtml2pdf (puro Python, sin dependencias de sistema). El HTML de este módulo
NO es el mismo de email_sender.py: xhtml2pdf no soporta tablas anidadas con
padding ni border-radius, así que aquí se usa un layout plano de tablas simples.
"""
import io

BYC_ROSA   = "#C07082"
BYC_CREMA  = "#F0E8E5"
BYC_TEXTO  = "#3a2a27"
BYC_SUAVE  = "#9a7a74"
BYC_LINEA  = "#EAE0DC"

PL_BARRO   = "#8E8275"
PL_ARENA   = "#F5F0E8"
PL_TEXTO   = "#3D332C"
PL_SUAVE   = "#7A6E64"
PL_LINEA   = "#DDD5CC"


def _fmt(value) -> str:
    try:
        return f"${int(float(value)):,}".replace(",", ".")
    except Exception:
        return str(value)


def _esc(texto) -> str:
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _base_css(acento: str, crema: str, texto: str, suave: str, linea: str) -> str:
    return f"""
    @page {{
      size: a4 portrait;
      margin: 1.4cm 1.5cm 1.8cm 1.5cm;
      @frame footer {{
        -pdf-frame-content: pie_pagina;
        bottom: 0.7cm; left: 1.5cm; width: 18cm; height: 1cm;
      }}
    }}
    body  {{ font-family: Helvetica; font-size: 9pt; color: {texto}; }}
    .cab           {{ background-color: {acento}; color: white; padding: 12pt 14pt; }}
    .marca         {{ font-size: 17pt; }}
    .marca-sub     {{ font-size: 7pt; color: #F3E3E6; }}
    .cab-datos     {{ font-size: 7.5pt; color: #F3E3E6; text-align: right; }}
    .barra         {{ background-color: {crema}; padding: 9pt 14pt; }}
    .titulo        {{ font-size: 16pt; color: {texto}; }}
    .meta-label    {{ font-size: 6.5pt; color: {suave}; text-align: right; }}
    .meta-valor    {{ font-size: 9pt; color: {acento}; text-align: right; }}
    .caja          {{ border: 1px solid {linea}; padding: 8pt 10pt; }}
    .caja-titulo   {{ font-size: 8pt; color: {acento}; padding-bottom: 5pt; }}
    .campo         {{ padding: 1.5pt 0; }}
    .campo-label   {{ font-size: 6.5pt; color: {suave}; padding: 1pt 0; }}
    .campo-valor   {{ font-size: 8.5pt; color: {texto}; padding: 1pt 0; }}
    .seccion       {{ font-size: 11pt; color: {texto}; padding: 12pt 0 5pt 0; }}
    .th            {{ background-color: {acento}; color: white; font-size: 7pt; padding: 6pt 8pt; }}
    .td            {{ font-size: 8.5pt; padding: 6pt 8pt; border-bottom: 1px solid {linea}; }}
    .td-desc       {{ font-size: 7.5pt; color: {suave}; }}
    .total-fila    {{ background-color: {acento}; color: white; font-size: 11pt; padding: 8pt; }}
    .nota          {{ background-color: {crema}; padding: 8pt 10pt; font-size: 8pt; }}
    .nota-titulo   {{ font-size: 6.5pt; color: {acento}; padding-bottom: 3pt; }}
    .pie           {{ font-size: 7pt; color: {suave}; text-align: center; }}
    .der           {{ text-align: right; }}
    .cen           {{ text-align: center; }}
    """


def _cabecera(acento, crema, texto, suave, marca_html, contacto_html, numero, fecha) -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr valign="top"><td class="cab" width="55%">{marca_html}</td>
          <td class="cab cab-datos" width="45%">{contacto_html}</td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr valign="top">
        <td class="barra titulo" width="55%">Cotización</td>
        <td class="barra meta-label" width="23%">N° COTIZACIÓN<br/>
            <span class="meta-valor">{_esc(numero)}</span></td>
        <td class="barra meta-label" width="22%">FECHA<br/>
            <span class="meta-valor">{_esc(fecha)}</span></td>
      </tr>
    </table>
    """


def _campos(titulo: str, pares: list) -> str:
    """Caja de label/valor apilados. Sin tablas anidadas: xhtml2pdf las desalinea."""
    bloque = f'<div class="caja-titulo">{titulo}</div>'
    vacio = True
    for label, val in pares:
        if val:
            vacio = False
            bloque += (f'<div class="campo"><span class="campo-label">{label.upper()}</span>'
                       f'&nbsp; <span class="campo-valor">{_esc(val)}</span></div>')
    if vacio:
        bloque += '<div class="campo-valor">Sin datos</div>'
    return bloque


def _bloque_cliente(cliente: dict) -> str:
    return _campos("CLIENTE", [
        ("Contacto", cliente.get("nombre", "")),
        ("Empresa",  cliente.get("empresa", "")),
        ("Celular",  cliente.get("telefono", "")),
        ("Correo",   cliente.get("email", "")),
    ])


def _pie(acento, frase, correo_pie) -> str:
    return f"""
    <div id="pie_pagina" class="pie">
      <i>{frase}</i><br/>
      Precios en pesos colombianos (COP) · {correo_pie} · 310 492 5416 · NIT 901.481.694-2
    </div>
    """


def _html_a_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    salida = io.BytesIO()
    resultado = pisa.CreatePDF(io.StringIO(html), dest=salida, encoding="utf-8")
    if resultado.err:
        raise RuntimeError(f"xhtml2pdf falló con {resultado.err} errores")
    return salida.getvalue()


# ── Cotización PRODUCTOS (Bosque y Cielo) ────────────────────────────────────

def generar_html_pdf_cotizacion(datos: dict) -> str:
    cliente     = datos.get("cliente", {})
    productos   = datos.get("productos", [])
    envio_val   = int(float(datos.get("envio", 0) or 0))
    notas       = datos.get("notas", "")
    plazo       = datos.get("plazo_entrega", "4-6 semanas hábiles")
    condiciones = datos.get("condiciones_pago", "50% anticipo · 50% contra entrega")
    numero      = datos.get("numero", "")
    fecha       = datos.get("fecha", "")

    subtotal = sum(int(float(p.get("precio_unitario", 0))) * int(p.get("cantidad", 1))
                   for p in productos)
    total = subtotal + envio_val

    filas = ""
    for p in productos:
        qty  = int(p.get("cantidad", 1))
        pre  = int(float(p.get("precio_unitario", 0)))
        desc = (f'<br/><span class="td-desc">{_esc(p["descripcion"])}</span>'
                if p.get("descripcion") else "")
        filas += f"""
        <tr>
          <td class="td" width="52%"><b>{_esc(p.get('nombre',''))}</b>{desc}</td>
          <td class="td cen" width="10%">{qty}</td>
          <td class="td der" width="19%">{_fmt(pre)}</td>
          <td class="td der" width="19%"><b>{_fmt(qty*pre)}</b></td>
        </tr>"""

    if envio_val:
        filas += f"""
        <tr>
          <td class="td der" colspan="3">Envío</td>
          <td class="td der">{_fmt(envio_val)}</td>
        </tr>"""

    bloque_notas = ""
    if notas:
        bloque_notas = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:10pt">
          <tr><td class="nota">
            <div class="nota-titulo">NOTAS Y OBSERVACIONES</div>{_esc(notas)}
          </td></tr>
        </table>"""

    marca = ('<div class="marca">Bosque y Cielo'
             '<br/><span class="marca-sub">CERÁMICA ARTESANAL</span></div>')
    contacto = ('www.bosqueycielo.com<br/>KR 34 # 5B-61 LC 103 · Cali, Valle<br/>'
                'Cel: 310 492 5416 · NIT: 901.481.694-2')

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{_base_css(BYC_ROSA, BYC_CREMA, BYC_TEXTO, BYC_SUAVE, BYC_LINEA)}</style>
</head><body>

{_cabecera(BYC_ROSA, BYC_CREMA, BYC_TEXTO, BYC_SUAVE, marca, contacto, numero, fecha)}

<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12pt">
  <tr valign="top">
    <td width="49%" class="caja">{_bloque_cliente(cliente)}</td>
    <td width="2%"></td>
    <td width="49%" class="caja">
      <div class="caja-titulo">CONDICIONES</div>
      <div class="campo-label">CONDICIONES DE PAGO</div>
      <div class="campo-valor">{_esc(condiciones)}</div>
      <div class="campo-label" style="padding-top:6pt">PLAZO DE ENTREGA</div>
      <div class="campo-valor">{_esc(plazo)}</div>
    </td>
  </tr>
</table>

<div class="seccion">Productos cotizados</div>
<table width="100%" cellpadding="0" cellspacing="0" repeat="1">
  <tr>
    <td class="th" width="52%">PRODUCTO / DESCRIPCIÓN</td>
    <td class="th cen" width="10%">CANT.</td>
    <td class="th der" width="19%">P. UNITARIO</td>
    <td class="th der" width="19%">TOTAL</td>
  </tr>
  {filas}
  <tr>
    <td class="total-fila" colspan="3">TOTAL</td>
    <td class="total-fila der">{_fmt(total)}</td>
  </tr>
</table>

{bloque_notas}
{_pie(BYC_ROSA, "Cada pieza es única, hecha a mano con amor.", "hola@bosqueycielo.com")}
</body></html>"""


def generar_pdf_cotizacion(datos: dict) -> bytes:
    return _html_a_pdf(generar_html_pdf_cotizacion(datos))


# ── Cotización EXPERIENCIAS (Pottery Lab) ────────────────────────────────────

def generar_html_pdf_pottery(datos: dict) -> str:
    cliente     = datos.get("cliente", {})
    taller      = datos.get("taller", {})
    notas       = datos.get("notas", "")
    condiciones = datos.get("condiciones_pago",
                            "50% anticipo para confirmar la reserva · 50% el día del taller")
    inclusiones = datos.get("inclusiones",
                            "Materiales · piezas en bizcocho listas · horneada · "
                            "entrega de piezas terminadas aprox. 2 semanas después")
    numero      = datos.get("numero", "")
    fecha       = datos.get("fecha", "")

    participantes  = int(taller.get("participantes", 1))
    precio_persona = int(float(taller.get("precio_por_persona", 0)))
    total          = participantes * precio_persona
    anticipo       = total // 2

    bloque_taller = _campos("DETALLE DEL TALLER", [
        ("Tipo de evento",   taller.get("tipo", "")),
        ("Ejercicio",        taller.get("ejercicio", "")),
        ("Lugar",            taller.get("lugar", "")),
        ("Fecha del taller", taller.get("fecha_taller", "")),
        ("Duración",         taller.get("duracion", "")),
    ])

    ejercicio = (f'<br/><span class="td-desc">{_esc(taller["ejercicio"])}</span>'
                 if taller.get("ejercicio") else "")

    bloque_notas = ""
    if notas:
        bloque_notas = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:10pt">
          <tr><td class="nota">
            <div class="nota-titulo">NOTAS Y OBSERVACIONES</div>{_esc(notas)}
          </td></tr>
        </table>"""

    marca = ('<div class="marca"><span class="marca-sub" style="font-size:8pt">POTTERY LAB</span>'
             '<br/>Bosque &amp; Cielo</div>')
    contacto = ('www.bosqueycielo.com<br/>Cel: 310 492 5416 · NIT: 901.481.694-2')

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{_base_css(PL_BARRO, PL_ARENA, PL_TEXTO, PL_SUAVE, PL_LINEA)}</style>
</head><body>

{_cabecera(PL_BARRO, PL_ARENA, PL_TEXTO, PL_SUAVE, marca, contacto, numero, fecha)}

<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12pt">
  <tr valign="top">
    <td width="49%" class="caja">{_bloque_cliente(cliente)}</td>
    <td width="2%"></td>
    <td width="49%" class="caja">{bloque_taller}</td>
  </tr>
</table>

<div class="seccion">Inversión</div>
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td class="th" width="46%">CONCEPTO</td>
    <td class="th cen" width="16%">PARTICIPANTES</td>
    <td class="th der" width="19%">P. POR PERSONA</td>
    <td class="th der" width="19%">TOTAL</td>
  </tr>
  <tr>
    <td class="td"><b>{_esc(taller.get('tipo','Taller'))}</b>{ejercicio}</td>
    <td class="td cen">{participantes}</td>
    <td class="td der">{_fmt(precio_persona)}</td>
    <td class="td der"><b>{_fmt(total)}</b></td>
  </tr>
  <tr>
    <td class="td" colspan="3" style="background-color:{PL_ARENA}">
      <i>Anticipo para reservar (50%)</i></td>
    <td class="td der" style="background-color:{PL_ARENA}"><b>{_fmt(anticipo)}</b></td>
  </tr>
  <tr>
    <td class="total-fila" colspan="3">TOTAL</td>
    <td class="total-fila der">{_fmt(total)}</td>
  </tr>
</table>

<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12pt">
  <tr valign="top">
    <td width="49%" class="caja">
      <div class="caja-titulo">INCLUYE</div>
      <div class="campo-valor">{_esc(inclusiones)}</div>
    </td>
    <td width="2%"></td>
    <td width="49%" class="caja">
      <div class="caja-titulo">CONDICIONES DE PAGO</div>
      <div class="campo-valor">{_esc(condiciones)}</div>
    </td>
  </tr>
</table>

{bloque_notas}
{_pie(PL_BARRO, "Cada taller es una experiencia única, hecha con amor.", "hola@bosqueycielo.com")}
</body></html>"""


def generar_pdf_pottery(datos: dict) -> bytes:
    return _html_a_pdf(generar_html_pdf_pottery(datos))
