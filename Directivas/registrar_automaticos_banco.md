# Directiva: Registrar Cargos Automáticos del Banco

Proceso para agregar en bloque a Movimientos todos los cargos automáticos que genera Bancolombia cada mes.
Ejecutar durante la **Fase 2 (Conciliación bancaria)** del cierre de mes.

---

## ¿Qué son los cargos automáticos?

Movimientos que el banco genera sin intervención manual y que normalmente no se registran en el día a día:

| Tipo | Descripción banco | Categoría Movimientos | Tipo |
|------|-------------------|-----------------------|------|
| 4x1000 | `IMPTO GOBIERNO 4X1000` | Gastos Financieros | Egreso |
| Intereses ahorros | `ABONO INTERESES AHORROS` | Ingresos Financieros | Ingreso |
| Cuota manejo tarjeta | `C MANEJO TARJ DEB` | Gastos Financieros | Egreso |
| Fee Shopify | `COMPRA INTL Shopify` | Fee Shopify | Egreso |
| Pauta Meta/Facebook | `COMPRA INTL FACEBK` | Redes Sociales | Egreso |

---

## Pasos

### 1. Leer el extracto bancario del mes
Obtener todos los movimientos del PDF/CSV del banco.

### 2. Identificar los automáticos
Buscar en el extracto todas las líneas de los tipos listados arriba.

### 3. Verificar cuáles ya están en Movimientos
```bash
./execution/leer_rango.sh "Movimientos!A:I"
```
Filtrar por el mes y buscar cada tipo. Los 4x1000 del día a día normalmente ya están porque el bot los registra.

### 4. Agregar los que faltan en bloque

Formato de cada fila (columnas A a I de Movimientos):

```
Fecha (DD/MM/YYYY) | Mes | Año | Tipo | Categoría | Descripción | Cliente/Proveedor | Método de Pago | Monto
```

**Reglas de formato:**
- Monto siempre positivo (sin signo negativo, sin $)
- Para 4x1000: usar el monto exacto del extracto (ej: `9766.30`)
- Para intereses: agregar uno por día (monto exacto del extracto)
- Método de Pago: siempre `Transferencia` (son débitos/créditos bancarios)
- Cliente/Proveedor: `Bancolombia` para todos los cargos del banco

**Ejemplo de bloque Python para subir:**

```python
entries = [
    # 4x1000
    ["18/06/2026","Junio","2026","Egreso","Gastos Financieros","Impuesto 4x1000","Bancolombia","Transferencia","9766.30"],
    # Intereses
    ["18/06/2026","Junio","2026","Ingreso","Ingresos Financieros","Abono intereses ahorros","Bancolombia","Transferencia","17.70"],
    # Fee Shopify
    ["20/06/2026","Junio","2026","Egreso","Fee Shopify","Suscripción mensual Shopify","Shopify","Transferencia","86868.79"],
    # Facebook
    ["23/06/2026","Junio","2026","Egreso","Redes Sociales","Pauta publicitaria Facebook/Instagram","Meta - Facebook","Transferencia","20607.14"],
]

data = {
    "spreadsheetId": "SPREADSHEET_ID",
    "range": "Movimientos!A:J",
    "values": entries,
    "valueInputOption": "USER_ENTERED"
}
# Subir con: composio execute GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND -d @data.json
```

### 5. Verificar el total del mes
Después de subir, leer el Resumen del mes y confirmar que los totales cuadran con el extracto.

---

## Valores típicos de referencia (Junio 2026)

| Cargo | Total mes |
|-------|-----------|
| 4x1000 acumulado | ~$69,578 |
| Intereses ahorros | ~$303 |
| Cuota manejo tarjeta | $14,900 |
| Fee Shopify | $86,869 |
| Pauta Facebook | ~$20,607 |

---

## Nota sobre Wompi y Bold

- **Bold** ($472,250 jun 2026): pago de datáfono. Registrar como ingreso por la línea de negocio correspondiente, no como Comisión Pasarela.
- **Wompi**: recaudo de ventas online (PSE/tarjeta). Verificar si las ventas ya fueron registradas individualmente (ej: por Shopify sync). Si no, registrar por línea de negocio.
- **CCA Alianza Fiduciaria**: recaudo de ventas B2B. Identificar el proyecto/cliente y registrar como B2B.
