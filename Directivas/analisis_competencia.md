# Directiva: Análisis de Competencia (Bosque y Cielo)

## Objetivo
Saber a qué precio vende la competencia sus productos de cerámica y sus talleres en
Bogotá, Cali y Medellín, y cómo se mueven esos precios en el tiempo. El valor no está
en la foto de un día, sino en el histórico: quién sube precios, cuándo y cuánto.

## Herramienta
`execution/competencia.py` — barrido de precios públicos.

```bash
python3 execution/competencia.py                      # barrido completo → Sheet
python3 execution/competencia.py --tipo talleres      # solo talleres
python3 execution/competencia.py --tipo productos
python3 execution/competencia.py --ciudad Medellin    # sin tilde también funciona
python3 execution/competencia.py --solo carmesi
python3 execution/competencia.py --sin-sheet --json   # prueba sin escribir nada
```

Desde Telegram: tool `barrer_competencia(tipo, ciudad)` en `execution/bot.py`.
Tarda entre 30 segundos y 2 minutos según cuántos competidores se consulten.

## Salida
Pestaña **Competencia** del Sheet (crearla con `python3 execution/setup_competencia.py`):

| Fecha | Competidor | Ciudad | Tipo | Ítem | Precio COP | Unidad | Detalle | Fuente |

Cada barrido **agrega** filas, nunca reemplaza. Así se acumula el histórico. No editar
la pestaña a mano: si algo quedó mal, se corrige el script y se vuelve a barrer.

## Los tres métodos de lectura
Cada competidor tiene la web hecha en algo distinto, así que no hay un solo camino:

- **`shopify`** — catálogo completo y exacto vía `/products.json`. Es el ideal: no se
  rompe y trae todas las variantes. Antes de agregar un competidor, probar siempre
  `curl https://SUDOMINIO/products.json?limit=2` a ver si cae por aquí.
- **`html`** — se baja la página pública y **Claude extrae los precios del texto**. Se
  usa un modelo y no selectores CSS a propósito: cada competidor rediseña su web cada
  tanto y los selectores se romperían en silencio. El modelo tiene instrucción estricta
  de omitir lo que no tenga precio explícito, nunca de estimarlo.
- **`manual`** — el competidor existe pero no publica precios. Queda registrado sin
  precio, con la razón en la columna Detalle. **Nunca inventar ni estimar un precio.**

## Reglas de convivencia
- Se respeta `robots.txt`: si no permite la consulta, se omite y se anota.
- Si un sitio responde 403 (bloquea consultas automáticas), se registra como bloqueado
  y **no se reintenta ni se disfraza la petición**. Lumbre y Barro es uno de esos.
- Un segundo de pausa entre sitios. No hay ningún apuro.
- Solo páginas públicas: nada que exija iniciar sesión. Por eso Instagram queda fuera,
  aunque sea la vitrina principal del gremio.

## Estado de las fuentes (verificado 2026-09-17)

**Productos — con precios:**
- Cerámicas Carmesí (El Carmen de Viboral) — Shopify, ~250 productos
- Home Poetry (Bogotá) — Shopify, ~135 productos
- Amasa Cerámica (Bogotá) — html, pocos precios en `/shop`

**Productos — sin precios públicos:** Tybso, Fray Angélico (venden por cotización).

**Talleres — con precios:**
- Dos Golondrinas (Medellín) — html
- Tornus Cerámica (Bogotá) — html, en `/clases`

**Talleres — sin precios públicos:** KUAN (solo publica precios de insumos, no de
clases), Mama Pottery, Alharaca (Wix que carga por JavaScript), Lumbre y Barro (bloquea).

**Cali: vacío.** En la búsqueda del 2026-09-17 no apareció ningún taller de Cali con web
propia y precios publicados — la competencia local se mueve en Instagram y WhatsApp.
Agregar a mano en `COMPETIDORES` los que Camilo y Daniela conozcan de primera mano.

## Referencias de mercado (2026-09-17)
Para dimensionar, de lo que sí está publicado:
- **Tazas/pocillos:** Carmesí mediana $42.500 (rango $19.500–$61.000) · Home Poetry
  mediana $69.500 (rango $45.000–$136.000)
- **Platos:** Carmesí mediana $36.500 · Home Poetry mediana $67.000
- **Clases sueltas en Bogotá:** entre $40.000 y $88.000 por persona
- **Experiencias en Medellín:** entre $100.000 y $120.000 por persona (unas 3 horas)

Carmesí es producción de El Carmen de Viboral a escala, con precios bajos; Home Poetry
juega en la gama alta de Bogotá. Son dos referencias distintas, no un promedio único.

## Cómo agregar un competidor
Editar la lista `COMPETIDORES` en `execution/competencia.py`:
1. Probar primero `/products.json` — si responde, es `shopify` y listo.
2. Si no, buscar **en qué URL están los precios**. Casi ninguno los muestra en la página
   de inicio: suelen estar en `/tienda`, `/shop`, `/collections/all`, `/clases`.
   Apuntar a esa URL, no a la home.
3. Si en ninguna página hay precios, entra como `manual` con su `nota`.

## Casos extremos
- Si el barrido no encuentra ningún precio, decirlo tal cual. Nunca rellenar con
  estimaciones ni con precios de barridos anteriores.
- Un competidor que antes traía precios y ahora no, puede haber rediseñado su web o
  haberlos quitado: revisar la URL antes de asumir que el script se rompió.
- Los precios de la competencia no son comparables uno a uno con los de Bosque y Cielo
  sin mirar tamaño, técnica y acabado. Al reportar, dar rango y mediana, no un número
  suelto que se preste a una conclusión apresurada.
