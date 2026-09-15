# De la venta al comprobante

Una aplicación educativa de Loopian para mostrar en YouTube cómo transformar una planilla de ventas en una herramienta administrativa. Interfaz luminosa, violeta oscuro y acentos lima; tres pasos: **Revisar ventas → Preparar comprobantes → Resumen mensual**.

**DEMOSTRACIÓN · Sin validez fiscal.** Usá exclusivamente datos ficticios y correos `@example.com`.

## Versión 2: correcciones desde la pantalla

La app ahora se organiza en **1 · Revisar**, **2 · Preparar** y **3 · Resumen**. La cabecera ocupa menos espacio, el aviso de demostración permanece fijo y las explicaciones están agrupadas en **Cómo funciona**. El botón de respaldo aparece debajo del contenido de cualquiera de las tres pestañas.

### Corregir el ejemplo sin volver a la planilla

1. En **1 · Revisar**, el formulario selecciona primero una fila con errores. La etiqueta incluye el número de fila, el ID y el cliente para distinguir las dos `V003`.
2. En la **fila 4**, cambiá `V003` por `V005` y tocá **Guardar corrección**. Si todos los datos son válidos, se habilitan tanto esa venta como la otra `V003` que dejó de estar duplicada.
3. El formulario pasa al error restante. En la **fila 6**, reemplazá `no_es_un_importe` por `17500,25` y guardá.
4. Ahora hay **5 ventas pendientes válidas**, sin errores, por **$ 327.500,75**. La corrección no genera ni aprueba un comprobante.
5. En **2 · Preparar**, elegí una venta, revisá los datos, marcá la aprobación y generá su comprobante demo.
6. Descargá el registro actualizado para conservar tanto las correcciones como el historial. El **CSV original** sigue siendo el archivo cargado inicialmente y no incluye los cambios hechos en pantalla.

### Reglas de corrección

- Podés corregir ID, fecha, cliente ficticio, email de ejemplo, concepto e importe. El estado y los datos de comprobante se administran automáticamente.
- Sólo se guarda una corrección si la fila queda válida y su ID es único. Si falla, no se modifica ninguna venta ni el historial; el formulario conserva lo que escribiste para que puedas corregirlo.
- Nunca se permite editar una fila cuyo ID ya tenga un comprobante conservado, aunque esa fila aparezca con error por un CSV conflictivo. Tampoco se puede asignar el ID de un comprobante a otra venta, incluso si el original ya no está en la planilla activa.
- Al guardar se vuelven a validar todas las filas. Los otros errores pueden permanecer, pero no se incorporan a los totales. No hay edición parcial de una fila que siga siendo inválida.
- Una corrección borra las aprobaciones que hubieran quedado marcadas en pantalla: siempre hay que revisar y aprobar los datos actuales.
- Los registros de la primera versión siguen siendo compatibles. El historial conserva sus IDs, fechas y PDF; no hace falta migrarlo ni volver a procesarlo.

### Diseño para celular

Se agregaron ajustes para pantallas de **390 px**: pestañas cortas en una fila, campos que se apilan, botones de al menos 44 px y ancho completo, texto largo que puede partirse y tarjetas de ventas en lugar de la tabla horizontal en pantallas pequeñas. El resumen también usa tarjetas. La tabla de escritorio queda dentro de **Ver todas las ventas**. Se implementaron estos estilos; la revisión visual en un navegador real de 390 × 844 sigue pendiente, ya que el navegador disponible no pudo acceder al servidor local.

## Publicarla gratis desde el navegador

No necesitás instalar Python en tu computadora para publicar en Streamlit Community Cloud. No hay APIs pagas ni claves de IA.

