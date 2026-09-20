# Directiva: Registrar Ingresos y Egresos

## Spreadsheet ID
`1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE`

## Pestañas y columnas

### INGRESOS

| Pestaña | Columnas (en orden) |
|---|---|
| `Shop` | No.Factura · Fecha · Cliente · SKU · Cantidad · Valor unitario · Valor×cant · Valor IVA · Valor Total |
| `Studio Amphora` | No.Factura · Fecha · Cliente · Cantidad · Valor unitario · Valor IVA · Valor Total |
| `Pottery Lab ` *(espacio)* | No.Factura · Fecha · Cliente · Cantidad · Valor unitario · Valor IVA · Valor Total |
| `Ceramikids` | No.Factura · Fecha · Cliente · Cantidad · Valor unitario · Valor IVA · Valor Total |
| `Ecommerce` | No.Factura · Fecha · Cliente · SKU · Cantidad · Valor unitario · Valor×cant · Valor Envío · Valor Total |
| `B2B` | Leer cabecera antes de escribir |
| `Personalización` | Leer cabecera antes de escribir |

### EGRESOS

| Pestaña | Uso |
|---|---|
| `Materia Prima` | Arcilla, esmaltes, insumos — leer fila 1 para columnas exactas |
| `Mano de Obra` | Pagos a Daniela, Jessica, Andrea, Don Jair |
| `Gastos Operativos` | Marketing, envíos, arriendo, servicios, eventos |

## Clasificación por palabras clave

| Si el usuario dice | → Pestaña |
|---|---|
| "vendí en la tienda" / "Bold" / "caja" | Shop |
| "mensualidad" / "pagó el taller" / "amphora" | Studio Amphora |
| "Pottery Lab" / "taller adultos" | Pottery Lab  |
| "Ceramikids" / "niños" | Ceramikids |
| "Shopify" / "online" / "ecommerce" | Ecommerce |
| "personalizado" / "pedido" | Personalización |
| "empresa" / "B2B" | B2B |
| "arcilla" / "esmalte" / "insumo" | Materia Prima |
| "pagué a [nombre]" / "honorarios" | Mano de Obra |
| "marketing" / "envío" / "arriendo" / otros | Gastos Operativos |

## Métodos de pago reconocidos
- **Bold** → terminal POS en tienda física (Shop)
- **Efectivo** → caja (Shop o Studio Amphora)
- **Transferencia** → mensualidades Studio, mano de obra

## Flujo de registro
1. Clasificar según palabras clave → elegir pestaña
2. Rellenar campos con datos del usuario
3. Fecha de hoy si no la especificó (DD/MM/AAAA)
4. Números sin $, sin puntos, sin comas: `736500` no `$736.500`
5. Llamar `agregar_fila` con valores en el orden exacto de las columnas
6. Confirmar con resumen: qué · cuánto · dónde

## Convenciones de estado
- `OK` / `OK Pagado` → confirmado
- `Pagado $X` → pago parcial
- vacío → pendiente
- `ANULADO` → cancelar un registro erróneo

## La dimensión que falta: el pedido (2026-09-20)

Todas las pestañas de arriba organizan la plata por **línea de negocio** (Shop, B2B,
Pottery Lab…) o por **categoría de gasto** (Materia Prima, Mano de Obra…). Ninguna guarda
a qué pedido pertenece, así que con ellas solas es imposible responder *"¿cuánto me dejó
realmente el pedido de Camilo Rojas?"*.

Por eso existe la pestaña **`Movimientos`** en *Ventas y Costos B&C* (`execution/movimientos.py`):
Fecha · Tipo · **Pedido** · Categoría · Concepto · Monto · Forma de pago · Pestaña PNL · Notas

- `registrar_movimiento` — solo para plata atribuible a un pedido. Arriendo, servicios y
  nómina del mes **no** van acá: siguen su camino de siempre.
- `leer_movimientos(pedido)` — cobrado, gastado, neto, y el contraste contra lo cotizado.

**Ojo con el doble registro.** Un movimiento de pedido normalmente pertenece a los dos
sitios: acá (para el margen del pedido) y en su pestaña del PNL (para el mes). La columna
*Pestaña PNL* deja la traza de que ya se hizo. Unificarlo de verdad — que un solo registro
alimente ambas vistas — exigiría agregarle una columna Pedido a las diez pestañas de
ingresos y egresos, que hoy tienen cabeceras distintas entre sí. Está sin decidir.

**Para qué sirve el contraste.** `leer_movimientos` compara el gasto real contra el total
cotizado. Si el margen real sale muy por debajo del que prometía la cotización, el
cotizador tiene costos que no está viendo — y eso es lo que hay que corregir en los
parámetros, no en el precio.
