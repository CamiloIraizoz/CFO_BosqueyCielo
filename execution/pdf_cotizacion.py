#!/usr/bin/env python3
"""
Generación de cotizaciones en PDF (Bosque y Cielo / Pottery Lab).

Usa xhtml2pdf (puro Python, sin dependencias de sistema). El HTML de este módulo
NO es el mismo de email_sender.py: xhtml2pdf no soporta tablas anidadas con
padding ni border-radius.

Dos reglas que vienen de pelearse con el motor y conviene no romper:
  1. El contenido de cada celda va en UN SOLO bloque con <br/>. Si se ponen
     varios divs hermanos, xhtml2pdf los reparte verticalmente para llenar la
     celda y el texto queda flotando con huecos enormes.
  2. Las tablas no se anidan dentro de celdas: se desalinean.

Tipografías: solo las base de PDF. 'Times' hace de serif de marca (el email usa
Georgia) y 'Helvetica' del resto.
"""
import io

# Bosque y Cielo — productos
BYC = {
    "acento": "#C07082", "acento_suave": "#F6ECEF", "crema": "#F0E8E5",
    "texto": "#3a2a27", "suave": "#9a7a74", "linea": "#EAE0DC", "sobre_acento": "#FBEFF2",
}
# Pottery Lab — experiencias
PL = {
    "acento": "#8E8275", "acento_suave": "#EFE8DD", "crema": "#F5F0E8",
    "texto": "#3D332C", "suave": "#7A6E64", "linea": "#DDD5CC", "sobre_acento": "#F5F0E8",
}


def _fmt(value) -> str:
    try:
        return f"${int(float(value)):,}".replace(",", ".")
    except Exception:
        return str(value)


def _esc(texto) -> str:
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _css(p: dict) -> str:
    return f"""
    @page {{
      size: a4 portrait;
      margin: 1.5cm 1.6cm 2cm 1.6cm;
      @frame footer {{
        -pdf-frame-content: pie_pagina;
        bottom: 0.9cm; left: 1.6cm; width: 17.8cm; height: 1.2cm;
      }}
    }}
    body            {{ font-family: Helvetica; font-size: 9pt; color: {p['texto']}; }}

    /* Cabecera */
    .cab            {{ background-color: {p['acento']}; padding: 15pt 16pt;
                       vertical-align: top; }}
    .marca          {{ font-family: Times; font-size: 20pt; color: white; }}
    .marca-sub      {{ font-family: Helvetica; font-size: 7pt; color: {p['sobre_acento']}; }}
    .cab-datos      {{ font-size: 7.5pt; color: {p['sobre_acento']}; text-align: right;
                       line-height: 1.6; padding: 15pt 16pt; vertical-align: top;
                       background-color: {p['acento']}; }}

    /* Barra de título */
    .barra          {{ background-color: {p['crema']}; padding: 11pt 16pt;
                       vertical-align: top; }}
    .titulo         {{ font-family: Times; font-size: 18pt; color: {p['texto']}; }}
    .meta           {{ background-color: {p['crema']}; padding: 11pt 8pt; text-align: right;
                       font-size: 6.5pt; color: {p['suave']}; line-height: 1.5;
                       vertical-align: top; }}
    .meta-valor     {{ font-family: Helvetica; font-size: 9.5pt; color: {p['acento']}; }}

    /* Cajas de datos: un solo bloque por celda, ver docstring */
    .caja           {{ border: 1px solid {p['linea']}; padding: 11pt 13pt;
                       vertical-align: top; }}
    .caja-cuerpo    {{ line-height: 1.75; }}
    .caja-titulo    {{ font-family: Times; font-size: 9.5pt; color: {p['acento']}; }}
    .campo-label    {{ font-size: 6.5pt; color: {p['suave']}; }}
    .campo-valor    {{ font-size: 9pt; color: {p['texto']}; }}

    /* Tabla */
    .seccion        {{ font-family: Times; font-size: 12.5pt; color: {p['texto']};
                       padding: 16pt 0 6pt 0; }}
    .th             {{ background-color: {p['acento']}; color: white; font-size: 6.5pt;
                       padding: 7pt 10pt; }}
    .td             {{ font-size: 9pt; padding: 8pt 10pt; border-bottom: 1px solid {p['linea']};
                       line-height: 1.5; }}
    .td-desc        {{ font-size: 7.5pt; color: {p['suave']}; }}
    .td-extra       {{ font-size: 8.5pt; color: {p['suave']}; padding: 6pt 10pt;
                       border-bottom: 1px solid {p['linea']}; }}
    .anticipo       {{ background-color: {p['acento_suave']}; font-size: 8.5pt;
                       color: {p['texto']}; padding: 7pt 10pt; }}
    .total          {{ background-color: {p['acento']}; color: white; font-family: Times;
                       font-size: 13pt; padding: 11pt 10pt; }}

    /* Notas y pie */
    .nota           {{ background-color: {p['crema']}; padding: 10pt 13pt;
                       font-size: 8.5pt; line-height: 1.6; }}
    .nota-titulo    {{ font-size: 6.5pt; color: {p['acento']}; }}
    .pie            {{ font-size: 7pt; color: {p['suave']}; text-align: center; line-height: 1.7; }}
    .pie-frase      {{ font-family: Times; font-size: 8.5pt; color: {p['acento']}; }}
    .espacio        {{ height: 14pt; }}
    .espacio-corto  {{ height: 10pt; }}
    .der            {{ text-align: right; }}
    .cen            {{ text-align: center; }}
    """


