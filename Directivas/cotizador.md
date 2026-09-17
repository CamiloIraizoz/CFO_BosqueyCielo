# Directiva: Cotizador (Bosque y Cielo)

## Objetivo
Calcular cuánto cobrar por una pieza de cerámica a partir de los costos reales del
taller, con el desglose completo, para no cotizar a ojo. El resultado es un precio
**sugerido**: la decisión de cobrar más o menos siempre es de Camilo.

## Herramienta
`execution/cotizador.py`

```bash
python3 execution/cotizador.py --cantidad 50 --tamano M --dificultad medio --producto "Taza cónica"
python3 execution/cotizador.py --cantidad 6 --tamano L --dificultad facil --minutos 22
```

Desde Telegram: tool `calcular_precio(...)` en `execution/bot.py`. Primero se calcula el
precio, después se envía la cotización con `enviar_cotizacion`.

## La cadena de cálculo
Réplica exacta de la hoja **Cotizador Interno** (pestaña *Costos Detallados*):

```
  materiales (bizcocho + esmaltes + vinilo)
+ mano de obra  (minutos por pieza x valor hora)
+ empaque
= costo directo
+ desperdicio (10%)
= costo directo total
+ mercadeo (5% del costo directo total)
+ arriendo y servicios por pieza
+ gastos administrativos por pieza
= gran total costo + gastos
x margen (40% sobre el costo)
= PVP sin IVA   →  + IVA (19%)  =  precio final
```

## Las quemas NO son costo directo
La energía de las dos quemas ya está dentro de **servicios públicos**, que se prorratea
por pieza más abajo. Cobrarlas además como línea de costo directo sería contarlas dos
veces e inflar el precio (en una taza M, unos $17.000). Los parámetros
`costo_quema_*` existen pero van en **cero**, y solo se llenarían si algún día se mide
el consumo por hornada y se saca ese valor de servicios públicos.

Por eso `pct_uso_servicios` está en **70%** (decisión de Camilo, 2026-09-17), muy por
encima del 20% del arriendo: el arriendo se reparte por metros cuadrados, pero la
energía la consumen los hornos. Con eso los fijos locativos quedan en $1.340.000/mes,
o **$4.467 por pieza** sobre 300 piezas/mes.

## Dos decisiones de negocio (2026-09-17, con Camilo)

**1. Los fijos se reparten entre 300 piezas/mes, no entre el pedido.**
300 es la producción real del taller. Si los fijos se repartieran entre las piezas del
pedido, uno de 30 piezas cargaría $69.000 de fijos por pieza y el precio sería
imposible de vender. La contrapartida: un pedido chico solo se sostiene si el mes se
llena con otro trabajo — por eso el cotizador avisa cuando el pedido es menor al 20%
del volumen de referencia.

**Hay que actualizar `volumen_referencia` cuando cambie la capacidad del taller.**
Si no, todas las cotizaciones quedan mal calibradas.

**2. El margen del 40% se aplica sobre el costo** (costo × 1,40), no sobre el precio de
venta. El parámetro `margen_modo` permite cambiarlo a `sobre_venta` (costo ÷ 0,60), que
sobre la misma pieza da unos $12.000 más.

## Clasificación de la pieza

**Tamaño** (por gramaje, del Discovery): XS/S piezas pequeñas (~0.65 kg) · M taza o plato
de 27 cm (~1.2 kg) · L jarra o pieza de ~2 kg · XL matera grande (4 kg+).

**Dificultad del acabado**: NO se juzga a ojo. Se pasan `pct_pintado` y `num_tintas` y el
script aplica la regla del Discovery. Cada dimensión aporta **0, 1 o 2 puntos**:

| | 0 puntos | 1 punto | 2 puntos |
|---|---|---|---|
| Superficie pintada | 0-29% | 30-59% | 60-100% |
| Tintas | 0-1 | 2-3 | 4+ |

Si la pintura va solo sobre el relieve, se resta 1 punto.
Total: **Bajo ≤ 1 · Medio 2-3 · Alto 4+**

