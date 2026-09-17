# Dónde vamos — 17 de septiembre de 2026

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

### 1. Publicar la página — desde la cuenta personal, NO la de Globetek
`web/taller-amphora.html` está lista. Se publica como Artifact con capacidades
`db`, `user` (scopes profile) y `downloads`.

**Debe publicarse desde la cuenta personal de Camilo.** Una página con base de datos
queda dentro de la organización que la publica: si sale bajo Globetek, los datos de
Bosque y Cielo viven ahí y se pierden el día que Camilo se desvincule.

Al publicarla hay que sembrar en su base:
- `config/parametros` — los valores que hoy están en `PARAMS_DEFECTO` de `cotizador.py`
- `config/tiempos` — las tablas de `ETAPAS_TIEMPO`

**Ojo con la duplicación:** la página recalcula el precio en JavaScript con la misma
cadena que `execution/cotizador.py`. Si se cambia la fórmula en un lado hay que
cambiarla en el otro, o el bot y la página darán precios distintos.

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

### 5. Verificar el scope `files` de HubSpot
`python3 execution/verificar_hubspot.py --escritura` (pasando `HUBSPOT_TOKEN` por
entorno). Si el PDF se adjunta bien a las notas, ya está: el bot lo dice en cada
cotización con "nota con PDF adjunto".
