# Dónde vamos — 18 de septiembre de 2026

Estado del proyecto para retomar en otra sesión. Lo que está hecho vive en el repo;
lo que falta está abajo con lo que hace falta para cerrarlo.

## Lo que quedó funcionando

- **Cotizaciones en PDF** (`execution/pdf_cotizacion.py`) — el correo del cliente es
  opcional: sin él va solo a Daniela y Camilo con asunto `[Interna]`.
- **Registro automático en HubSpot** (`hubspot.registrar_cotizacion`) — contacto, negocio
  en etapa cotización y nota con el PDF adjunto. Probado en producción.
- **Motor de cotización** (`execution/cotizador.py`) — ver `Directivas/cotizador.md`.
- **Análisis de competencia** (`execution/competencia.py`) — ver
  `Directivas/analisis_competencia.md`.
- **Página Bosque y Cielo** (`web/bosque-y-cielo.html`) — cotizador y producción.

## Lo que falta

### 1. ~~Publicar la página~~ — HECHO el 2026-09-17
**https://claude.ai/artifact/7tLyDp5hwSXnQLY5rWbM5j** — publicada desde la cuenta
personal (camilo.iraizoz@gmail.com), con `db`, `user` y `downloads`, y con
`config/parametros` y `config/tiempos` ya sembrados.

Para actualizarla desde otra conversación hay que pasar esa URL como `url` al publicar;
sin eso se crea un artifact aparte. Es privada hasta que se comparta desde su menú.

Versión 7 (2026-09-18): cotiza hasta **20 referencias en un mismo pedido**, cada una con
sus propios materiales, minutos de acabado, minutos extra y descuento; condiciones del
pedido (descuento, urgencia, envío, molde, anticipo, validez, plazo, IVA); pestaña
**Ajustes** con los parámetros del taller y la tabla de tiempos; y Producción con
bitácora por proyecto, anotaciones automáticas de cada cambio de etapa y pendientes.

**jsPDF viaja con la página** (`web/vendor/`, ver su README): la URL de cdnjs devuelve
404 y por eso el PDF no se armaba. Al republicar hay que volver a pasar el archivo de
apoyo, o la página queda sin generador:

```
files: { "vendor/jspdf.umd.min.js": "web/vendor/jspdf.umd.min.js" }
```

**Falta que Camilo confirme** que el PDF ya baja en su navegador — es lo único que no se
puede probar desde acá.

**Ojo con la duplicación:** la página recalcula el precio en JavaScript con la misma
cadena que `execution/cotizador.py`. Si se cambia la fórmula en un lado hay que
cambiarla en el otro, o el bot y la página darán precios distintos.

**Ojo con los parámetros:** la página los guarda en su propia base (`config/parametros`)
y el bot los lee de la hoja *Cotizador Interno*. Son dos sitios distintos: si se cambia
un costo en la pestaña Ajustes, hay que decírselo también al bot (o escribirlo en la
hoja) para que los dos coticen igual. La página lo advierte en pantalla.

**Dónde quedan las cotizaciones de la página:** en la base del artifact, colección
`cotizaciones` (se lee desde acá con ArtifactData). Al Cotizador Interno solo escribe el
bot, porque las credenciales de Google viven en Railway. El puente es el botón «Copiar
para el bot»: el texto se pega en Telegram y el bot llama `guardar_hoja_cotizacion`.

### 2. Cargar los costos que faltan
El precio sale **por debajo del real** hasta que estén. El bot los pregunta solo por
Telegram y los guarda; también se pueden escribir a mano en la pestaña
*Parámetros Cotizador*:

- `costo_esmaltes` u `oz_esmalte_por_pieza` (el galón de 128 oz cuesta $260.000 → $2.031/oz)
- Tiempos de **preparación del bizcocho** y de **terminado y empaque**, por tamaño
  (pestaña *Tiempos Estándar*). Lo ideal es cronometrarlos en planta.

El **empaque** ya no está en esta lista: va por pedido, se escribe en cada cotización.

Ya cargado: `costo_bizcocho` = $4.500 · volumen de referencia = 150 piezas/mes ·
servicios al 70% · margen 40% sobre el costo.

### 3. Darle acceso al bot al Cotizador Interno
La hoja *Cotizador Interno* (`1SRji5gNT85HPLOXBgUhQdIRG7WZvTTWx6eDPEu6exKE`) debe estar
compartida con la cuenta de servicio del bot — el correo que termina en
`.iam.gserviceaccount.com` y aparece en el panel Compartir del *Ventas y Costos B&C*.
Mientras no lo esté, el motor usa sus valores de respaldo y lo avisa en cada cotización.