def _caja(titulo: str, pares: list) -> str:
    """Caja de label/valor en UN bloque: evita el reparto vertical de xhtml2pdf."""
    lineas = [f'<span class="caja-titulo">{titulo}</span>', ""]
    llena = False
    for label, valor in pares:
        if not valor:
            continue
        llena = True
        etiqueta = f'<span class="campo-label">{label.upper()}</span>' if label else ""
        # Un valor largo en la misma línea que su etiqueta se parte feo: va debajo.
        separador = "<br/>" if len(str(valor)) > 24 else " &nbsp;"
        lineas.append(f'{etiqueta}{separador if etiqueta else ""}'
                      f'<span class="campo-valor">{_esc(valor)}</span>')
    if not llena:
        lineas.append('<span class="campo-valor">Sin datos</span>')
    return f'<div class="caja-cuerpo">{"<br/>".join(lineas)}</div>'


def _encabezado(p: dict, marca: str, sub: str, contacto: str, numero: str, fecha: str) -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td class="cab" width="52%">
          <div><span class="marca">{marca}</span><br/><span class="marca-sub">{sub}</span></div>
        </td>
        <td class="cab-datos" width="48%"><div>{contacto}</div></td>
      </tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td class="barra titulo" width="56%">Cotización</td>
        <td class="meta" width="26%">
          <div>N° COTIZACIÓN<br/><span class="meta-valor">{_esc(numero)}</span></div>
        </td>
        <td class="meta" width="18%">
          <div>FECHA<br/><span class="meta-valor">{_esc(fecha)}</span></div>
        </td>
      </tr>
    </table>
    """


def _pie(frase: str) -> str:
    return f"""
    <div id="pie_pagina" class="pie">
      <span class="pie-frase"><i>{frase}</i></span><br/>
      Precios en pesos colombianos (COP) · hola@bosqueycielo.com · 310 492 5416 · NIT 901.481.694-2
    </div>
    """


def _notas(p: dict, notas: str) -> str:
    if not notas:
        return ""
    return f"""
    <div class="espacio-corto"></div>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td class="nota">
        <div><span class="nota-titulo">NOTAS Y OBSERVACIONES</span><br/>{_esc(notas)}</div>
      </td></tr>
    </table>"""


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
    plazo       = datos.get("plazo_entrega", "4-6 semanas hábiles")
    condiciones = datos.get("condiciones_pago", "50% anticipo · 50% contra entrega")
    numero      = datos.get("numero", "")
    fecha       = datos.get("fecha", "")

    total = sum(int(float(p.get("precio_unitario", 0))) * int(p.get("cantidad", 1))
                for p in productos) + envio_val

    filas = ""
    for prod in productos:
        qty  = int(prod.get("cantidad", 1))
        pre  = int(float(prod.get("precio_unitario", 0)))
        desc = (f'<br/><span class="td-desc">{_esc(prod["descripcion"])}</span>'
                if prod.get("descripcion") else "")
        filas += f"""
        <tr>
          <td class="td" width="50%"><b>{_esc(prod.get('nombre',''))}</b>{desc}</td>
          <td class="td cen" width="10%">{qty}</td>
          <td class="td der" width="20%">{_fmt(pre)}</td>
          <td class="td der" width="20%"><b>{_fmt(qty*pre)}</b></td>
        </tr>"""

    if envio_val:
        filas += f"""
        <tr>
          <td class="td-extra der" colspan="3">Envío</td>
          <td class="td-extra der">{_fmt(envio_val)}</td>
        </tr>"""

    contacto = ("www.bosqueycielo.com<br/>KR 34 # 5B-61 LC 103 · Cali, Valle<br/>"
                "Cel: 310 492 5416 · NIT: 901.481.694-2")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_css(BYC)}</style></head><body>

{_encabezado(BYC, "Bosque y Cielo", "CERÁMICA ARTESANAL", contacto, numero, fecha)}

<div class="espacio"></div>
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="49%" class="caja">{_caja("Cliente", [
        ("Contacto", cliente.get("nombre", "")),
        ("Empresa",  cliente.get("empresa", "")),
        ("Celular",  cliente.get("telefono", "")),
        ("Correo",   cliente.get("email", "")),
    ])}</td>
    <td width="2%"></td>
    <td width="49%" class="caja">{_caja("Condiciones", [
        ("Condiciones de pago", condiciones),
        ("Plazo de entrega",    plazo),
    ])}</td>
  </tr>
</table>

<div class="seccion">Productos cotizados</div>
<table width="100%" cellpadding="0" cellspacing="0" repeat="1">
  <tr>
    <td class="th" width="50%">PRODUCTO / DESCRIPCIÓN</td>
    <td class="th cen" width="10%">CANT.</td>
    <td class="th der" width="20%">P. UNITARIO</td>
    <td class="th der" width="20%">TOTAL</td>
  </tr>
  {filas}
  <tr>
    <td class="total" colspan="3">TOTAL</td>
    <td class="total der">{_fmt(total)}</td>
  </tr>
</table>

{_notas(BYC, datos.get("notas", ""))}
{_pie("Cada pieza es única, hecha a mano con amor.")}
</body></html>"""


