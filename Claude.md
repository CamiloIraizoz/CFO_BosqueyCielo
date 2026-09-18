# Instrucciones para el Agente

> Este archivo está replicado en CLAUDE.md, AGENTS.md y GEMINI.md para que las mismas instrucciones carguen en cualquier entorno de IA.

## Aprendizajes del Agente (Mejora Continua)

> **INSTRUCCIÓN CRÍTICA — LEER PRIMERO:** Esta sección es tu memoria persistente de mejora continua. **Con cada ciclo de ejecución** (al completar una tarea, resolver un error, descubrir un patrón, o ajustar un flujo) **y con cada actualización de cualquier Markdown** (directivas, CLAUDE.md, AGENTS.md, GEMINI.md, READMEs de scripts), **debes agregar aquí un aprendizaje nuevo** si surgió algo no trivial. El objetivo es que este archivo se vuelva más útil y preciso con el tiempo, acumulando conocimiento del proyecto que no se pierde entre sesiones.
>
> **Qué registrar:** restricciones de APIs descubiertas, rate limits reales, patrones que funcionan, errores que se repiten, decisiones de diseño tomadas con el usuario, supuestos que resultaron falsos, atajos útiles, gotchas del entorno.
>
> **Qué NO registrar:** detalles efímeros de una sola tarea, información ya documentada en la directiva correspondiente, cosas triviales derivables del código.
>
> **Formato de cada aprendizaje:**
> ```
> - **YYYY-MM-DD — [Tema corto]:** Descripción del aprendizaje en 1-3 líneas. **Por qué importa:** consecuencia práctica o cómo aplicarlo en el futuro.
> ```
>
> **Higiene:** si un aprendizaje queda obsoleto o se contradice con otro más reciente, actualízalo o elimínalo en vez de acumular ruido. Mantén la lista ordenada por fecha (más recientes arriba). Si superas ~25 entradas, consolida las más antiguas o promuévelas a la directiva que corresponda.

### Registro de aprendizajes