### 4. Competencia en Cali
`COMPETIDORES` en `execution/competencia.py` no tiene ningún taller de Cali: en la
búsqueda del 2026-09-17 no apareció ninguno con web propia y precios publicados. Hay que
agregar a mano los que Camilo y Daniela conozcan.

### 5. Que Railway tome el último commit
El bot solo reconoce el texto de «Copiar para el bot» con el prompt del commit 6ca7b4f.
Si al pegarlo no responde como debe, revisar que Railway haya desplegado.

### 6. Verificar el scope `files` de HubSpot
`python3 execution/verificar_hubspot.py --escritura` (pasando `HUBSPOT_TOKEN` por
entorno). Si el PDF se adjunta bien a las notas, ya está: el bot lo dice en cada
cotización con "nota con PDF adjunto".

---

## Lo que trajo el asesor de producción y costos (2026-09-19)

Doce puntos de Camilo. Los dos primeros ya están hechos; el resto está ordenado por lo
que desbloquea, no por el número.

**Hecho**
- **(4) Separar costos** — el desglose ya sale agrupado en materia prima, mano de obra,
  desperdicio y costos indirectos, en la página, en el bot y en la hoja de cada cotización.
- **(1) Plantilla de tiempos para imprimir** — botón *Plantilla para cronometrar* en
  Ajustes. Hoja 1: la grilla etapa × tamaño × dificultad con lo ya medido en gris.
  Hoja 2: renglones para cronometrar pieza por pieza y sacar el promedio.

**El nudo: un catálogo de bizcochos** — junta los puntos 2, 3, 5, 6 y 9
Una referencia por bizcocho con: serial, nombre, alto, largo, ancho, peso, foto, tamaño
(XS-XL, que hoy se elige a mano y debería salir del peso), costo y onzas de esmalte
estándar. Con eso el cotizador deja de pedir datos sueltos: se elige la referencia y el
resto sale solo. Falta que Camilo levante la lista con fotos y medidas.

**Decisiones que faltan** (cada una cambia el precio)
- **(9) Onzas de esmalte por tamaño** — hoy hay un solo valor para todo. Debería ser una
  tabla por tamaño, como los tiempos. Falta el consumo real por tamaño.
- **(10) Vinilo** — ¿lleva o no lleva? ¿el costo va por pieza, por tamaño o por cantidad
  de vinilo? Falta la regla.
- **(11) Quemas y hornos** — hoy el costo de quema va en cero porque su energía está
  dentro de servicios públicos. Si se quiere costear por hornada hay que medir el consumo
  y **sacarlo** de servicios, o se cuenta dos veces.
- **(12) Capacidad de los hornos** — cuántas piezas de cada tamaño caben en una hornada.
  Sirve para dos cosas: repartir el costo de la quema y ser el tope de producción
  ("este pedido son 4 hornadas").
- **(8) Botón «llega modelado»** — cuando la pieza no se compra en bizcocho sino que se
  modela en casa. Cambia el material (arcilla en vez de bizcocho) y suma las etapas de
  modelado, que todavía no están medidas.
- **(7) «Acabado medio»** — Camilo quiere revisar ese rótulo. Falta saber qué le incomoda:
  el nombre, la regla que lo calcula, o que no se vea de dónde sale.


---

## Producción vive en Telegram (decidido el 2026-09-20)

Camilo eligió la opción 1: **un solo almacén**. El tablero de producción salió de la
página; la página quedó como cotizador (Productos · Pottery Lab · Ajustes).

Todo lo de producción está en el Sheet *Ventas y Costos B&C*, y el bot es su única
puerta:

| Qué | Pestaña | Herramientas del bot |
|---|---|---|
| Pedidos y su etapa | `Producción` | `agregar_pedido_produccion` · `actualizar_etapa_produccion` · `leer_produccion` |
| Parte diario del taller | `Jornadas` | `registrar_jornada` · `leer_jornadas` · `resumen_tiempos` |
| Pendientes | `Pendientes` | `agregar_pendiente` · `leer_pendientes` · `cerrar_pendiente` |

`leer_produccion` ya no devuelve la hoja pelada: le suma el avance que sale de las
jornadas ("Camilo Rojas: 40 pintar platos · 150 empacar").

**Quedó sin migrar:** los 3 proyectos que estaban en la base de la página (colección
`proyectos`, todos del mismo pedido de Camilo Rojas — 150 platos con frases, entrega
01/10/2026). No se borraron; siguen en la base del artifact por si hacen falta. Para
llevarlo al Sheet basta registrarlo una vez por Telegram.

## Jornadas del taller (2026-09-19)

