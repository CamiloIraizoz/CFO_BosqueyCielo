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