def generar_pdf_cotizacion(datos: dict) -> bytes:
    return _html_a_pdf(generar_html_pdf_cotizacion(datos))


# ── Cotización EXPERIENCIAS (Pottery Lab) ────────────────────────────────────

def generar_html_pdf_pottery(datos: dict) -> str:
    cliente     = datos.get("cliente", {})
    taller      = datos.get("taller", {})
    condiciones = datos.get("condiciones_pago",
                            "50% anticipo para confirmar la reserva · 50% el día del taller")
    inclusiones = datos.get("inclusiones",
                            "Materiales · piezas en bizcocho listas · horneada · "
                            "entrega de piezas terminadas aprox. 2 semanas después")
    numero = datos.get("numero", "")
    fecha  = datos.get("fecha", "")

    participantes  = int(taller.get("participantes", 1))
    precio_persona = int(float(taller.get("precio_por_persona", 0)))
    total          = participantes * precio_persona
    anticipo       = total // 2

    ejercicio = (f'<br/><span class="td-desc">{_esc(taller["ejercicio"])}</span>'
                 if taller.get("ejercicio") else "")
    contacto = "www.bosqueycielo.com<br/>Cali, Valle<br/>Cel: 310 492 5416 · NIT: 901.481.694-2"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_css(PL)}</style></head><body>

{_encabezado(PL, "Pottery Lab", "BOSQUE &amp; CIELO", contacto, numero, fecha)}

<div class="espacio"></div>
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="49%" class="caja">{_caja("Cliente", [
        ("Contacto", cliente.get("nombre", "")),
        ("Empresa",  cliente.get("empresa", "")),
        ("Celular",  cliente.get("telefono", "")),
        ("Correo",   cliente.get("email", "")),
    ])}</td>
    <td width="2%"></td>
    <td width="49%" class="caja">{_caja("Detalle del taller", [
        ("Tipo de evento",   taller.get("tipo", "")),
        ("Lugar",            taller.get("lugar", "")),
        ("Fecha del taller", taller.get("fecha_taller", "")),
        ("Duración",         taller.get("duracion", "")),
    ])}</td>
  </tr>
</table>

<div class="seccion">Inversión</div>
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td class="th" width="44%">CONCEPTO</td>
    <td class="th cen" width="16%">PARTICIPANTES</td>
    <td class="th der" width="20%">P. POR PERSONA</td>
    <td class="th der" width="20%">TOTAL</td>
  </tr>
  <tr>
    <td class="td"><b>{_esc(taller.get('tipo','Taller'))}</b>{ejercicio}</td>
    <td class="td cen">{participantes}</td>
    <td class="td der">{_fmt(precio_persona)}</td>
    <td class="td der"><b>{_fmt(total)}</b></td>
  </tr>
  <tr>
    <td class="anticipo" colspan="3"><i>Anticipo para reservar (50%)</i></td>
    <td class="anticipo der"><b>{_fmt(anticipo)}</b></td>
  </tr>
  <tr>
    <td class="total" colspan="3">TOTAL</td>
    <td class="total der">{_fmt(total)}</td>
  </tr>
</table>

<div class="espacio"></div>
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="49%" class="caja">{_caja("Incluye", [("", inclusiones)])}</td>
    <td width="2%"></td>
    <td width="49%" class="caja">{_caja("Condiciones de pago", [("", condiciones)])}</td>
  </tr>
</table>

{_notas(PL, datos.get("notas", ""))}
{_pie("Cada taller es una experiencia única, hecha con amor.")}
</body></html>"""


def generar_pdf_pottery(datos: dict) -> bytes:
    return _html_a_pdf(generar_html_pdf_pottery(datos))