Las dos personas que producen reportan por Telegram lo que hicieron en el día y de ahí
salen los minutos por pieza. Ver `Directivas/cotizador.md`, sección *De dónde salen los
tiempos*.


---

## Seguimiento de producción: resuelto (2026-09-21)

Camilo decidió que **la etapa se deduce de las jornadas** y que moverla a mano queda solo
para corregir (`execution/avance.py`).

- Un pedido pasa de etapa cuando las piezas reportadas en esa etapa alcanzan la cantidad
  del pedido. Por eso `agregar_pedido_produccion` ahora **exige las piezas** (columna K de
  la pestaña Producción) y el bot las pregunta.
- **La deducción solo avanza.** Una jornada vieja nunca deshace una corrección a mano, ni
  en el recálculo ni en el tablero.
- `leer_produccion` muestra: etapa, cuántas piezas van de cuántas, y **cuántas horas de
  taller faltan** para cerrar la etapa en curso, al ritmo medido en las jornadas de ESE
  pedido y a 12 h/día (2 personas × 6 h). Si la proyección se pasa de la fecha de entrega,
  el bot lo dice sin que le pregunten.
- El ritmo se toma **de la etapa en curso**, no del promedio del pedido: si esmaltar va a
  6 min/pieza y pintar a 24, el promedio (11) subestimaría el pintado a menos de la mitad.
- "Lo metí al horno" solo se asigna a una quema cuando el proceso tiene **una sola**. En
  el clásico hay dos y es ambiguo: mejor no adivinar y que el bot pregunte.

**Lo que sigue sin resolver:** las etapas que no son trabajo por pieza. Una quema son 12 h
más 18 h de enfriamiento por hornada, y eso no se acelera con más gente — la proyección de
horas de taller no lo tiene en cuenta todavía.

## Acceso del taller al bot (2026-09-20)

**Las dos personas del taller NO necesitan permiso en Google Sheets.** Quien escribe en la
hoja es la cuenta de servicio del bot (`amphora-cfo@amphora-bc-496723.iam.gserviceaccount.com`),
no la persona. Darles acceso al Sheet sería además peligroso: verían cartera, márgenes y
nómina, y podrían romper fórmulas sin querer.

Lo que necesitan es acceso **al bot**, y para eso hubo que ponerle roles — antes
respondía a cualquiera que lo encontrara, con acceso completo a cartera, flujo de caja,
HubSpot y Meta Ads.

| Rol | Quién | Qué puede |
|---|---|---|
| `admin` | Camilo (y quien él agregue) | las 43 herramientas |
| `taller` | las dos personas que producen | 8: jornadas, pendientes y ver producción |
| desconocido | cualquiera | nada — le devuelve su código para que Camilo lo autorice |

Al rol `taller` ni siquiera se le **ofrecen** las otras herramientas al modelo, así que no
puede llamarlas aunque se lo pidan. Y usa un prompt distinto (`SYSTEM_TALLER`), corto y
enfocado: si le preguntan por plata o clientes, responde que de eso no sabe.

### Cómo dar de alta a alguien
1. La persona le escribe `/chatid` al bot. Le responde su código (o sale en el mensaje de
   rechazo).
2. Camilo agrega ese número a la variable de entorno en Railway:
   - `TALLER_CHAT_IDS` — separados por coma, para la gente del taller.
   - `ADMIN_CHAT_IDS` — para quien deba verlo todo.
3. Railway reinicia y listo.

**Ojo:** si ninguna de las dos variables está puesta, el bot se comporta como antes
(abierto a todos). Como `ADMIN_CHAT_ID` ya existe en Railway, los roles se activan solos
en el próximo despliegue.

### Mezclan lotes
Confirmado por Camilo: las dos personas trabajan por prioridades y mezclan pedidos en una
misma sesión. Por eso el prompt del taller pide registrar **una jornada por pedido**,
repartiendo piezas y tiempo en proporción, y diciendo cómo se repartió.

### Los números del taller
- **$10.000 la hora** de trabajo (`costo_hora_mo`). Antes se deducía del salario mensual
  y daba **$20.833** — más del doble. El valor puesto a mano ahora manda.
- **2 personas × 6 horas = 12 horas de taller al día** (`personas_taller`,
  `horas_dia_persona`). Es la base para proyectar fechas de entrega.
- **La gerente: $5.000.000/mes, 20% a producción** (`sueldo_gerente_mes`,
  `pct_gerente_produccion`). Confirmado por Camilo el 2026-09-21 — el resto de su día
  son tareas gerenciales. Ese 20% son $6.667 de cada pieza; si su rol cambia, hay que
  volver a mirarlo porque es el parámetro que más mueve el precio.
