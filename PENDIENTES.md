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
- **Página Taller Amphora** (`web/taller-amphora.html`) — escrita y probada, **sin publicar**.

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
- `costo_empaque`
- Tiempos de **preparación del bizcocho** y de **terminado y empaque**, por tamaño
  (pestaña *Tiempos Estándar*). Lo ideal es cronometrarlos en planta.

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
