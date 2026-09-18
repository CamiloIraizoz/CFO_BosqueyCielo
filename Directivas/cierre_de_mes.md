# Directiva: Cierre de Mes

Proceso estándar para cerrar cada mes contable de Amphora B&C.
Ejecutar entre el día 1 y 5 del mes siguiente.

---

## FASE 1 — Pre-cierre: Integridad de datos

Antes de conciliar, verificar que todos los movimientos del mes están registrados.

**Checklist:**
- [ ] Shopify auto-sync corrió sin errores durante el mes (revisar `shopify_sync.log`)
- [ ] Todas las entradas manuales de ingresos están en Movimientos (Studio, Pottery Lab, Ceramikids, B2B, etc.)
- [ ] Todos los egresos del mes están registrados (materia prima, mano de obra, gastos operativos)
- [ ] No hay transacciones en estado pendiente que correspondan al mes que cierra
- [ ] Devoluciones y anulaciones del mes están marcadas (col Estado = ANULADO)

```bash
# Leer movimientos del mes para revisión
./execution/leer_rango.sh "Movimientos!A1:J200"
```

Si faltan movimientos, ingresarlos antes de continuar con las siguientes fases.

---

## FASE 2 — Conciliación bancaria

Cruzar el extracto del banco (fuente de verdad) contra los movimientos registrados en el Sheet.

**Pasos:**
1. Cargar extracto bancario del mes (PDF o CSV del banco)
2. Leer los movimientos bancarios registrados:
   ```bash
   ./execution/leer_rango.sh "Movimientos Bancarios 2026!A1:F200"
   ```
3. Cruzar línea por línea: cada débito/crédito del extracto debe tener su contraparte en el Sheet
4. Para cada diferencia encontrada:
   - Si falta en el Sheet → registrar la transacción en Movimientos
   - Si está en el Sheet pero no en el extracto → marcar como ANULADO o corregir
5. Al terminar, el saldo final según extracto debe coincidir con el saldo del Sheet

**Leer resumen bancario actual:**
```bash
./execution/leer_rango.sh "Resumen Bancario 2026!A1:D20"
```

---

## FASE 3 — Cuadre de caja

Verificar que la posición total de tesorería al 1° del mes siguiente cuadra matemáticamente.

**Fórmula de cuadre:**
```
Saldo inicial del mes
+ Total ingresos del mes
- Total egresos del mes
= Saldo final esperado

Saldo final esperado = Saldo banco al 1° + Efectivo en caja al 1°
```

Si no cuadra → hay un movimiento sin registrar o un error de monto. No avanzar al cierre hasta que cierre.

**Datos a recopilar:**
- Saldo banco según extracto al último día del mes
- Efectivo en caja física al cierre del mes (conteo manual)
- Total ingresos y egresos del mes desde el PNL

---

## FASE 4 — Cierre financiero (PNL real del mes)

Una vez conciliado y cuadrado, generar el estado de resultados real del mes.

```bash
python3 execution/resumen_mensual.py [MES]
# Ejemplo: python3 execution/resumen_mensual.py Junio
```

O leer directamente:
```bash
./execution/leer_rango.sh "PNL!A1:N50"
./execution/leer_rango.sh "Ingresos/Egresos Consolidados!A1:N30"
```

**Métricas a reportar:**
- Ingresos totales y por línea de negocio (Studio, Pottery Lab, Ceramikids, Ecommerce, Shop, B2B, Personalización, Kintsugi)
- Egresos totales y por categoría (Producción, Venta, Admin, Otros)
- Utilidad bruta y margen bruto %
- Utilidad neta y margen neto %
- Posición de caja al cierre (banco + efectivo)

---

## FASE 5 — Post-mortem: Real vs. Proyectado

Análisis separado del cierre. Su objetivo es entender desviaciones y extraer accionables.

**No es un reporte de resultados — es un diagnóstico.**

### Preguntas a responder:

**Ingresos:**
- ¿Qué líneas de negocio superaron el proyectado? ¿Por qué?
- ¿Qué líneas quedaron por debajo? ¿Por qué?
- ¿Hubo ingresos no proyectados (proyectos especiales, B2B puntual)? ¿Se deben proyectar en adelante?
- ¿Qué ingresos faltaron por registrar y por qué no estaban en el Sheet?

**Egresos:**
- ¿Qué categorías superaron el proyectado? ¿Era evitable?
- ¿Qué egresos proyectados no ocurrieron? ¿Se pospusieron o se eliminaron?
- ¿Hay egresos recurrentes que no estaban proyectados y deberían estarlo?

**Patrones de planeación:**
- ¿Hay líneas que sistemáticamente sobre- o sub-performan vs. proyectado? → el modelo de proyección necesita ajuste, no el negocio
- ¿El proyectado se hizo con suficiente información o fue un número de escritorio?

**Lectura del proyectado:**
```bash
./execution/leer_rango.sh "PROYECTADO DE [MES]!A1:C50"
```

### Accionables:
Al finalizar el post-mortem, definir mínimo:
1. **Qué ajustar en el proyectado del mes siguiente** (supuestos erróneos)
2. **Qué procesos operativos mejorar** (por qué faltaron movimientos)
3. **Qué líneas de negocio requieren atención** (bajo rendimiento recurrente)

---

## Orden de ejecución

```
Fase 1 (datos completos)
  → Fase 2 (conciliación bancaria)
    → Fase 3 (cuadre de caja — debe cerrar)
      → Fase 4 (cierre PNL real)
        → Fase 5 (post-mortem, sesión aparte)
```

No avanzar a la siguiente fase si la anterior tiene inconsistencias sin resolver.
El cuadre de caja (Fase 3) es el punto de no retorno: si cierra, los números son confiables.