1. Descargá el ZIP y descomprimilo en tu computadora.
2. Entrá a [GitHub](https://github.com/), iniciá sesión y elegí **New repository**. Por ejemplo: `loopian-ventas-demo`. Elegí un repositorio público y crealo. Subí únicamente el código y los datos ficticios de este paquete.
3. En el repositorio, elegí **Add file → Upload files**. Subí `app.py`, `requirements.txt`, `ventas_ejemplo.csv` y `README.md` en la raíz, sin una carpeta contenedora. Podés sumar `test_app.py` para conservar las pruebas. Confirmá con **Commit changes**.
4. Agregá también la configuración visual: **Add file → Create new file**, escribí `.streamlit/config.toml` como nombre, copiá el contenido siguiente y confirmá el cambio. El ZIP ya incluye ese archivo; podés subir la carpeta si tu navegador la muestra.

```toml
[theme]
base = "light"
primaryColor = "#493064"
backgroundColor = "#FAF9FC"
secondaryBackgroundColor = "#F0EDF5"
textColor = "#302044"
font = "sans serif"

[server]
maxUploadSize = 2

[browser]
gatherUsageStats = false
```

5. Entrá a [Streamlit Community Cloud](https://share.streamlit.io/), iniciá sesión y conectá tu cuenta de GitHub siguiendo las pantallas del servicio.
6. Elegí **Create app** y, si aparece, **Yup, I have an app**. Seleccioná el repositorio, la rama `main` y **Main file path: `app.py`**.
7. En **Advanced settings**, elegí **Python 3.11**, que es la versión probada. Dejá vacío el campo de secretos: esta app no los necesita.
8. Presioná **Deploy**. Cuando termine la instalación, abrí el enlace que te entregue Streamlit. Los nombres de los botones de GitHub y Streamlit pueden aparecer en inglés.

La publicación gratuita y el flujo de repositorio/rama/archivo están documentados por [Streamlit](https://streamlit.io/) y en su [guía oficial de despliegue](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy). Consultados el 15/09/2026. La instancia de ejemplo está publicada; para tener tu propia copia, seguí estos pasos en tus cuentas.

Si aparece `ModuleNotFoundError`, comprobá que `requirements.txt` esté junto a `app.py`. Si no encuentra el archivo principal, revisá que no hayas subido toda la carpeta dentro de otra carpeta. Guardá `.streamlit/config.toml` para fijar el tema claro.

## Primera demostración: 3 minutos

1. Abrí la app: ya aparecen las **5 filas ficticias de septiembre de 2026**.
2. Mostrá los errores: las dos filas `V003` están bloqueadas por ID repetido; `V004` contiene `no_es_un_importe`. No se elige una de las filas repetidas ni se convierte el importe inválido en cero.
3. El total inicial válido es **$ 210.000,50**, correspondiente a `V001` y `V002`. Hay **3 filas con errores** y cero comprobantes.
4. En **Preparar comprobantes**, revisá `V001`: cliente, email, concepto y $ 85.000,00. Marcá la aprobación y tocá **Aprobar y generar comprobante demo**. Sin la casilla marcada no se procesa.
5. Descargá el PDF y usá **Descargar correo preparado** para obtener el `.eml` con ese mismo PDF adjunto. La app no envía nada. El archivo puede abrirse en un cliente de correo que admita `.eml`; la vista de borrador depende de ese cliente.
6. En septiembre, el resumen ahora muestra **1 comprobante / $ 85.000,00**, **1 venta pendiente / $ 125.000,50** y **3 filas con errores / importe excluido**.
7. Descargá el resumen mensual y, especialmente, el **registro actualizado CSV**.
8. Volvé a importar `ventas_ejemplo.csv` en la misma sesión: `V001` continúa procesada y su comprobante conserva el ID.
9. Para mostrar la recuperación: descargá el registro, restablecé el ejemplo con su confirmación e importá ese registro. Se recuperan los estados y el PDF. No hace falta volver a aprobar lo que ya estaba procesado.

La app permite descargar el CSV original cargado y el ejemplo incorporado. Para empezar nuevamente, abrí **Restablecer el ejemplo** en **1 · Revisar**, marcá la confirmación y presioná **Restablecer ejemplo**. Ese reinicio borra deliberadamente los comprobantes de la sesión; descargá antes lo que quieras conservar.

## Formato CSV

Columnas obligatorias, en minúsculas y sin espacios alrededor del encabezado:

| Columna | Formato |
| --- | --- |
| `id` | Único. De 1 a 40 letras ASCII, números, guiones o guiones bajos. Empieza con letra o número. Distingue mayúsculas de minúsculas. |
| `fecha` | `AAAA-MM-DD`, fecha válida desde 1900. |
| `cliente` | Nombre ficticio, hasta 120 caracteres. |
| `email` | Dirección ficticia terminada en `@example.com`. |
| `concepto` | Texto de hasta 800 caracteres. |
| `importe` | ARS, mayor que cero, hasta 9.999.999.999,99. Sin separadores de miles; punto o coma decimal, máximo 2 decimales. |
| `estado` | `pendiente` en una planilla nueva. El registro exportado también usa `procesada` y `error`. |

Codificación UTF-8; se acepta BOM, separador coma o punto y coma. Si el separador es coma y el importe lleva coma decimal, encerrá el valor entre comillas: `"85000,50"`. Límite: 2 MB y 5.000 filas por archivo. Se rechazan caracteres de control y saltos de línea dentro de celdas. Cliente y concepto admiten texto español/CP1252, sin emojis u otros alfabetos; si aparecen, se indica el error.

El importe se valida y se suma con `Decimal`. pandas se usa para las tablas visuales, no para calcular dinero.

Corregí los errores en el formulario de la pestaña **1 · Revisar**, o en la planilla de origen para volver a importarla. No hace falta cambiar `error` a `pendiente`: el estado se recalcula. Una venta marcada `procesada` sin su respaldo queda bloqueada; escribir ese estado a mano no genera un comprobante.

**Importar reemplaza las ventas que se están revisando**, pero conserva el historial de comprobantes de esa sesión. No acumula automáticamente las ventas pendientes de diferentes archivos. Descargá el registro antes de cambiar de archivo. Para revisar varios meses juntos, importá una planilla que los incluya.

## Guardar y recuperar: el registro es el respaldo

La app usa `st.session_state`, sin base de datos. Cada sesión tiene su propio estado. Una recarga completa del navegador, desconexión, suspensión de la app o reinicio del servidor puede perderlo. No hay coordinación entre usuarios ni entre pestañas independientes.

**Descargá el registro actualizado después de procesar ventas.** Para recuperarlo, abrí **Cargar CSV o recuperar registro** en **1 · Revisar**, seleccioná el CSV y tocá **Importar CSV**.

El registro agrega `tipo_registro`, `version_registro`, `id_demo`, `fecha_demo` y `errores`:

- `tipo_registro = venta`: filas de la planilla activa con estados recalculados y observaciones.
- `tipo_registro = comprobante`: una copia del contenido de cada comprobante preparado. Permite conservar comprobantes aunque cambies de planilla y reconstruir los PDF sin guardar archivos binarios.

**No sumes juntas las filas de ambos tipos.** Una venta procesada aparece como venta y también como respaldo. La app y el resumen distinguen los tipos y cuentan cada comprobante una sola vez. En Sheets filtrá `tipo_registro = venta` para ver la planilla de trabajo. Conservá las filas `comprobante`, sus columnas y valores al exportar el respaldo completo.

No edites las filas de comprobante. Si un registro importado entra en conflicto con un comprobante de esta sesión, se rechaza la importación completa y se conserva el estado anterior. Si una venta usa el ID de un comprobante pero cambia sus datos, esa venta queda bloqueada; el comprobante original se conserva.

Los ID `DEMO-…` se derivan del ID de venta. Volver a hacer clic, ejecutar de nuevo la pantalla o reimportar el mismo archivo en una sesión no prepara un segundo comprobante. Al restaurar el registro, se conserva la fecha de preparación y se reconstruye el mismo PDF con estas versiones del generador. Cambiar código o versiones puede cambiar la representación del PDF, aunque se mantengan los datos.

El registro **no está firmado ni autenticado**. Si se altera fuera de la app y se carga en una sesión vacía, no hay una fuente externa que pruebe su autenticidad. El ID demo es una referencia administrativa, no una autorización ni una garantía fiscal.

El CSV exportado agrega una comilla simple inicial a celdas que podrían interpretarse como fórmulas. Al reimportar un registro de versión 1, la app revierte esa protección. Conservá esa comilla en la planilla para mantener los valores literales.

## Resumen para el contador

**Resumen administrativo de ejemplo**, descargable como CSV UTF-8:

- Cantidad e importe de comprobantes demo conservados del mes.
- Cantidad e importe de ventas válidas pendientes de la planilla activa.
- Cantidad de filas con errores del mes, con importe vacío/excluido.
- Cantidad de errores sin fecha válida, informados aparte y sin asignarlos arbitrariamente a un mes.

El criterio temporal es **fecha de venta**, tanto para pendientes como para comprobantes; no la fecha en que se preparó el PDF. Las fechas de preparación se registran en UTC. Los errores se cuentan por fila: una fila con varios problemas cuenta una vez. Los contadores de la pestaña Revisar abarcan todos los meses; los importes están en Resumen.

Si cargás una fila errónea que coincide con un ID procesado anteriormente, se informa el error de la fila activa; el comprobante previo sigue en el historial y se cuenta por sus datos originales. Adjuntá también el registro completo si el contador necesita el detalle; la app no comparte ni envía archivos automáticamente.

## Google Sheets, sin sincronización automática

Para cargar ventas:

1. Abrí la hoja con las columnas requeridas.
2. Elegí **Archivo → Descargar → Valores separados por comas (.csv, hoja actual)**.
3. Cargá ese archivo en la app y tocá **Importar CSV**.

Para devolver el registro a Sheets:

1. Descargá **registro actualizado CSV** desde la app.
2. En Sheets, elegí **Archivo → Importar → Subir**.
3. Elegí **Insertar hojas nuevas** para conservar tu planilla original.
4. Conservá IDs como texto y fechas como `AAAA-MM-DD`. Si se ofrece conversión automática a números, fechas o fórmulas, desactivala para el respaldo.
5. Filtrá por `tipo_registro = venta` para revisar las ventas. Conservá el respaldo completo con las filas `comprobante`; no descargues únicamente una selección para recuperar la sesión.

No hay lectura o escritura conectada a Google Sheets. El intercambio es manual por CSV.

## Alcance y límites

- Datos ficticios, para capacitación y grabación. Sin cuentas, permisos por usuario ni auditoría de producción.
- **Sin emisión ARCA**. No se calcula IVA, no se eligen alícuotas, no se inventan exenciones ni se imita una autorización. No se solicita ninguna clave fiscal.
- Los PDF llevan **DEMOSTRACIÓN · Sin validez fiscal**, un ID interno DEMO, importe registrado y texto educativo. No tienen letra fiscal, CAE, QR fiscal ni logos de ARCA. Tampoco acreditan pago.
- **La emisión fiscal requiere configurar ARCA y validar las reglas de la empresa con su contador**.
- Correo preparado como `.eml`, sin SMTP ni envío real. `X-Unsent: 1` sugiere borrador en clientes compatibles; no garantiza cómo lo abrirá cada cliente. Todas las direcciones son de ejemplo.
- Sin ejecución automática 24/7, tareas programadas o procesos de fondo. La app trabaja cuando se interactúa con ella y Community Cloud puede suspender una app inactiva.
- Sin persistencia local garantizada. Ningún CSV o PDF escrito en el servidor se usa como almacenamiento permanente. Los documentos se generan en memoria y el usuario conserva sus descargas.
- Sin APIs pagas, sin IA necesaria y sin integraciones externas. Fuentes PDF incluidas con ReportLab; sin imágenes o fuentes remotas obligatorias.

## Organización para ampliar después

`app.py` contiene cuatro bloques separados para que sea fácil enseñar y publicar sin muchos archivos:

1. **Dominio:** validación, dinero, evaluación de estado y aprobación idempotente.
2. **Adaptador CSV:** lectura, recuperación del historial, exportación y resumen.
3. **Salidas:** generación de PDF y preparación del `.eml` en memoria.
4. **Interfaz:** Streamlit, formularios y estado de sesión.

Una futura conexión real a Sheets puede convertirse en un adaptador que entregue los mismos datos validados. Una futura emisión fiscal debe ser un servicio independiente con requisitos confirmados por la empresa y su contador, almacenamiento durable, control de acceso, credenciales seguras e idempotencia transaccional. No basta con renombrar el PDF demo ni cambiar su banner. Esas conexiones **no están implementadas** en este prototipo.

## Ejecutar y probar localmente (opcional)

Con Python 3.11, desde la carpeta del proyecto:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Para repetir las pruebas incluidas, sin instalar pytest:

```bash
python -m unittest -v test_app.py
```

**Verificación realizada en esta versión:** 32 pruebas aprobadas con Python 3.12.14, Streamlit 1.55.0, pandas 2.3.3 y ReportLab 4.4.10. Cubren duplicados, importes inválidos, Decimal, aprobación explícita, segundo clic, reimportación del original, recuperación en sesión vacía, identidad del PDF reconstruido, conflictos sin sobrescritura, conservación del historial al cambiar de archivo, fallo de PDF sin procesamiento, CSV mal formado, separadores, estado procesado sin respaldo, escape de markup en PDF, protección de fórmulas CSV, adjunto exacto del `.eml`, fechas/email y agrupación mensual. Se conservaron las 19 pruebas anteriores y se agregaron 13. Las nuevas cubren corrección de ID duplicado, importe con coma decimal, rechazo de un ID ya usado, bloqueo de filas procesadas o conflictivas, bloqueo de IDs que sólo existen en el historial, validación sin cambios parciales, recuperación de correcciones y conservación del PDF, y aprobación obligatoria tras corregir. En total, seis pruebas ejercitan la interfaz con `streamlit.testing.v1.AppTest`: las tres pestañas y el flujo de corrección/aprobación, error y reintento de una corrección, exclusión de ventas con comprobante, limpieza de una aprobación anterior, aprobación y reinicio con confirmación, y restauración del registro. La extracción de texto PDF tiene una comprobación adicional si está instalado pypdf; no es dependencia de la app.

En la primera versión se generó y revisó visualmente un PDF de ejemplo. El generador PDF y el correo no cambiaron; las pruebas de regresión vuelven a verificar su contenido, reconstrucción y adjunto.

**Verificación adicional de publicación (15/09/2026):** las 32 pruebas también pasaron con Python 3.11. La app se desplegó en Community Cloud con esa versión. En un navegador real se verificaron las tres pestañas, la corrección de ID e importe, la aprobación, la descarga de PDF/correo/CSV y la recuperación del mismo PDF (comparación byte por byte) desde una sesión nueva. Se probaron las tres pestañas a 390 × 844 sin desborde horizontal. El correo se descarga y contiene el PDF; su presentación como borrador depende del cliente de correo que uses. No se probó un envío porque esta app no envía correos.

El estado de sesión y sus límites están explicados en la [documentación oficial de Streamlit](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state).


## Publicación de esta demostración

App: https://loopian-planilla-demo.streamlit.app/

Repositorio: https://github.com/loopian-demo-ia/de-la-planilla-a-tu-app

La instancia de demostración pertenece a una cuenta de ejemplo independiente del alojamiento de Loopian y Milti. Podés copiar el código bajo licencia MIT y desplegarlo en tu propia cuenta. Publicada con Python 3.11. Las comprobaciones adicionales de producción se documentan en el material del video.
