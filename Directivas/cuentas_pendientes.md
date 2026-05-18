# Directiva: Cuentas Pendientes

## Spreadsheet ID
`1UgbFF9HWMEwV8ShxxCQn61OXDLPA9-_UykK_o3-c5kE`

## Por PAGAR — revisar filas con estado vacío
- `Mano de Obra!A1:F50`
- `Materia Prima!A1:F50`
- `Gastos Operativos!A1:F50`
- `PROYECTADO DE MAYO!A1:C60`

## Por COBRAR — proyectos con saldo pendiente
- `Proyecto Padova!A1:F30`
- `Kintsugi!A1:F30`
- `Proyecto Iluminata!A1:F30`

## Flujo
1. Leer cada pestaña
2. Identificar filas sin estado "OK"
3. Consolidar lista ordenada por monto
4. Al confirmar pago → actualizar celda de estado a "OK Pagado"
