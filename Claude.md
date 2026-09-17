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

- **2026-09-16 — Verificar permisos de HubSpot:** `execution/verificar_hubspot.py` prueba con llamadas reales qué permisos tiene el token (contactos, negocios, notas, archivos) y con `--escritura` sube y borra un PDF de prueba, que es la única forma de confirmar el scope `files`. Los 403 de HubSpot traen en `context.requiredScopes` el scope exacto que falta. **Por qué importa:** no hay `.env` local en esta máquina (las credenciales viven en Railway) ni CLI de Railway instalado, así que para verificar hay que pasar el token por entorno al correr el script.
- **2026-09-16 — Cotización → HubSpot automático:** Toda cotización enviada se registra sola vía `hubspot.registrar_cotizacion()`: resuelve contacto (por email exacto, o nombre exacto si no hay email), reutiliza el negocio abierto más reciente del contacto en vez de crear duplicados, y adjunta el PDF a una nota. Nunca retrocede de etapa: solo mueve a "cotizacion" un negocio que siga en "lead". Adjuntar el PDF exige el scope `files` en el token privado; si falta, la nota se crea igual sin adjunto. **Por qué importa:** el registro nunca debe romper el envío del correo — todos los fallos de HubSpot se devuelven como texto "⚠️ HubSpot: ..." y el correo ya salió.
- **2026-09-16 — `preparar_cotizacion()` es el punto único:** Numera, calcula el total, arma el detalle en texto y genera el PDF una sola vez; ese "paquete" lo comparten el envío por correo y el registro en HubSpot. **Por qué importa:** si llamas a `enviar_cotizacion(datos)` sin paquete, el número y el PDF se regeneran y HubSpot quedaría con otro número distinto al del correo.
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