Ojo: el Discovery numera los grados del 1 al 3, pero sus propios rangos ("Bajo: 1 o
menos") solo cuadran con la escala 0/1/2. Leerlo como 1/2/3 hace que casi todo caiga en
"difícil" y el precio salga inflado.

## Tiempos de acabado (minutos por pieza, Discovery 2026-09)

| Tamaño | Fácil | Medio | Difícil |
|---|---|---|---|
| XS | 4.0 | 10.0 | 20.0 |
| S | 6.5 | 12.6 | 23.0 |
| M | 9.5 | 14.7 | 23.0 |
| L | — | 18.3 | 26.2 |
| XL | — | 26.0 | — |

Las celdas vacías no están medidas. El cotizador **se niega a calcular** en esos casos y
pide los minutos a mano (`--minutos` o `minutos_acabado`). No se estiman en silencio.

## Parámetros
Viven en la pestaña **Parámetros Cotizador** de la hoja *Cotizador Interno*
(archivo distinto del *Ventas y Costos B&C*). Se crean con:

```bash
python3 execution/setup_cotizador.py
```

**Requisito:** el Cotizador Interno debe estar compartido con la cuenta de servicio del
bot (el correo que termina en `.iam.gserviceaccount.com`; aparece en el panel Compartir
del *Ventas y Costos B&C*). Mientras no lo esté, el motor corre con los valores de
respaldo embebidos en `cotizador.py` y lo avisa en consola.

Estructura actual: salario mensual $4.000.000 sobre 192 horas → hora de taller $20.833 ·
gastos administrativos $1.230.000/mes · arriendo $3.200.000 al 20% de uso ·
servicios $1.000.000 al 70% de uso · desperdicio 10% · mercadeo 5% ·
margen 40% sobre el costo · IVA 19%.

## El bot pregunta lo que falta
Cuando una cotización sale con la advertencia "Sin costo cargado: ...", el bot **pregunta
esos valores en lenguaje llano**, de a uno por mensaje, y los guarda con
`guardar_parametro_cotizador`. Así cada dato se pide una sola vez en la vida. Si el
usuario no lo sabe en el momento, no se insiste: vuelve a aparecer en la siguiente
cotización.

Preguntables hoy: `costo_bizcocho`, `costo_esmaltes`, `costo_empaque`, `costo_vinilo`,
`minutos_otros_pasos`, `volumen_referencia`, `margen_pct`.

La pestaña de parámetros se crea sola la primera vez que se guarda un valor, así que no
hace falta correr el setup a mano.

## Cada cotización deja su hoja
Cuando el precio ya es el definitivo, `guardar_hoja_cotizacion` crea en el Cotizador
Interno una pestaña con **todo el desglose**: la pieza, los minutos, cada línea de costo,
el margen, el IVA, las advertencias y **los parámetros exactos que se usaron**. Con eso
se puede reproducir cualquier precio meses después y entender por qué dio lo que dio.

Además se registra una fila en la pestaña índice **Cotizaciones** (fecha, número,
producto, cantidad, PVP, total, y en qué pestaña está el detalle).

No se guarda en cada tanteo de precio, solo cuando el precio es el bueno o se va a enviar
la cotización — si no, el archivo se llena de hojas basura.

## El esmalte se carga en onzas
El galón de 128 oz cuesta $260.000, o sea **$2.031 la onza**. Es más fácil saber cuántas
onzas lleva una pieza que cuántos pesos, así que el bot pregunta `oz_esmalte_por_pieza` y
saca el costo. Si de todos modos se carga `costo_esmaltes` en pesos, las onzas mandan
cuando están puestas. Los demás materiales de referencia (barbotina $140/oz, arcilla Luis
Reyes $4.80/g, arcilla negra $3.91/g) están en `MATERIALES` de `cotizador.py`.

## Gotcha: los nombres de pestaña con espacios van entre comillas
`Parámetros Cotizador!A2:B60` NO se puede parsear; tiene que ser
`'Parámetros Cotizador'!A2:B60`. Para eso está el helper `_rango()`. Como
`leer_sheet_numericos` se traga los errores y devuelve `[]`, un rango mal armado hacía
que el cotizador usara los valores de respaldo **en silencio** y el precio no cambiara
nunca por más datos que se guardaran. Ahora `cotizar` avisa cuando no pudo leer la hoja.

## Lo que falta cargar (al 2026-09-17)
En la hoja están en cero, así que **hoy el precio sale por debajo del real**:
`costo_bizcocho`, `costo_esmaltes`, `costo_empaque` y `minutos_otros_pasos`.

Como referencia de la diferencia: una taza M de acabado medio da **$20.247** de PVP con
lo que hay hoy, y **$47.520** con valores de ejemplo cargados.

## Casos extremos
- **Mostrar siempre las advertencias.** Mientras falten costos, el número no es un precio
  definitivo y presentarlo como tal lleva a vender por debajo del costo.
- Si no hay tiempo medido para ese tamaño y dificultad, pedir los minutos. Nunca estimar.
- Los precios de la competencia (ver `Directivas/analisis_competencia.md`) sirven para
  contrastar, no para fijar el precio: el costo manda.
