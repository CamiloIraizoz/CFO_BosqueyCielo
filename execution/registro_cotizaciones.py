"""El registro de cotizaciones que sí funciona hoy.

Una cotización tiene que quedar en tres sitios y cada uno sirve para algo
distinto:

  1. *Ventas y Costos B&C* → pestaña `Cotizaciones`: una fila por cotización.
     Es el registro de operación — cuántas se hicieron, por cuánto, en qué
     quedaron. **Este es el único que no depende de permisos pendientes.**
  2. HubSpot → contacto, negocio y ticket. Es el seguimiento comercial.
  3. *Cotizador Interno* → el desglose completo, fórmula por fórmula.
     Hoy bloqueado por permisos; cuando se comparta la hoja, entra solo.

Lo importante es que un fallo en cualquiera de los tres NO impida los otros
dos: antes, el 403 del Cotizador Interno dejaba la cotización sin registrar
en ningún lado.
"""

from datetime import datetime

from sheets import agregar_fila, crear_pestana, escribir_rango, leer_sheet_numericos

PESTANA = "Cotizaciones"
CABECERA = ["Número", "Fecha", "Tipo", "Cliente", "Empresa", "Contacto",
            "Piezas", "Total", "Estado", "Negocio HS", "Ticket HS", "Notas"]


def _asegurar_pestana():
    if leer_sheet_numericos(f"'{PESTANA}'!A1:L1"):
        return ""
    r = crear_pestana(PESTANA)
    if str(r).startswith(("Error", "❌")):
        return str(r)
    escribir_rango(f"'{PESTANA}'!A1:L1", [CABECERA])
    return ""


def ya_registrada(numero):
    """Evita filas repetidas si se pega la misma cotización dos veces."""
    for f in leer_sheet_numericos(f"'{PESTANA}'!A2:A500"):
        if f and str(f[0]).strip() == str(numero).strip():
            return True
    return False


def guardar_fila(numero, cliente="", empresa="", contacto="", tipo="producto",
                 piezas=0, total=0, fecha="", notas="", deal_id="", ticket_id="",
                 estado="enviada"):
    fallo = _asegurar_pestana()
    if fallo:
        return "⚠️ No pude crear la pestaña Cotizaciones: " + fallo
    if ya_registrada(numero):
        return f"↩️ {numero} ya estaba en la pestaña Cotizaciones (no la dupliqué)."
    fila = [numero, fecha or datetime.now().strftime("%d/%m/%Y"), tipo, cliente,
            empresa, contacto, int(piezas or 0), int(total or 0), estado,
            deal_id, ticket_id, notas]
    r = agregar_fila(f"'{PESTANA}'!A:L", fila)
    if str(r).startswith(("Error", "❌")):
        return "⚠️ No quedó en la pestaña Cotizaciones: " + str(r).replace("Error: ", "", 1)
    return f"✅ Registrada en la pestaña Cotizaciones de Ventas y Costos B&C."


def leer(cliente="", limite=15):
    filas = [f for f in leer_sheet_numericos(f"'{PESTANA}'!A2:L500") if f and len(f) >= 8]
    if cliente:
        filas = [f for f in filas
                 if cliente.strip().lower() in f"{f[3]} {f[4]}".strip().lower()]
    if not filas:
        cual = f" de {cliente}" if cliente else ""
        return f"No hay cotizaciones registradas{cual}."
    filas = filas[-int(limite):]
    lineas = ["*Cotizaciones registradas*", ""]
    for f in reversed(filas):
        total = f"${int(f[7]):,}".replace(",", ".") if str(f[7]).strip() else "—"
        quien = str(f[4]).strip() or str(f[3]).strip()
        lineas.append(f"· {f[0]} · {f[1]} · {quien} · {total} · {f[8]}")
    return "\n".join(lineas)


def marcar_estado(numero, estado):
    """aceptada · perdida · vencida — para saber cuántas se cierran."""
    from sheets import actualizar_celda
    for i, f in enumerate(leer_sheet_numericos(f"'{PESTANA}'!A2:L500"), start=2):
        if f and str(f[0]).strip() == str(numero).strip():
            r = actualizar_celda(f"'{PESTANA}'!I{i}", estado)
            if str(r).startswith(("Error", "❌")):
                return str(r)
            return f"✅ {numero} quedó como '{estado}'."
    return f"No encontré la cotización {numero} en el registro."
