# Librerías que viajan con la página

`jspdf.umd.min.js` — jsPDF 4.2.1, build UMD para navegador (MIT).

Está acá y no en un CDN porque **cdnjs no sirve este archivo**: la ruta
`ajax/libs/jspdf/2.5.2/jspdf.umd.min.js` devuelve 404 y el índice de cdnjs lista la
versión 2.5.2 sin ningún `.js`. La página llamaba a esa URL, nunca cargaba, y el botón
de PDF no hacía nada — en la máquina de desarrollo no se veía porque las pruebas usan
el paquete de npm.

Se publica como archivo de apoyo del artifact:

    files: { "vendor/jspdf.umd.min.js": "web/vendor/jspdf.umd.min.js" }

Para actualizarlo: `npm i jspdf` y copiar `node_modules/jspdf/dist/jspdf.umd.min.js`.
