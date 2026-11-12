# 06 — Backlog, mejoras de interfaz y plan de trabajo

## Pendientes que quedan para más adelante (2026-11-10)

| Pendiente | Quién | Nota |
|---|---|---|
| Revisión a oído de las canciones de SongMaker | usuario + programa | 6 de 62 revisadas (Tarantino, Goma de Mascar, Afortunadamente No Eres Tú, Natural, Lento, Koi no Uta). Seguir con las de LISA y Paty Cantú; el método: el usuario corrige tiempos, el programa mide el tono (`P`) y copia sus arreglos a los estribillos repetidos. Lista: `~/LetsSing/INFORME_SONGMAKER.md`, puntos dudosos con `N` en el editor |
| Corregir a mano tres de USDB: Goo Goo Dolls - Iris, P!nk - Who Knew, Paloma Faith - Only Love Can Hurt Like This | usuario + programa | descargadas de USDB el 2026-11-11 (IDs 15041, 4704, 31776) y ya en la Switch; el usuario las corrige en el editor de sincronía y después el programa mide el tono y copia los arreglos a los estribillos repetidos. Ojo: volver a descargarlas con usdb_syncer reescribe el txt y se pierden los arreglos |
| Calidad de los .bk2 con mucho movimiento | programa (con el sí del usuario) | medidos los 829 el 2026-11-12 (`~/LetsSing/analisis_bk2.json`): el bk2 copia el bitrate del origen (211–4.859 kbps; 99 por debajo de 1.200) con tope de 80 MB (35 de las 44 topadas son de la tanda del 10-nov); Bink rinde menos que AV1/VP9 y hay un paso intermedio que pierde calidad. Opción elegida para más adelante: **720p con más bitrate (~4.500 kbps, ~140 MB) y sin el paso intermedio**; antes, prueba con una canción (Party Rock Anthem) para verla en la tele y comprobar que la consola no se resiente (reintentar, sincronía). Ningún .bk2 se toca sin confirmación; el actual se guarda |
| LISA - Cobra | usuario | corregidos solo los primeros segundos (el resto es rap); terminarla a mano cuando tenga tiempo, luego medir el tono y marcarla revisada |
| Notas que se alargan sobre la reverberación («no» de Tarantino, «face») | programa | arreglado a mano en Tarantino; propuesto aplicarlo a las demás de SongMaker antes de revisarlas (esperando el sí) |
| Let's Sing 2027 | usuario | cuando lo compre: IDs del juego y de sus DLC (International Hits, Mit Deutschen Hits, Français et International) desde DBI; ver si el formato es el de 2026 antes de activarle modo Feat, idiomas e IDs de juego |
| Commit 98787ac en GitHub | usuario | reescrito como 5413561; pedir a GitHub Support que purgue el SHA viejo (también aparece en el PR #35 del original) |

## 0. Estado al 2026-11-01

Las fases 1 a 4 y 6 del plan están hechas (bugs B-01…B-45 cerrados; ver [09_HISTORIAL_BUGS.md](09_HISTORIAL_BUGS.md)).
El resto del documento es el plan original del 2026-10-21, que se conserva como referencia.

| ID | Estado | Nota |
|---|---|---|
| M-01 | Hecho | `tests/test_conversion.py` (51 pruebas, `unittest`) |
| M-02 | Hecho | resumen ok/omitidas/fallidas con motivo en el log y estado por canción en la tabla |
| M-03 | Parcial | `tools/validate_patch.py` revisa el parche; las canciones se validan al convertir (`SongError` con motivo) |
| M-04 | Pendiente | duetos: el parser solo toma P1 |
| M-05 | Hecho (2026) | idioma, género, dificultad, voz y año reales; solo en Let's Sing 2026 |
| M-06 | Hecho | `_atomic_write_text` |
| M-07 | Pendiente | la CLI no expone hilos, vaciar salida, forzar ni `--dry-run` |
| M-08 | Pendiente | `SyncModel.py` ya separa la lógica del editor; falta el resto |
| M-09 | Pendiente | |
| M-10 | Pendiente | la capa `language` del vxla sigue en `english` (el idioma real va en `songs_xx.json`) |
| M-11, M-12 | Pendiente | |
| M-13 | Hecho | columna Sinc. + `tools/sync_scan.py` |
| G-01…G-05 | Hecho | modelo/vista con escaneo en fondo, i18n completa, columna Estado, convertir marcadas, menú contextual por fila |
| G-06 | Hecho | formulario en apartados 1–5 |
| G-07 | Hecho | editor nuevo (carril de notas, cortes, ajustar a la voz, atajos, `.bak`) |
| G-08 | Hecho | `QPlainTextEdit` con límite, colores, panel redimensionable |
| G-09 | Hecho | iconos Tabler |
| G-10 | Pendiente | vista de detalle de canción |
| G-11 | Hecho | tamaño, posición y columnas en `QSettings` |
| G-12 | Parcial | progreso con ETA; sin fase por canción |
| G-13 | Hecho | Ctrl+F, F5, Ctrl+Enter, Esc |
| G-14 | Pendiente | `Guide.md` solo en inglés |

## 1. Plan por fases (propuesto)

Cada fase es un conjunto de commits pequeños y probables por separado.

### Fase 1 — Arreglos rápidos y seguros (≈ 1 sesión)
Cambios de pocas líneas, riesgo bajo, impacto alto.
- B-01 validación (indentar `return`)
- B-21 `log_message` → `log`
- B-22 columna de orden 7 → 8
- B-23 restaurar `ExtendedSelection`
- B-03 `utf-8-sig` al leer JSON
- B-07 división por cero en tono
- B-16 búsqueda de ffprobe
- B-18 ruta de `config.yml`
- B-19 cargar multihilo/hilos desde config
- B-35, B-36, B-43 (menores)
- Añadir a `config_default.yml` las claves que faltan

### Fase 2 — Integridad de la salida (lo que puede colgar la consola o mezclar canciones)
- B-02 temporal por canción
- B-04 orden registrar/copiar + año tolerante
- B-05 lock único para JSON/TSV/name.txt + deduplicación
- B-10 fallback mp4 real en XML
- B-09 / B-28 nombres de intermedios centralizados (constante única) + Clear cache completo
- B-15 comprobaciones previas con mensajes claros
- B-24 / B-45 fin de conversión, Stop real, cierre seguro

### Fase 3 — Elegir bien las fuentes y la caché
- B-08 `resolve_sources()` (usa `#AUDIO/#MP3/#VIDEO/#COVER`, ordena, excluye generados)
- B-12 / B-13 caché con firma de parámetros
- B-11 tamaño máximo en bk2
- B-14 aceptar `.bk2`/`.mpeg`/`.m4v`/`.mov`
- B-29 parser tolerante (+ P1 en duetos)
- B-30 módulo `naming.py` único + detección de colisiones

### Fase 4 — Calidad musical
- B-06 corrección de tono por octavas
- B-40 tildes en letras (tras verificar con vxla oficial)
- B-26 Sync Editor correcto (audio, VIDEOGAP, codificación)
- B-39 caché negativa de Genius / modo sin conexión

### Fase 5 — Interfaz gráfica (sección 3)

### Fase 6 — Herramientas, build y repositorio
- B-31, B-32, B-33, B-34 → un único lector de vxla
- B-41 build verificado; B-42 requirements mínimos y `.gitignore`
- B-37 logging; B-38 imports perezosos; B-44 binkc robusto
- ~~Ordenar scripts sueltos~~ hecho 2026-11-01: los útiles están en `tools/` con parámetros, los viejos se quitaron

## 2. Backlog funcional

| ID | Prioridad | Mejora | Notas |
|---|---|---|---|
| M-01 | Alta | Pruebas automatizadas (`pytest`) | parser, name_id, tono, registro JSON/TSV con hilos, validación GUI; usar `test_input/` |
| M-02 | Alta | Resumen al final de la conversión | tabla OK / omitidas / con error y motivo; botón "copiar informe" |
| M-03 | Alta | Validador previo ("Revisar canciones") | detecta antes de convertir: sin audio, sin portada, BPM inválido, año inválido, IDs duplicados, notas mal formadas |
| M-04 | Media | Soporte de duetos | ver rama `upstream/18-add-support-for-duets` |
| M-05 | Media | Metadatos reales en JSON | `#LANGUAGE`, `#GENRE`, `#EDITION`, `#YEAR`; `gender`, `difficulty`, `theme` editables por canción |
| M-06 | Media | Escritura atómica de JSON/TSV/name.txt | temporal + `os.replace`, evita `Extra data` (B-03) |
| M-07 | Media | CLI completa | flags para multihilo, clear output, force reconvert, idioma de logs, `--dry-run` |
| M-08 | Media | Separar lógica y GUI | `services/` (escaneo, conversión, config) sin Qt; GUI solo vista |
| M-09 | Media | Exportar parche listo para copiar | zip o carpeta `atmosphere/contents/<TitleID>/romfs` con instrucciones |
| M-10 | Baja | Idioma del vxla según la canción | hoy `language="english"` fijo |
| M-11 | Baja | Catálogo de DLC editable | importar desde `raw_data.xlsx` o editar en la GUI; añadir nuevas ediciones sin tocar código |
| M-12 | Baja | Normalización de sonoridad medida | `loudnorm` de 2 pasadas con `linear=true` (no altera tiempos) o ganancia fija calculada; ver R-10 |
| M-13 | Baja | Detección de desfase integrada | **Hecho**: columna Sinc. + `tools/sync_scan.py` (apartado 5 de la GUI) |

## 3. Mejoras de la interfaz gráfica

Estado actual: ventana 1400×800 con panel izquierdo (formulario largo) y derecho (tabla + log de 150 px); mezcla de inglés y español;
iconos genéricos dibujados a mano (círculo/cuadro/cruz); botones por celda; sin resumen de resultados.

| ID | Prioridad | Mejora | Detalle |
|---|---|---|---|
| G-01 | Alta | Respuesta fluida | escaneo en segundo plano + modelo/vista (`QAbstractTableModel` + delegados) en lugar de 2 `QPushButton` por fila; refresco por fila durante la conversión (B-25) |
| G-02 | Alta | i18n completa | todos los textos con `tr()` (tooltips, tabla, leyenda, diálogos, logs, SyncEditor); idioma guardado y restaurado; cambio en caliente; idioma por defecto según el sistema (B-20) |
| G-03 | Alta | Estado por canción en la tabla | columna "Estado" (pendiente / convirtiendo / OK / error) con tooltip del motivo; filtro "solo con errores" |
| G-04 | Alta | Convertir solo lo marcado | hoy los checkboxes solo sirven para Clear cache; permitir "Convertir seleccionadas" |
| G-05 | Media | Selección vs. marcado | separar "seleccionar fila" de "marcar checkbox" (hoy un clic en la fila alterna la marca); menú contextual por fila: abrir carpeta, Fix Sync, limpiar caché, ver txt |
| G-06 | Media | Formulario por pasos | 1) Juego y DLC, 2) Herramientas (con botón "Detectar"), 3) Carpetas, 4) Opciones; indicador ✓/✗ por sección; mostrar la ruta de salida **final** (con `_Patch`) |
| G-07 | Media | Sync Editor renovado | forma de onda del audio con las notas superpuestas; ajuste ±10/±50/±250 ms con teclado; vista previa del VIDEOGAP; deshacer; guardado respetando la codificación |
| G-08 | Media | Panel de log mejor | `QPlainTextEdit` con límite, colores por nivel, filtro por nivel, botón "abrir error.log", panel redimensionable (`QSplitter`) |
| G-09 | Media | Iconos y tema | iconos reales (pytablericons ya está en dependencias y no se usa) o SVG propios; `qdarktheme` aplicado de verdad o quitarlo; no acumular hojas de estilo al cambiar de tema |
| G-10 | Media | Vista de detalle de canción | panel lateral al seleccionar: portada, duración, BPM/GAP/VIDEOGAP, archivos detectados (fuente y caché), name_id, avisos |
| G-11 | Baja | Ventana adaptable | tamaño inicial relativo a la pantalla, recordar tamaño/posición y anchos de columna (`QSettings`) |
| G-12 | Baja | Barra de progreso más informativa | canción actual, fase (audio/video/bk2/vxla), ETA por fase; icono en barra de tareas |
| G-13 | Baja | Accesibilidad | atajos (Ctrl+Enter convertir, Esc parar, F5 refrescar, Ctrl+F buscar), orden de tabulación, textos alternativos |
| G-14 | Baja | Ayuda integrada | Guide.md traducida, enlaces a cada sección desde los tooltips "?" |

## 4. Riesgos a tener en cuenta al arreglar

- **Cambiar name_id** vuelve a renombrar toda la caché y cambia IDs ya instalados en la consola (puntuaciones/favoritos ligados al ID,
  canciones duplicadas al fusionar con JSON base anteriores). Cualquier cambio debe ser compatible hacia atrás o venir con migración.
- **Cambiar el formato del vxla o la corrección de tono** no se aplica a canciones ya cacheadas hasta implementar B-13 (o forzar).
- **Probar en consola real** cualquier cambio en JSON/TSV/name.txt/vxla: los errores de formato pueden colgar el juego.
- Mantener la compatibilidad Windows (rutas `\`, `.exe`, sin Wine) cuando se toque código de Linux/Wine.