- **2026-09-18 — Se cotizan dos cosas, y solo una se costea:** Productos (motor de costos completo) y **experiencias Pottery Lab**, donde Camilo pone el precio por persona y la cotización es `participantes x precio` + traslado si es a domicilio. Pidió explícitamente que las experiencias NO se costeen. Cada una tiene su identidad: rosa para productos, arcilla (#8E8275) para Pottery Lab, en la página y en el PDF. **Por qué importa:** ofrecerle un motor de costos para talleres es trabajo que no quiere; y la empresa se llama **Bosque y Cielo** — "Studio Amphora" y "Amphoritas" son nombres de pestañas del Sheet (línea de clases), no el nombre de la empresa.

- **2026-09-18 — El empaque va por pedido, no por pieza:** Se cotiza una sola vez (`condiciones.empaque`) y el motor lo reparte entre las piezas del pedido, así que entra al costo unitario y lleva margen. Camilo eligió el reparto sobre cobrarlo como renglón aparte, para que el precio por pieza quede completo. Dejó de ser parámetro del taller y de ajuste por línea. **Por qué importa:** un costo que depende del pedido no puede vivir como parámetro fijo; si se cargaba por pieza, un pedido de 10 y uno de 300 pagaban el mismo empaque por unidad.

- **2026-09-17 — El CDN era el bug: jsPDF va dentro del artifact:** `cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.2/jspdf.umd.min.js` devuelve **404** — el índice de cdnjs lista la versión 2.5.2 sin ningún `.js`. El PDF nunca funcionó en el navegador y las pruebas locales no lo veían porque usan el paquete de npm. Ahora la librería viaja como archivo de apoyo del artifact (`files: {"vendor/jspdf.umd.min.js": ...}`) y la página la llama por ruta relativa. **Por qué importa:** una URL de CDN hay que verificarla con un `curl` antes de confiar en ella, y una dependencia externa en un artifact es un punto de falla que no se ve desde acá — mejor publicarla junto a la página.
- **2026-09-17 — La página y el Sheet son dos almacenes distintos:** El botón Guardar escribe en la base del artifact (se lee desde acá con ArtifactData), NO en el Cotizador Interno. Al Sheet solo escribe el bot, porque las credenciales de Google viven en Railway. El puente es el botón «Copiar para el bot»: un texto con todas las líneas y sus ajustes que se pega en Telegram, y el bot llama `guardar_hoja_cotizacion`. **Por qué importa:** cuando Camilo dice "no guarda", lo primero es mirar la base con ArtifactData — puede estar guardando perfecto en el sitio equivocado.

- **2026-09-17 — Una promesa de capacidad que nunca se resuelve deja la página muda:** `downloads.save()` abre una confirmación; si esa confirmación no se puede mostrar en la vista donde está abierto el artifact, la promesa no resuelve **ni rechaza**, y el botón parece muerto aunque el código esté bien. Hay que correr toda espera de una capacidad contra un plazo (`Promise.race`) y reportar el vencimiento. **Por qué importa:** los `catch` no alcanzan — un fallo silencioso no es un rechazo, y sin plazo no hay forma de distinguirlo de un botón sin listener.

- **2026-09-17 — Un botón que no hace nada es un bug, no un estado:** El botón de PDF se deshabilitaba solo cuando la cotización no era válida (pasa con L/fácil y XL, que no tienen tiempo medido en el Discovery) y no había forma de saber por qué. Ahora los botones nunca se deshabilitan en silencio: al hacer clic dicen el motivo, y la referencia sin estándar trae su propio campo de minutos de acabado para desbloquearse ahí mismo. También hay un «Ver PDF» que muestra el archivo dentro de la página, que no depende de la capacidad `downloads`. **Por qué importa:** desde afuera "no me deja descargar" puede ser cinco cosas distintas; cada camino tiene que nombrar la suya, con el código de error incluido.

- **2026-09-17 — `window.claude` no existe cuando arranca el script:** La página preguntaba una sola vez al cargar (`if (!window.claude) return;`) y, si la plataforma todavía no lo había inyectado, se quedaba sin base y sin descargas **para siempre**: el PDF no bajaba, las cotizaciones no se guardaban y los proyectos que agregaban se perdían. El arreglo es un `pedir(nombre)` que espera a que aparezca (hasta 12 s) y memoiza la promesa, y pedir la capacidad **en el momento del clic**, no al arrancar. **Por qué importa:** el fallo es silencioso — los botones se ven habilitados y no pasa nada; en cualquier página con capacidades hay que resolverlas perezosamente y mostrar en pantalla si hay conexión con la base.
- **2026-09-17 — Probar un artifact antes de publicarlo:** `jsdom` con `runScripts:"dangerously"` corre el HTML real, y con un `window.claude` falso **inyectado tarde** se reproduce el bug de arriba y se puede hacer clic en los botones de verdad. jsPDF se mete desde npm quitando el `<script src>` del CDN. **Por qué importa:** es la única forma de ver que un botón "no hace nada" sin publicar y pedirle al usuario que pruebe.

- **2026-09-17 — Cotizar varias referencias en un mismo pedido:** `cotizar_pedido()` cotiza cada línea con SUS materiales y SU decoración, y comparte lo que es del pedido (descuento, urgencia, envío, molde, IVA). Dos cosas que solo se ven con varias líneas: la advertencia de volumen debe mirar el total de piezas (`cantidad_pedido`), no cada línea, o un pedido de 10 referencias de 5 piezas suelta 10 avisos; y las advertencias "Sin medir" hay que colapsarlas en una. **Por qué importa:** los parámetros y los tiempos se leen UNA vez y se pasan a todas las líneas — leerlos por línea serían 20 llamadas a Sheets por cotización.
- **2026-09-17 — Los materiales varían por producto, no por taller:** Un plato de 27 cm lleva más bizcocho y más esmalte que un pocillo; cotizar los dos con el mismo costo era la mayor imprecisión del motor. Por eso existen los `AJUSTES_LINEA`: el parámetro general es el valor típico y el de la línea es la excepción (vacío = usar el general). **Por qué importa:** antes de subir un parámetro general porque "un producto salió barato", revisar si lo que cambia es ese producto y no el taller.
- **2026-09-17 — Cómo probar la página sin navegador:** Con un `document` falso de ~40 líneas (scratchpad `dom.js`), `eval` del `<script>` y jsPDF de npm, la lógica y el PDF de `web/bosque-y-cielo.html` corren en Node; después `pypdfium2` renderiza las páginas a PNG para mirarlas. Así se vio que el número de cotización se montaba encima de la fecha y que la segunda hoja no decía de qué cotización era. **Por qué importa:** es la única forma de revisar un artifact antes de publicarlo, y los errores de maquetación del PDF no se ven en el código.

- **2026-09-16 — Verificar permisos de HubSpot:** `execution/verificar_hubspot.py` prueba con llamadas reales qué permisos tiene el token (contactos, negocios, notas, archivos) y con `--escritura` sube y borra un PDF de prueba, que es la única forma de confirmar el scope `files`. Los 403 de HubSpot traen en `context.requiredScopes` el scope exacto que falta. **Por qué importa:** no hay `.env` local en esta máquina (las credenciales viven en Railway) ni CLI de Railway instalado, así que para verificar hay que pasar el token por entorno al correr el script.
- **2026-09-16 — Cotización → HubSpot automático:** Toda cotización enviada se registra sola vía `hubspot.registrar_cotizacion()`: resuelve contacto (por email exacto, o nombre exacto si no hay email), reutiliza el negocio abierto más reciente del contacto en vez de crear duplicados, y adjunta el PDF a una nota. Nunca retrocede de etapa: solo mueve a "cotizacion" un negocio que siga en "lead". Adjuntar el PDF exige el scope `files` en el token privado; si falta, la nota se crea igual sin adjunto. **Por qué importa:** el registro nunca debe romper el envío del correo — todos los fallos de HubSpot se devuelven como texto "⚠️ HubSpot: ..." y el correo ya salió.
- **2026-09-16 — `preparar_cotizacion()` es el punto único:** Numera, calcula el total, arma el detalle en texto y genera el PDF una sola vez; ese "paquete" lo comparten el envío por correo y el registro en HubSpot. **Por qué importa:** si llamas a `enviar_cotizacion(datos)` sin paquete, el número y el PDF se regeneran y HubSpot quedaría con otro número distinto al del correo.
- **2026-09-17 — Rangos de Sheets con espacios en el nombre:** `Parámetros Cotizador!A2:B60` es un rango inválido; tiene que ir como `'Parámetros Cotizador'!A2:B60`. Como `leer_sheet_numericos` y `escribir_rango` devuelven `[]` o un string de error en vez de lanzar, el cotizador cayó a valores de respaldo **en silencio**: guardabas un costo y el precio no cambiaba nunca. **Por qué importa:** todas las pestañas del proyecto hasta ahora eran de una palabra (Cartera, Competencia) y por eso nunca salió; usar siempre el helper `_rango()` y verificar el retorno de `escribir_rango` en vez de darlo por exitoso.
- **2026-09-17 — Las quemas no son costo directo:** Su energía ya está dentro de servicios públicos, que se prorratea por pieza. Cargarlas también como línea de costo las contaba dos veces e inflaba una taza M en ~$17.000. Los parámetros `costo_quema_*` quedan en cero. **Por qué importa:** antes de agregar una línea de costo, verificar que no esté ya dentro de un gasto mensual prorrateado.
- **2026-09-17 — El bot pregunta los datos que faltan, no solo los reporta:** `guardar_parametro_cotizador` escribe el valor en la hoja y la pestaña se crea sola al primer guardado. **Por qué importa:** una advertencia que se repite cada vez es ruido; preguntar una vez y guardar resuelve el problema de raíz.
- **2026-09-17 — Cómo se cotiza (decisiones con Camilo):** Los costos fijos se reparten entre un volumen de referencia FIJO (150 piezas/mes, la producción real), no entre las piezas del pedido: repartirlos entre el pedido daba $69.000 de fijos por pieza en un pedido de 30 y precios imposibles. Los minutos salen de la tabla de acabado del Discovery. **Por qué importa:** el volumen de referencia hay que actualizarlo cuando cambie la capacidad del taller, o todas las cotizaciones quedan mal calibradas.
- **2026-09-17 — La escala de dificultad del Discovery es 0/1/2, no 1/2/3:** El Discovery define grados 1-3 por dimensión y luego dice "Acabado: Bajo 1 o menos". Con escala 1/2/3 el mínimo sería 2 y "Bajo" sería inalcanzable; con 0/1/2 (grado menos uno) los rangos cuadran exactamente, y lo mismo pasa con modelado ("Bajo: 2 o menos", tres dimensiones). **Por qué importa:** con la escala mal leída, casi todo se clasificaba como difícil y el precio salía inflado.
- **2026-09-17 — El Cotizador Interno tiene la lógica pero no los datos:** La hoja trae la cadena completa (materiales → mano de obra → quemas → desperdicio 10% → mercadeo 5% → fijos → margen 40% → IVA 19%) y los parámetros de estructura (hora de taller $20.833, admin $1.230.000/mes, arriendo y servicios $840.000/mes), pero los 18 pasos de tiempo y los costos de materiales están en cero. **Por qué importa:** el motor calcula igual, pero SIEMPRE devuelve advertencias diciendo qué falta; nunca presentar ese precio como definitivo.
- **2026-09-17 — Scraping de competencia, lo que sí funciona:** Las webs de cerámica colombianas son un zoo (Shopify, Wix, WordPress, WooCommerce). Lo único estable es `/products.json` de Shopify (Carmesí 250 productos, Home Poetry 135, ambos con precio exacto). Para el resto se baja el HTML y **Claude extrae los precios**, no selectores CSS: cada competidor rediseña su web y los selectores se romperían en silencio. **Por qué importa:** antes de agregar un competidor, probar siempre `/products.json` — ahorra todo el trabajo.
- **2026-09-17 — Los precios casi nunca están en la home:** De 9 sitios revisados, solo 1 mostraba precios en su página de inicio; el resto los tiene en `/tienda`, `/shop`, `/collections/all` o `/clases`. Y varios competidores directamente no publican precios (los dan por WhatsApp o Instagram). **Por qué importa:** apuntar a la home da falsos "no hay precios"; hay que sondear rutas antes de dar por perdido a un competidor, y distinguir "no publica" (dato de mercado) de "no se pudo leer" (problema nuestro).
- **2026-09-17 — Tres trampas de xhtml2pdf en el diseño del PDF:** (1) las celdas centran su contenido verticalmente — hay que poner `vertical-align: top` en el CSS del `td`, el `valign="top"` del HTML no hace nada; (2) varios divs hermanos dentro de una celda se reparten para llenarla y dejan huecos enormes — el contenido de cada caja va en UN solo div con `<br/>`; (3) el `margin-top` de una tabla se mide mal y la manda a la página siguiente aunque quepa — usar un div espaciador con `height`. **Por qué importa:** los tres se ven como "el diseño quedó raro", no como un error, y cuestan mucho de diagnosticar sin renderizar.
- **2026-09-16 — Cotizaciones en PDF:** El HTML de `email_sender.py` (tablas anidadas con padding, ancho fijo 620px) revienta en xhtml2pdf con `negative availWidth`. Por eso `execution/pdf_cotizacion.py` tiene plantillas propias: tablas planas con anchos en %, sin anidar. Solo hay fuentes base: `Times` hace de serif de marca (el email usa Georgia) y `Helvetica` del resto. **Por qué importa:** si cambias el diseño de la cotización hay DOS plantillas que actualizar — email y PDF — y la de PDF hay que re-renderizarla para verificarla.
- **2026-09-16 — Verificar PDFs sin poppler:** El entorno no tiene `pdftoppm`, así que la herramienta Read no renderiza PDFs. Alternativa: `pip install pypdfium2` en un venv temporal y renderizar la página a PNG para inspeccionarla. **Por qué importa:** es la única forma de revisar visualmente un PDF generado antes de darlo por bueno.
- **2026-09-16 — Correo del cliente opcional en cotizaciones:** `enviar_cotizacion` y `enviar_cotizacion_pottery` ya no exigen email. Sin email → va solo a Daniela y Camilo con asunto `[Interna]`; con email → al cliente con copia a ambos. La lista interna vive en `CC_EMAILS` de `execution/email_sender.py`. **Por qué importa:** un solo punto de edición si cambian los correos internos.

<!-- Agrega nuevas entradas arriba de esta línea. -->

---

Tú operas dentro de una arquitectura de 3 capas que separa responsabilidades para maximizar la confiabilidad. Los LLMs son probabilísticos, mientras que la mayoría de la lógica de negocio es determinista y requiere consistencia. Este sistema resuelve esa incompatibilidad.

## La Arquitectura de 3 Capas

**Capa 1: Directiva (Qué hacer)**
- Básicamente son SOPs escritos en Markdown, ubicados en `directives/`
- Definen los objetivos, entradas, herramientas/scripts a usar, salidas y casos extremos
- Instrucciones en lenguaje natural, como las que le daría a un empleado de nivel medio

**Capa 2: Orquestación (Toma de decisiones)**
- Esta es tu función. Tu trabajo: enrutamiento inteligente.
- Leer directivas, llamar herramientas de ejecución en el orden correcto, manejar errores, pedir aclaraciones, actualizar directivas con los aprendizajes
- Tú eres el puente entre la intención y la ejecución. Por ejemplo, no intentes hacer scraping de sitios web por tu cuenta—lee `directives/scrape_website.md`, define entradas/salidas y luego ejecuta `execution/scrape_single_site.py`

**Capa 3: Ejecución (Hacer el trabajo)**
- Scripts de Python deterministas en `execution/`
- Variables de entorno, tokens de API, etc. se almacenan en `.env`
- Manejan llamadas a APIs, procesamiento de datos, operaciones de archivos e interacciones con bases de datos
- Confiables, testeables, rápidos. Use scripts en vez de trabajo manual.

**Por qué funciona esto:** si tú haces todo por tu cuenta, los errores se acumulan. Un 90% de precisión por paso = 59% de éxito en 5 pasos. La solución es empujar la complejidad hacia código determinista. Así tú te concentras solo en la toma de decisiones.

## Principios de Operación

**1. Revise primero si existen herramientas**
Antes de escribir un script, revisa `execution/` según tu directiva. Solo crea scripts nuevos si no existe ninguno.

**2. Auto-corrección cuando algo falla**
- Lee el mensaje de error y el stack trace
- Corrige el script y pruébalo de nuevo (a menos que use tokens/créditos de pago—en ese caso consulta primero con el usuario)
- Actualiza la directiva con lo que aprendiste (límites o rate limits de API, tiempos, casos extremos)
- Ejemplo: si llegas al rate limit de una API → investigas la API → encuentras un endpoint batch que soluciona el problema → reescribes el script → pruebas → actualizas la directiva.

**3. Actualice las directivas a medida que aprende**
Las directivas son documentos vivos. Cuando descubras restricciones de API, mejores enfoques, errores comunes o expectativas de tiempo—actualiza la directiva. Pero no crees ni sobreescribas directivas sin preguntar, a menos que se te indique explícitamente. Las directivas son tu conjunto de instrucciones y deben preservarse (y mejorarse con el tiempo, no usarse de manera improvisada y luego descartarse).

## Ciclo de Auto-corrección

Los errores son oportunidades de aprendizaje. Cuando algo falla:
1. Corrija el problema
2. Actualice la herramienta
3. Pruebe la herramienta, asegúrese de que funcione
4. Actualice la directiva con el nuevo flujo
5. El sistema ahora es más robusto

## Organización de Archivos

**Estructura de directorios:**
- `.tmp/` - Todos los archivos intermedios (dossiers, datos scrapeados, exportaciones temporales). Nunca se suben al repositorio, siempre se regeneran.
- `execution/` - Scripts de Python (las herramientas deterministas).
- `directives/` - SOPs en Markdown (el conjunto de instrucciones).
- `.env` - Variables de entorno y claves de API.
- `credentials.json`, `token.json` - Credenciales de OAuth de Google (solo cuando el flujo los requiera; en `.gitignore`).

**Principio clave:** Los archivos intermedios viven en `.tmp/` y pueden borrarse siempre. Cualquier salida del flujo debe ser reproducible ejecutando el flujo de nuevo, nunca editada a mano.

## Resumen

Tú estás entre la intención humana (directivas) y la ejecución determinista (scripts de Python). Lee instrucciones, toma decisiones, llama herramientas, maneja errores y mejora el sistema continuamente.

Se pragmático. Se confiable. Auto-corríjete.

