# 03 — Registro de bugs

Registro abierto con la auditoría del commit `4e1cb35` (las líneas del detalle de B-01…B-45 son de ese commit; el
estado de cada bug está en la tabla). "Evidencia" = verificado con prueba, con `error.log`, o por lectura directa del código.

## Resumen

| ID | Sev. | Área | Título | Estado |
|---|---|---|---|---|
| B-01 | CRÍTICO | GUI | La validación de campos antes de convertir está desactivada | CERRADO (7fc2657) |
| B-02 | ALTO | Conversión | Portadas mezcladas entre canciones con multihilo (archivo temporal compartido) | CERRADO (30669e3) |
| B-03 | ALTO | Conversión | JSON del DLC con BOM no se puede leer → canciones descartadas | CERRADO (30669e3) |
| B-04 | CRÍTICO | Conversión | Registro en name.txt/JSON/TSV antes de copiar medios; año no numérico rompe a mitad | CERRADO (30669e3) |
| B-05 | ALTO | Conversión (XML) | Carrera entre hilos al escribir SongsDLC.tsv y name.txt | CERRADO (30669e3) |
| B-06 | ALTO | Tono | Corrección "fast": +48 a canciones agudas y transposiciones que no son octavas | CERRADO (8426e7e) |
| B-07 | MEDIO | Tono | División por cero en canciones sin notas normales/doradas | CERRADO (8426e7e) |
| B-08 | ALTO | Conversión | Elección de archivos fuente arbitraria: ignora #MP3/#COVER y toma archivos generados | CERRADO (30669e3) |
| B-09 | MEDIO | Caché | Filtro `_cover.mp4` obsoleto: el video estático cacheado cuenta como video fuente | CERRADO (30669e3) |
| B-10 | ALTO | Conversión (XML) | En XML se copia un AVI con extensión .mp4 | CERRADO (30669e3) |
| B-11 | MEDIO | Video (JSON) | "Max video size" no se aplica a los .bk2 | CERRADO (b9d454f: tasa /D de Bink restaurada, ver B-47) |
| B-12 | MEDIO | Caché | "Still video" contamina la caché (XML) o se ignora (JSON) | CERRADO (30669e3) |
| B-13 | MEDIO | Caché | El vxla no se regenera al cambiar formato/tono/medley | CERRADO (30669e3) |
| B-14 | MEDIO | Video (JSON) | Videos fuente .bk2/.mpeg/.m4v se ignoran → video estático | CERRADO (30669e3) |
| B-15 | MEDIO | Conversión | Excepciones opacas sin audio, sin imagen o con ffprobe vacío | CERRADO (30669e3) |
| B-16 | BAJO | Rutas | ffprobe se busca como `ffprobe.exe` también en Linux | CERRADO (30669e3) |
| B-17 | MEDIO | Salida | Escudo `_Patch`: `isfile` relativo al CWD y doble anidado `_Patch/_Patch` | CERRADO (30669e3 + 7fc2657) |
| B-18 | ALTO | Config | config.yml se guarda en el CWD pero se lee de la carpeta de la app | CERRADO (7fc2657) |
| B-19 | MEDIO | GUI/Config | Multihilo y nº de hilos no se cargan; al guardar se pisan | CERRADO (7fc2657) |
| B-20 | MEDIO | GUI/i18n | Idioma no se restaura; textos mezclados; clave española en modo inglés | CERRADO (7fc2657 + revisión 2026-10-31: 0 textos sin traducir) |
| B-21 | ALTO | GUI | `self.log_message` no existe → excepción en Fix Sync y Play | CERRADO (7fc2657) |
| B-22 | BAJO | GUI | Volver al "orden original" ordena por la columna Lyrics | CERRADO (7fc2657) |
| B-23 | BAJO | GUI | Tras convertir se pierde la selección múltiple | CERRADO (7fc2657) |
| B-24 | MEDIO | GUI | Stop/error informan "finished successfully"; Stop no detiene ffmpeg; pkill global | CERRADO (30669e3 + 7fc2657) |
| B-25 | ALTO | GUI/Rendimiento | Escaneo completo repetido (parsea todos los txt) incluso durante la conversión | CERRADO (7fc2657) |
| B-26 | MEDIO | Sync Editor | Audio equivocado, ignora VIDEOGAP, guardado con codificación incorrecta | CERRADO (7fc2657) |
| B-27 | BAJO | GUI | Play reproduce el primer .ogg (puede ser la preview) | CERRADO (7fc2657) |
| B-28 | MEDIO | Caché | "Clear cache" no borra los intermedios `.avi` ni `_cover.avi` | CERRADO (7fc2657) |
| B-29 | MEDIO | Parser | Notas sin sílaba revientan; tags sensibles a mayúsculas; duetos mezclados | CERRADO (cd87f8d) |
| B-30 | MEDIO | IDs | name_id: colisiones, ID vacío, 6 implementaciones divergentes | CERRADO (30669e3 + 1b437ba: un solo módulo naming.py, colisiones detectadas) |
| B-31 | MEDIO | Tools | Recover cache no encuentra el romfs correcto en XML ni IDs nuevos | CERRADO (b779bc6) |
| B-32 | ALTO | Tools | Tools → Unpack está roto (NameError) y genera tiempos erróneos | CERRADO (27f8a17) |
| B-33 | BAJO | Tools | reverse_vxla: NameError `name_id` | CERRADO (27f8a17) |
| B-34 | BAJO | Tools | ExtractorPro no lee vxla propios; espacios mal detectados | CERRADO (27f8a17) |
| B-35 | BAJO | Datos | `DlcRepository.init` falla en BD nueva | CERRADO (DROP TABLE IF EXISTS; prueba DlcRepositoryTest) |
| B-36 | BAJO | GUI | Regex de TitleID laxa | CERRADO (7fc2657) |
| B-37 | MEDIO | Logging | error.log en el CWD; spam DEBUG de librerías; log sin límite | CERRADO (30669e3) |
| B-38 | MEDIO | Tono | Importación pesada de TensorFlow al cargar; Demucs no funciona empaquetado | CERRADO (8426e7e) |
| B-39 | MEDIO | Rendimiento | Genius sin caché negativa: segundos de espera por canción sin conexión | CERRADO (cd87f8d) |
| B-40 | MEDIO | Calidad | Las letras pierden tildes y ñ | CERRADO (cd87f8d) — confirmar en consola |
| B-41 | ALTO | Build | El `.spec` excluye QtMultimedia, que la GUI importa | CERRADO (7fc2657; build de PyInstaller probado en Linux 2026-11-01: la GUI arranca) |
| B-42 | MEDIO | Repo | requirements.txt y build.yml no versionados; requirements inutilizable | CERRADO (4c68038: instalación limpia probada) |
| B-43 | BAJO | Código muerto | `rename_folders_physically` con `return` en lugar de `continue` | CERRADO (30669e3) |
| B-44 | MEDIO | Wine/Bink | binkc sin timeout ni diagnóstico; `wine` fijo | CERRADO (30669e3) |
| B-45 | MEDIO | GUI | Cerrar la ventana con la conversión en marcha deja hilos vivos | CERRADO (7fc2657) |
| B-46 | CRÍTICO | Letras | Letras con acentos/apóstrofes **borradas** si aparecen después de los primeros 4 KB del txt | CERRADO (cd87f8d) |
| B-47 | MEDIO | Video | "Max video size" sin efecto: binkc no recibía la tasa `/D` (R-11) | CERRADO (b9d454f) |
| B-48 | ALTO | Tools/Caché | Copias del extractor con el ID del conversor tomadas como ya convertidas: portadas a tamaño completo en el parche, 28 GB de `.mp4` duplicados (R-12) | CERRADO (b9d454f + 1b437ba) |
| B-49 | MEDIO | Letras | Palabras pegadas a mitad de línea en canciones UltraStar ("sideto side"): el espacio de una nota sostenida `~ ` no pasaba a la letra | CERRADO (28276db, ajustado en 3eca0ac) |
| B-50 | ALTO | Letras | 112 de 224 vxla oficiales v2.0: toda la letra pegada ("We'retalkingaway"), se mostraba `lyrics_cut`, que no tiene espacios | CERRADO (3eca0ac) |
| B-51 | ALTO | Sync Editor | Las letras no aparecían nunca ("Aquí aparecerán las letras"): un atributo tapaba el método `lyrics_offset_s` (desde `b074be4`) | CERRADO (d412df5) |
| B-52 | ALTO | Datos | El idioma de todas las canciones salía "English" (fijo en el código): el filtro por idioma del juego no servía | CERRADO (aa33a0e, e4aeb93; solo 2026) |
| B-53 | ALTO | Portadas | 79 canciones con la portada de otra (una por artista, de un script anterior) | CERRADO (aa33a0e: tools/fix_covers.py) |
| B-54 | ALTO | Letras | Caracteres rotos ("Ã©", "Â«") en letras oficiales: archivos UTF-8 que declaran Windows-1252 | CERRADO (e4aeb93) |
| B-55 | MEDIO | Datos | Género "Rap" no existe en 2026 (es "HipHop"); RnB/Latin/Country nunca se usaban | CERRADO (7f89e26; solo 2026) |
| B-56 | ALTO | Orden | Lista "Título" del juego ordenada por artista: Let's Sing 2026 ordena por el ID y el nuestro empezaba por las iniciales del artista | CERRADO (7f89e26: ID de juego título primero, solo 2026) |
| B-57 | MEDIO | Datos | 240 canciones de DLC con el año del DLC (2020) en vez del de la canción | CERRADO (7f89e26: tools/fix_years.py) |
| B-58 | MEDIO | Portadas | Portadas del megapack en blanco, fotogramas borrosos o de recopilatorios | CERRADO (7f89e26: fix_covers --blank/--dlc) |
| B-59 | BAJO | Biblioteca | Swish Swish duplicada (normal y Album Version) | CERRADO (movida a archivo/duplicados_quitados) |
| B-60 | BAJO | Herramientas | Los registros de los servicios no se vaciaban al relanzar (systemd "file:") | CERRADO (usar "truncate:") |
| B-61 | ALTO | GUI | La ventana se congeló una vez (hilo principal bloqueado, con el video de BBHMM abierto) | ABIERTO (vigilante hang_trace.log en 6e74b01) |
| B-62 | MEDIO | Switch | DBI no sobrescribe archivos por MTP ("Access denied") | CERRADO (e4aeb93: borrar ya respaldado y copiar) |
| B-63 | ALTO | usdb_syncer | Su carpeta de canciones seguía en el disco dañado | CERRADO (configuración corregida) |
| B-64 | MEDIO | Herramientas | Detener sync_scan dejaba el informe solo con lo revisado en esa pasada | CERRADO (81eadc3) |
| B-65 | MEDIO | Caché | Un `.bk2` se volvería a codificar si usdb_syncer renombra la carpeta | CERRADO (81eadc3) |
| B-66 | ALTO | Video | 28 canciones con la portada fija como `.bk2` aunque tienen su videoclip | CERRADO (5b0e377: 27 recodificadas desde los video.mp4 del usuario, Merry Christmas con su .bk2 oficial, Maria y Something About Us con videoclip alineado) |
| B-67 | ALTO | Switch | La SD se llenó copiando el parche nuevo junto al viejo; carpetas sin crear tras vaciarla | CERRADO (429f0a7, b1b09cb) |
| B-68 | MEDIO | Switch | Copias por MTP cortadas por fallos sueltos de DBI | CERRADO (135db90: reintentos) |
| B-69 | ALTO | Mod | El mod cerraba el juego: faltaban llamadas al sistema en main.npdm | CERRADO (2be952a) |
| B-70 | MEDIO | Audio | Vista previa en el intro (segundo 60 fijo) | CERRADO (5083880: desde el coro) |
| B-71 | MEDIO | Sincronía | Something About Us con la letra 1,08 s tarde | CERRADO (2be952a) |
| B-72 | MEDIO | Letras | La búsqueda de estribillos en Genius no lee cabeceras con nombres enlazados ("[Coro: Luis Fonsi," partida en líneas): 75 canciones con página y sin estribillos | CERRADO (a16d166: 72 releídas, 51 con estribillos) |
| B-73 | ALTO | Feat | El modo Feat cerraba el juego: faltaba vxla_feat y todas decían "coopfriendly": "Coop" sin segunda voz | CERRADO (4c02966; solo 2026) |
| B-74 | ALTO | usdb_syncer | usdb_syncer no marcaba ninguna canción descargada: la carpeta se guardó como texto y la ignoraba | CERRADO (configuración; 271 reconocidas) |
| B-75 | MEDIO | SongMaker | Letras pegadas y palabras donde no se canta en las canciones fabricadas (Goma de Mascar) | EN CURSO (notas hechas 2026-11-05; falta la colocación de la letra) |

---

## Detalle

### B-01 · CRÍTICO · Validación desactivada
- **Dónde**: [Gui.py:1178-1188](../Gui.py#L1178-L1188) `required_fields_missing.req`
- **Causa**: el `return` quedó fuera del `if not line_edit.isEnabled():` → la función sale siempre en la primera línea.
- **Impacto**: se puede iniciar la conversión con FFmpeg/RAD/entrada/salida vacíos o inválidos; el fallo aparece más tarde y peor
  (p. ej. salida vacía → `_Patch` en el CWD).
- **Origen**: regresión de `5f0d14e` (en `upstream/main` está bien indentado). Ver R-01.
- **Arreglo**: indentar el `return` dentro del `if`.

### B-02 · ALTO · Portadas mezcladas con multihilo
- **Dónde**: [ConvertFiles.py:273-291](../ConvertFiles.py#L273-L291) `get_clean_image_path`
- **Causa**: todas las llamadas escriben `tempfile.gettempdir()/temp_cover_clean.jpg`. Con 5 hilos (config actual), el hilo A
  escribe su portada, el hilo B la sobrescribe antes de que ffmpeg de A la lea.
- **Impacto**: portadas, `_long`, `_InGameLoading` y videos estáticos de **otra canción**. Además quedan en caché y se repiten.
- **Origen**: `4e1cb35` (R-02).
- **Arreglo**: archivo temporal único por llamada (`NamedTemporaryFile(delete=False)` o `mkstemp`) y borrarlo tras ffmpeg;
  mejor aún, generar la portada limpia una sola vez por canción y reutilizarla.
- **Relacionados**: B-08 (qué imagen se elige).

### B-03 · ALTO · JSON con BOM
- **Dónde**: [ConvertFiles.py:503](../ConvertFiles.py#L503), [ConvertFiles.py:508](../ConvertFiles.py#L508)
- **Evidencia**: 106 × `Unexpected UTF-8 BOM (decode using utf-8-sig)` en `error.log`; 119 × `Extra data` (JSON destino corrupto
  de ejecuciones anteriores con `clear_output: false`).
- **Arreglo**: leer con `encoding='utf-8-sig'`; si el JSON destino es inválido, registrar un error claro y no seguir añadiendo
  canciones (hoy cada canción falla por separado). Escribir de forma atómica (archivo temporal + `os.replace`).

### B-04 · CRÍTICO · Registro antes de copiar; año no numérico
- **Dónde**: [ConvertFiles.py:858-889](../ConvertFiles.py#L858-L889); `int(year)` en [ConvertFiles.py:459](../ConvertFiles.py#L459) y [ConvertFiles.py:553](../ConvertFiles.py#L553)
- **Causa**: primero se añade el ID a `name.txt`, luego al JSON/TSV y **después** se copian los medios. Si algo falla entre medio
  (p. ej. `#YEAR:1985-03`, `#YEAR:` vacío, copia sin espacio), la canción queda registrada sin archivos o en `name.txt` sin metadatos.
- **Impacto**: el juego encuentra un ID sin medios → riesgo de cuelgue de la consola al abrir el menú.
- **Arreglo**: parsear el año con tolerancia (`re.search(r'\d{4}')`, por defecto 2000); copiar primero los medios y registrar
  al final; si el registro falla, eliminar los medios copiados de esa canción.

### B-05 · ALTO · Carreras en TSV y name.txt (formato XML)
- **Dónde**: [ConvertFiles.py:520](../ConvertFiles.py#L520), [ConvertFiles.py:586](../ConvertFiles.py#L586)
- **Causa**: solo `add_song_to_json` usa `json_lock`. Con multihilo, dos hilos leen el TSV, calculan el mismo UID y uno pisa al otro.
- **Impacto**: UIDs duplicados, canciones perdidas en el TSV, líneas de `name.txt` intercaladas. Además el TSV se abre sin
  `encoding` (en Windows cp1252 → error con caracteres no latinos) y `name.txt` no se deduplica.
- **Arreglo**: un único lock de registro para JSON/TSV/name.txt; `encoding='utf-8'`; deduplicar IDs.

### B-06 · ALTO · Corrección de tono "fast"
- **Dónde**: [PitchAnalyzer.py:132-152](../PitchAnalyzer.py#L132-L152) (heredado de upstream)
- **Evidencia (prueba)**: notas 80/85/95 → corrección **+48** (quedan en 128–143, fuera de MIDI); notas 20/30/40 → **+41**
  (no es múltiplo de 12: cambia la tonalidad).
- **Arreglo**: elegir `k·12` que lleve la mediana del txt al centro del rango `[43, 81]` (≈62) y, si sobra, ajustar para que
  `min/max` entren; nunca desplazamientos fuera de octava. Opcional: aplicar la misma regla de octavas al modo slow.

### B-07 · MEDIO · División por cero en el tono
- **Dónde**: [PitchAnalyzer.py:89](../PitchAnalyzer.py#L89) — `total_pitch / note_count` con 0 notas `:`/`*` (canciones solo rap/freestyle).
- **Arreglo**: devolver valores neutros y corrección 0 si no hay notas cantadas.

### B-08 · ALTO · Archivos fuente equivocados
- **Dónde**: [ConvertFiles.py:713-717](../ConvertFiles.py#L713-L717), [ConvertFiles.py:735](../ConvertFiles.py#L735), [ConvertFiles.py:303-306](../ConvertFiles.py#L303-L306), [ConvertFiles.py:339-342](../ConvertFiles.py#L339-L342)
- **Causa**: `iterdir()` no está ordenado (el comentario "alfabéticamente el último" no se cumple); no se usan `#MP3`/`#AUDIO`,
  `#COVER`, `#VIDEO` salvo en un caso; las listas incluyen archivos generados (`<id>.ogg`, `<id>_preview.ogg`, `<id>.png`,
  `<id>_long.png`, `<id>.avi`, `_cover.avi`…).
- **Impacto**: la preview puede generarse desde el `.ogg` ya desplazado o desde la propia preview; portada desde `_InGameLoading.png`;
  txt de dueto o un txt ajeno (licencia, notas) tomado como letra.
- **Arreglo**: función única `resolve_sources(song_dir, txt_data)` que: elige el txt (ordenado, prefiere el que no sea `[MULTI]`/dueto
  y que tenga `#TITLE`), usa las etiquetas `#AUDIO`→`#MP3`, `#VIDEO`, `#COVER`, excluye todos los nombres generados y solo después
  cae a heurísticas. Reutilizarla en Gui (iconos, Play, Fix Sync).

### B-09 · MEDIO · Filtro `_cover.mp4` obsoleto
- **Dónde**: [ConvertFiles.py:751](../ConvertFiles.py#L751), [Gui.py:865](../Gui.py#L865)
- **Causa**: `4e1cb35` cambió el fallback a `_cover.avi` y el intermedio JSON a `<id>.avi`, pero los filtros siguen buscando `_cover.mp4`.
- **Impacto**: en ejecuciones posteriores el video estático o el intermedio cuentan como "video fuente" (icono ✓ falso, conversión del
  estático como si fuera video real). Ver R-02.

### B-10 · ALTO · AVI con extensión .mp4 en formato XML
- **Dónde**: [ConvertFiles.py:819-830](../ConvertFiles.py#L819-L830)
- **Causa**: el fallback estático es `_cover.avi` y para XML se **copia** tal cual como `<id>.mp4`.
- **Impacto**: juegos 2018–2023 reciben un contenedor AVI con nombre `.mp4` → video negro o cuelgue. Regresión de `4e1cb35` (R-02).
- **Arreglo**: generar el fallback en `.mp4` para XML y en `.avi` solo como intermedio para binkc, o remuxear (`-c copy`) a mp4.

### B-11 · MEDIO · Tamaño máximo ignorado en .bk2
- **Dónde**: [ConvertFiles.py:775-787](../ConvertFiles.py#L775-L787), [ConvertFiles.py:384](../ConvertFiles.py#L384)
- **Causa**: el AVI intermedio usa el bitrate **original**; `compression_percentage` se calcula pero `create_video_bink` no lo usa.
- **Arreglo**: limitar el bitrate del intermedio a `target_size_mb` y pasar la tasa de datos a binkc (`/D<bytes/s>` o el
  parámetro de compresión que corresponda; verificar con la ayuda de `binkc`).

### B-12 · MEDIO · "Still video" y caché
- **Dónde**: [ConvertFiles.py:816-830](../ConvertFiles.py#L816-L830)
- **XML**: con still video se **sobrescribe** el `<id>.mp4` real; al desactivarlo, como existe, nunca se vuelve a generar.
- **JSON**: si ya existe `<id>.bk2` real, still video se ignora.
- **Arreglo**: nombres de caché distintos por variante (`<id>.mp4` vs `<id>_still.mp4`) y elegir cuál copiar según la opción.

### B-13 · MEDIO · Caché del vxla
- **Dónde**: [ConvertFiles.py:833-849](../ConvertFiles.py#L833-L849)
- **Causa**: solo compara mtime del vxla con el del txt.
- **Impacto**: cambiar XML↔JSON (capas distintas), método de tono, `no_medley` o el audio (duración) no regenera el vxla.
- **Arreglo**: guardar junto al vxla un sidecar (`<id>.vxla.meta.json`) con hash del txt + parámetros + versión del conversor
  y regenerar si difiere. Lo mismo, a futuro, para audio/video.

### B-14 · MEDIO · Formatos de video ignorados en JSON
- **Dónde**: [ConvertFiles.py:775](../ConvertFiles.py#L775) — solo `.avi .divx .mp4 .flv .mkv .webm`.
- **Impacto**: `.bk2` (p. ej. `test_input/GAYLE - abcdefu/Abc.bk2`), `.mpeg` → no se convierten y se usa el video estático.
- **Arreglo**: si la fuente ya es `.bk2` 1280×720, copiarla; ampliar a `.mpeg .mpg .m4v .mov`.

### B-15 · MEDIO · Excepciones opacas
- **Dónde**: `create_audio` [ConvertFiles.py:342](../ConvertFiles.py#L342) (`files_avi[0]` vacío), `get_duration` [ConvertFiles.py:200](../ConvertFiles.py#L200),
  `create_still_video_from_cover_image` [ConvertFiles.py:231](../ConvertFiles.py#L231) (`files_jpg[0]` vacío), `is_video_still_image` (duración 0).
- **Evidencia**: `IndexError: list index out of range` (5) y `could not convert string to float: b''` en `error.log`.
- **Arreglo**: comprobar requisitos al inicio de cada canción y registrar "falta audio/portada" en lugar de un traceback.

### B-16 · BAJO · ffprobe en Linux
- **Dónde**: [ConvertFiles.py:61](../ConvertFiles.py#L61) — prueba `ffprobe.exe` junto a ffmpeg; en Linux siempre usa el `ffprobe` del PATH.
- **Arreglo**: probar `ffprobe` y `ffprobe.exe` junto a ffmpeg, luego `shutil.which`.

### B-17 · MEDIO · Escudo `_Patch`
- **Dónde**: [ConvertFiles.py:73-79](../ConvertFiles.py#L73-L79), [Gui.py:620-626](../Gui.py#L620-L626)
- **Causa**: `os.path.isfile(file_or_folder)` usa el nombre sin ruta → mira en el CWD. El escudo se aplica en la GUI y otra vez
  en ConvertFiles: si `X/_Patch` contiene cualquier archivo no-TitleID (p. ej. un log), la salida pasa a `X/_Patch/_Patch`.
- **Arreglo**: una sola función `safe_output_dir(path)` en ConvertFiles, usada por ambos; `os.path.join(path, name)`;
  si la carpeta ya se llama `_Patch` no volver a anidar. Mostrar en la GUI la ruta final real.

### B-18 · ALTO · Ruta de config.yml
- **Dónde**: [Gui.py:1638](../Gui.py#L1638) escribe `Path('.')/config.yml`; [ConfigLoader.py:49](../ConfigLoader.py#L49) lee `app_dir()/config.yml`.
- **Impacto**: si la app se abre desde otra carpeta (acceso directo, ejecutable con otro CWD), los cambios no se guardan donde se leen
  y `self.cfg = load_config()` devuelve la config **antigua**, que es la que se usa para convertir.
- **Origen**: `5f0d14e`.
- **Arreglo**: `app_dir() / 'config.yml'`; mejor aún, construir el cfg de la conversión directamente desde el formulario.

### B-19 · MEDIO · Multihilo no se carga
- **Dónde**: [Gui.py:693-745](../Gui.py#L693-L745) no lee `multithreading`/`multithreading_workers`; [Gui.py:1630-1632](../Gui.py#L1630-L1632) sí los guarda.
- **Impacto**: config.yml dice `multithreading: true, workers: 5`, la GUI muestra desmarcado/3 y al convertir guarda `false`.

### B-20 · MEDIO · Idioma
- **Dónde**: `set_defaults` no llama a `i18n.load_language(cfg.language)`; [Gui.py:1471](../Gui.py#L1471) usa una clave en español;
  [Gui.py:1504](../Gui.py#L1504) etiqueta inicial en español; sin `tr()`: tooltips, cabeceras de tabla, leyenda, títulos "Input and Output folders",
  "Input folder preview", "Logs", acciones del menú Tools, buscador, mensajes del log, diálogos, todo SyncEditor.
- **Arreglo**: ver G-02 (i18n completo).

### B-21 · ALTO · `log_message` inexistente
- **Dónde**: [Gui.py:969](../Gui.py#L969), [Gui.py:1026](../Gui.py#L1026), [Gui.py:1031](../Gui.py#L1031), [Gui.py:1033](../Gui.py#L1033)
- **Impacto**: al cerrar el Sync Editor se lanza `AttributeError`; el `except` vuelve a llamar a `log_message` → excepción no
  controlada en el slot. Play sin audio igual.
- **Origen**: `5f0d14e` / `4cb04ff`. **Arreglo**: usar `self.log`.

### B-22 · BAJO · Orden original
- **Dónde**: [PreviewTable.py:150](../PreviewTable.py#L150) `sortItems(7)` → debe ser 8 (OrigOrder). Origen `4cb04ff`.

### B-23 · BAJO · Selección múltiple perdida
- **Dónde**: [Gui.py:1222](../Gui.py#L1222) `SingleSelection` → debe restaurar `ExtendedSelection`.

### B-24 · MEDIO · Fin de conversión, Stop
- **Dónde**: [Gui.py:1279](../Gui.py#L1279), [Gui.py:1317-1352](../Gui.py#L1317-L1352)
- **Evidencia (prueba)**: `QThread.finished` se emite siempre al terminar `run()`, también después de `error`.
- **Impacto**: tras un error o un Stop se muestra "Conversion finished successfully"; Stop no mata ffmpeg (las 2 pasadas siguen);
  `pkill -9 -f radvideo` mata procesos de otras apps; no hay resumen de canciones OK/fallidas.
- **Arreglo**: el worker emite `done(ok, stopped, resumen)`; registrar los `Popen` activos y terminarlos; resumen final.

### B-25 · ALTO · Escaneo repetido y caro
- **Dónde**: [Gui.py:825-961](../Gui.py#L825-L961), [Gui.py:994](../Gui.py#L994), [Gui.py:1094-1101](../Gui.py#L1094-L1101), [Gui.py:289](../Gui.py#L289)
- **Causa**: cada escaneo parsea **todos** los txt (chardet + parse) para el aviso de sync y crea 2 botones por fila; se escanea varias
  veces al arrancar (cada cambio de combo/validador) y en cada evento del watcher, **incluido durante la conversión**, que escribe
  constantemente en las carpetas vigiladas. Cada escaneo reconstruye la tabla y pierde marcas, orden y scroll.
- **Impacto**: con cientos de canciones la ventana se congela segundos de forma repetida.
- **Arreglo**: escaneo en hilo de fondo con caché por mtime de carpeta; pausar el watcher durante la conversión y refrescar
  solo la fila afectada al terminar cada canción (señal por canción); modelo/vista (`QAbstractTableModel`) en lugar de widgets por celda.

### B-26 · MEDIO · Sync Editor
- **Dónde**: [SyncEditor.py:36-44](../SyncEditor.py#L36-L44), [SyncEditor.py:205-252](../SyncEditor.py#L205-L252), [SyncEditor.py:254-275](../SyncEditor.py#L254-L275), [Gui.py:1024-1029](../Gui.py#L1024-L1029)
- **Problemas**: toma el primer `*.ogg` (puede ser `_preview.ogg` o el original sin desplazar); el `.ogg` convertido sí lleva
  VIDEOGAP aplicado pero las letras no lo suman → desfase visual = VIDEOGAP; el video se sincroniza 1:1 sin VIDEOGAP; guarda en UTF-8
  aunque el txt se leyó en otra codificación (falla en silencio con `print`); si no existe `#GAP:` no lo añade; `note[4]` sin control
  dentro de un timer de 50 ms; Gui usa `glob('*.txt')[0]` y ConvertFiles `files_txt[-1]` (pueden ser distintos); textos solo en español;
  no hay atajos de teclado ni ajuste fino (10 ms).
- **Relacionados**: B-08, R-03, G-07.

### B-27 · BAJO · Play
- **Dónde**: [Gui.py:967](../Gui.py#L967) — primer `*.ogg`/`*.mp3`; debe usar la fuente resuelta (B-08) o el `.ogg` convertido.

### B-28 · MEDIO · Clear cache incompleto
- **Dónde**: [Gui.py:896-898](../Gui.py#L896-L898) lista `outputs`; [Gui.py:844-846](../Gui.py#L844-L846) nombres de relleno `"yoyoyo"`.
- **Impacto**: tras limpiar, el `.bk2` se regenera desde el `<id>.avi` viejo y el video estático desde `_cover.avi` viejo
  (portada antigua). Tampoco borra `_genius_cache.json` ni `demucs_out/`.

### B-29 · MEDIO · Parser UltraStar
- **Dónde**: [UltrastarToSingit.py:60-78](../UltrastarToSingit.py#L60-L78), [UltrastarToSingit.py:170-174](../UltrastarToSingit.py#L170-L174)
- **Problemas**: `: 10 4 5` (sin sílaba) → `IndexError` en `note[4]`; `#bpm:` en minúsculas → `KeyError 'BPM'`; espacios dobles entre
  números rompen `split(" ", 4)`; `#RELATIVE:yes` no soportado; duetos `P1`/`P2` se mezclan en una sola voz;
  `#VERSION:1.x` (`#AUDIO`, `#START`/`#END`) no contemplado.
- **Arreglo**: parser tolerante (regex por tipo de línea, claves en mayúsculas, valores `strip()`), soporte de RELATIVE y elegir P1 en duetos.

### B-30 · MEDIO · name_id
- **Dónde**: [ConvertFiles.py:153](../ConvertFiles.py#L153) y copias.
- **Problemas**: colisión (`Ana Belén - Hoy` y `Alejandro Bueno - Hoy` → `ABhoy` los dos)
  → una canción pisa a la otra en caché y en el JSON; ID vacío o casi vacío con artista/título en alfabetos no latinos;
  `split(' - ')` con más de un separador descarta el resto del título. Las versiones de `tools/` no aplican el filtro ASCII
  de `0844bc6` → no encuentran los archivos (R-04).
- **Arreglo**: módulo único `naming.py`; detectar colisiones antes de convertir y añadir sufijo estable; fallback a hash corto
  si el ID queda vacío; mantener compatibilidad con los IDs ya publicados.

### B-31 · MEDIO · Recover cache
- **Dónde**: [tools/cache_recovery.py:9-29](../tools/cache_recovery.py#L9-L29) — `os.walk` se queda con el primer `romfs` (puede ser el del core);
  name_id antiguo; no recupera `_long`, `_InGameLoading`, `meta.xml`.

### B-32 · ALTO · Tools → Unpack roto
- **Dónde**: [tools/unpacker.py:102](../tools/unpacker.py#L102) usa `safe_artist`/`safe_title` no definidos → `NameError` en la primera canción.
- **Además**: escribe `#BPM:` con el BPM del JSON pero convierte segundos a beats con BPM 300 → tiempos erróneos;
  espera notas `sílaba,tono` mientras este conversor escribe `#p<tono>#.<sílaba>`.
- **Arreglo**: reutilizar la lógica de `LetSing_ExtractorPro`/`reverse_vxla` en un único módulo `vxla_reader.py`.

### B-33 · BAJO · reverse_vxla
- [tools/reverse_vxla.py:154-155](../tools/reverse_vxla.py#L154-L155) `name_id` no definido cuando hay video. Rutas fijas.

### B-34 · BAJO · LetSing_ExtractorPro
- [tools/LetSing_ExtractorPro.py:111](../tools/LetSing_ExtractorPro.py#L111) solo busca la capa `notes` (los vxla propios usan `notes_full`);
  [tools/LetSing_ExtractorPro.py:55-67](../tools/LetSing_ExtractorPro.py#L55-L67) compara `str(t2)` (`12.3`) con el atributo (`12.300`).

### B-35 · BAJO · DlcRepository.init
- [data/repository/DlcRepository.py:16](../data/repository/DlcRepository.py#L16) `drop table dlc` sin `IF EXISTS`.

### B-36 · BAJO · Regex de TitleID
- [Gui.py:275](../Gui.py#L275), [Gui.py:281](../Gui.py#L281) `[0-F]{16}` con `search`: acepta `:;<=>?@`, rechaza minúsculas.
  Usar `re.fullmatch(r'[0-9A-Fa-f]{16}')` y normalizar a mayúsculas.

### B-37 · MEDIO · Logging
- [ConvertFiles.py:39-43](../ConvertFiles.py#L39-L43): handler a `error.log` relativo al CWD, añadido al importar; root a DEBUG → la GUI
  recibe los mensajes DEBUG de urllib3/PIL/numba; `QTextEdit` sin límite de bloques (memoria y lentitud en conversiones largas).
- **Arreglo**: `logging` configurado una vez en el arranque, archivo en `app_dir()/logs/` con rotación, nivel INFO para librerías,
  `QPlainTextEdit` con `setMaximumBlockCount`.

### B-38 · MEDIO · TensorFlow al cargar
- [PitchAnalyzer.py:21](../PitchAnalyzer.py#L21): importa crepe/tensorflow al importar el módulo (cada conversión, también en modo fast).
- **Evidencia**: 362 × `No module named 'tensorflow'` en `error.log`.
- Demucs se lanza con `sys.executable -m demucs` (no existe en el ejecutable congelado) y deja `demucs_out/` en la carpeta de la canción.
- **Arreglo**: importación perezosa solo en modo slow; avisar una vez en la GUI si faltan dependencias.

### B-39 · MEDIO · Genius sin caché negativa
- [UltrastarToSingit.py:379-473](../UltrastarToSingit.py#L379-L473): si falla, no guarda nada → en cada ejecución repite hasta
  2 URL (5 s) + 3 búsquedas (10 s) + página (10 s) por canción. También se consulta en formato XML, donde la estructura no se escribe.
- **Arreglo**: cachear también "no encontrado" con fecha; opción "sin conexión"; sesión `requests.Session` reutilizada.

### B-40 · MEDIO · Tildes en las letras — A VERIFICAR
- [UltrastarToSingit.py:38-42](../UltrastarToSingit.py#L38-L42): `normalize_text` elimina todas las marcas diacríticas
  (`canción` → `cancion`, `año` → `ano`) aunque el vxla se escribe en Windows-1252, que sí las admite.
- **Verificar**: abrir un vxla oficial de los DLC en español/francés/alemán; si traen tildes, quitar el filtrado NFD y dejar solo
  los reemplazos tipográficos (opción configurable por si alguna edición del juego no tiene la fuente).

### B-41 · ALTO · Build sin QtMultimedia — A VERIFICAR
- `Lets Sing Ultrastar Converter.spec:13` excluye `PySide6.QtMultimedia`; [Gui.py:21](../Gui.py#L21) y SyncEditor la importan
  (añadida en el fork, `5f0d14e`/`4cb04ff`). El ejecutable generado con ese spec probablemente no arranca. Icono con ruta Windows (`assets\\logo.ico`).
- **Verificar**: construir con PyInstaller y abrir el binario.

### B-42 · MEDIO · Repo y dependencias
- `.gitignore` ignora `*.txt` y `*/` → `requirements.txt` y `.github/workflows/build.yml` **no están en git** (el commit `9ba81f4`
  y `pr_body.txt` dicen haberlo añadido). Sí se versionan `tools/__pycache__/*.pyc`.
- `requirements.txt` es un `pip freeze` con torch, CUDA, tf-nightly y keras-nightly (varios GB, versiones nightly) → no sirve para
  instalar la app básica.
- **Arreglo**: `requirements.txt` mínimo (PySide6, PyYAML, munch, requests, beautifulsoup4, chardet, Levenshtein, Markdown,
  pillow, pyqtdarktheme) + `requirements-slow.txt` opcional; corregir `.gitignore`.

### B-43 · BAJO · Código muerto con bug
- [ConvertFiles.py:119-120](../ConvertFiles.py#L119-L120) `return` dentro del bucle. Función sin uso: eliminar.

### B-44 · MEDIO · binkc bajo Wine
- [ConvertFiles.py:406-428](../ConvertFiles.py#L406-L428): `wine` fijo (sin `WINEPREFIX` ni ruta configurable), sin timeout
  (un binkc colgado bloquea un hilo para siempre), `capture_output` descartado.
- **Evidencia**: 38 × `Failed to generate ... from binkc` sin más información.
- **Arreglo**: registrar stdout/stderr y código de salida; timeout proporcional a la duración; validar tamaño mínimo del `.bk2`
  (README_Linux menciona `.bk2` vacíos de ~800 bytes); opción `wine_path`/`wine_prefix` en config.

### B-45 · MEDIO · Cierre con conversión activa
- `MainWindow` no tiene `closeEvent`: cerrar la ventana deja el QThread y el pool vivos.
- **Evidencia**: 5 × `RuntimeError: can't register atexit after shutdown` en `error.log`.
- **Arreglo**: `closeEvent` que pida confirmación, active `stop_event`, termine los procesos y espere al worker.

### B-46 · CRÍTICO · Letras borradas por la detección de codificación
- **Dónde**: `UltrastarToSingit.detect_encoding` / `parse_file` (antes de `cd87f8d`).
- **Causa**: chardet analizaba solo los primeros 4 096 bytes (cabecera + primeras notas, casi siempre ASCII) → devolvía
  `ascii` → el archivo se abría con `errors='ignore'` → **todo carácter no ASCII se eliminaba sin aviso**.
- **Evidencia (prueba)**: `J’ai été là garçon` en UTF-8 después de 4 KB → `Jai t l garon`. Si los acentos aparecían antes,
  chardet acertaba pero `normalize_text` igualmente quitaba las tildes (`ete`, `la`, `garcon`).
- **Impacto**: canciones en francés/español/alemán con letras rotas ("se ven todo mal"), apóstrofes perdidos.
- **Arreglo**: lectura del archivo completo, UTF-8 estricto → chardet (no occidental) → cp1252 → latin-1; nunca
  `errors='ignore'`. Las letras conservan todo lo que admite Windows-1252 (opción "Conservar tildes", activada por defecto).
  Al cambiar `VXLA_GENERATOR_VERSION` todos los vxla se regeneran solos en la próxima conversión (los videos no).

### B-47 · MEDIO · Tamaño de video ignorado por Bink
- **Dónde**: `ConvertFiles.create_video_bink` (desde `5f0d14e` hasta `b9d454f`).
- **Causa**: al reescribir la función para usar una carpeta temporal (rutas de Wine) se perdió el `/D<porcentaje>` del
  conversor original. El porcentaje se seguía calculando con "Max video size" y se pasaba, pero no se usaba.
- **Impacto**: los `.bk2` quedan con la tasa que elija binkc → parches más grandes y más carga para la consola.
- **Arreglo**: `/D` restaurado con el mismo cálculo que el original (100 si el intermedio ya cabe; si no, objetivo/tamaño,
  entre 1 y 200). Los `.bk2` ya hechos **no** se recodifican: solo afecta a los videos nuevos.

### B-48 · ALTO · Copias "de caché" del extractor
- **Dónde**: `tools/LetSing_ExtractorPro.py` (`362d058`), `tools/unpacker.py` (`1e04eba`), `tools/reverse_vxla.py`.
- **Causa**: el extractor copiaba cada medio dos veces: como fuente (`audio.ogg`, `video.mp4`, `cover.png`) y con el ID
  del conversor (`<id>.ogg`, `<id>.mp4`, `<id>.png`) "para la caché". `reverse_vxla` incluso dejaba las fuentes con el ID
  oficial, que suele ser el mismo del conversor.
- **Impacto** (medido el 2026-10-24 en `songs_custom`, solo lectura):
  - 596 portadas `<id>.png` de 512–1080 px tomadas como convertidas → iban al parche sin reducir a 256×256;
  - 583 `<id>.mp4` idénticos a `video.mp4` (28,15 GB) sin uso (todas esas canciones tienen su `.bk2`);
  - con `reverse_vxla`, el video fuente `<id>.mp4` se descartaba por llamarse como un archivo del conversor.
- **Arreglo**: el conversor rehace las imágenes en caché con tamaño distinto al del juego (`_image_has_size`); el
  extractor y `reverse_vxla` solo guardan fuentes con nombre genérico; un `.bk2` fuente lo copia el conversor tal cual.
  Las copias existentes no se borran: `~/rescate/excluir_copias_mp4.txt` permite no copiarlas al restaurar
  (`rsync --exclude-from`).

### B-49 · MEDIO · Palabras pegadas a mitad de línea en canciones UltraStar
- **Dónde**: `UltrastarToSingit.map_data`.
- **Causa**: cuando el espacio iba en una sílaba sostenida (`side` `~ ` `to`), la sílaba `~` se ocultaba y su espacio
  solo se guardaba en la lista interna de palabras, no en la capa `lyrics`.
- **Arreglo**: cada palabra termina con espacio y un espacio inicial pasa al final de la palabra anterior. Al final de
  línea **no** se añade: los vxla oficiales tampoco lo llevan (el juego muestra cada página por separado; comprobado
  en un oficial de 2024: las 60 uniones sin espacio caen justo en fin de página). Prueba: `LyricSpacesTest`.

### B-50 · ALTO · Letra entera pegada en canciones con vxla oficial v2.0
- **Dónde**: `OfficialVxla.to_sing_it` (desde `7b5a82a`).
- **Causa**: el texto visible se armaba con `lyrics_cut`, y en 112 de los 224 vxla v2.0 de la biblioteca esa capa no
  tiene ningún espacio (Take On Me: "We're" "tal" "king" "a" "way"). La capa `lyrics`, con los mismos tiempos, sí los
  tiene y es la que muestra el juego.
- **Arreglo**: el texto visible es la capa `lyrics` (como en los v3.0); `lyrics_cut` solo reparte sílabas a las notas.
  `VXLA_GENERATOR_VERSION = 5`. Prueba: `test_v2_shown_text_keeps_the_spaces_of_the_lyrics_layer`.
  Verificado en el parche completo: Take On Me → "We're talking away I don't know what…"; las uniones restantes
  dentro de una línea son sílabas en mayúsculas de una misma palabra (BOOM-BA-YAH, A-B-C de abcdefu).

### B-51 · ALTO · Sync Editor sin letras
- **Dónde**: `SyncEditor.py` (desde `b074be4`, soporte de #START).
- **Causa**: el valor `self.lyrics_offset_s` (desplazamiento por #START) tenía el mismo nombre que el método
  `lyrics_offset_s()`; el valor tapaba al método y cada refresco de la letra fallaba en silencio.
- **Arreglo**: editor rehecho (`start_offset_s` + `shift_s()`), con carril de notas, controles de reproducción
  (±5 s, ±0,1 s, líneas, primera letra, velocidad, volumen, línea de tiempo con clic), modo cantar con micrófono
  (YIN, cualquier octava cuenta como el juego), copia `.bak` al guardar y, en las canciones con vxla oficial, sus
  notas reales en modo solo lectura (el #GAP del txt no se usa ahí). Pruebas: `SyncEditorTest`.

### B-63 · ALTO · usdb_syncer apuntaba al disco dañado
- **Dónde**: configuración de usdb_syncer (`~/.config/bohning/usdb_syncer.conf`, `song_dir`), no el conversor.
- **Causa**: tras rescatar la biblioteca a `~/LetsSing/songs` (2026-10-24) usdb_syncer seguía con
  la carpeta `songs_custom` del disco externo dañado: no veía las canciones y descargaría a una ruta que ya no existe.
- **Arreglo**: `song_dir=~/LetsSing/songs` (copia `usdb_syncer.conf.antes_LetsSing_20261101`). usdb_syncer
  encuentra cada canción por su `.usdb` (recorre toda la carpeta), así que reconoce las 271 sin importar el nombre de
  la carpeta. Comprobado: el escáner del programa reconoce las 660 carpetas (271 de USDB + 389 de DLC/juegos).
- **A saber**: las 271 descargadas antes tienen sus medios con nombre genérico (`audio.ogg`, `video.mp4`,
  `cover.png`, R-12), no los que guarda su `.usdb`; si se vuelve a descargar una en usdb_syncer, este baja de nuevo
  audio/video, **reescribe el txt** (se pierden #GENRE/#YEAR/#COVER y los ajustes del Sync Editor de esa canción) y
  renombra la carpeta a "Artista - Título". Las canciones nuevas se convierten sin nada especial
  (`SourcesTest.test_usdb_syncer_folder`).

### B-64 · MEDIO · Detener la revisión de sincronía dejaba el informe a medias
- **Dónde**: `tools/sync_scan.py`.
- **Causa**: el informe se reescribía después de cada canción solo con las revisadas en esa pasada: al detenerla
  (o con `--song`) se perdían las filas de las demás.
- **Arreglo**: las filas anteriores se conservan hasta que su canción se revisa otra vez y el archivo se escribe
  completo en un `.tmp` y se reemplaza de una vez. Comprobado deteniéndola a los 3 segundos: informe idéntico.

### B-65 · MEDIO · Un .bk2 se volvería a codificar si usdb_syncer renombra la carpeta
- **Dónde**: `ConvertFiles.adopt_legacy_cache`.
- **Causa**: el `.bk2` de la caché se llama con el ID de la carpeta; usdb_syncer renombra la carpeta a su plantilla al
  volver a descargar una canción (p. ej. una corregida con `rename_songs.py`) y el `.bk2` con el ID viejo no se usaba.
- **Arreglo**: si falta `<id>.bk2` y en la carpeta hay **un solo** `.bk2`, se reutiliza (enlace duro o copia; el
  original se queda). Con dos o más no se adivina. Prueba: `test_renamed_folder_keeps_its_converted_video`.

### B-66 · ALTO · 28 canciones con la portada fija como video aunque tienen su videoclip
- **Dónde**: biblioteca (anterior al 2026-10-21) + regla de no rehacer nunca un `.bk2`.
- **Causa**: esas canciones se convirtieron cuando aún no tenían video (USDB no lo tenía: `skipped_unavailable`) y su
  `.bk2` se hizo con la portada (~3 KB/s; un clip real ronda 200 KB/s). Después se añadió a mano el videoclip
  recortado a la duración del audio (`video.mp4`), pero el conversor nunca vuelve a codificar un `.bk2` existente.
  Ejemplos: La isla bonita (https://www.youtube.com/watch?v=zpzdgmqIHOQ), Mamma Mia, Bohemian Rhapsody, Alejandro.
  Todas las copias (carpeta, `respaldo_bk2_2026-10-25`, `parche_anterior_2026-10`) tienen el mismo `.bk2` fijo: no se
  borró ni reemplazó nada.
- **Arreglo** (autorizado por el usuario como única excepción a "nunca rehacer un .bk2"): si el `.bk2` convertido pesa
  menos de 20 KB/s (`is_still_bk2`) y la carpeta tiene un video con movimiento (`has_motion`: ffmpeg freezedetect, o el
  tamaño si es un `.bk2` oficial), el `.bk2` y su `.avi` intermedio se **mueven** a `_replaced_videos/<carpeta>/` junto
  a la carpeta de canciones y se codifica el video. La tabla marca esas canciones (triángulo en Video, "Solo
  problemas"). Clic derecho → "Volver a codificar el video desde su fuente…" lo fuerza. Recodificadas las 27 con video
  propio (`video.mp4` recortado a mano, intacto); Merry Christmas toma su `.bk2` oficial de Let's Sing 2024; Swish Swish
  (Album Version) tiene como video una imagen. Las 16 que no tienen video: `~/LetsSing/VIDEOS_PENDIENTES.md`.
  Pruebas: `test_still_bk2_is_moved_aside_never_deleted`.

### B-67 · ALTO · La copia a la Switch llenó la SD
- **Dónde**: `tools/switch_update.py`.
- **Causa**: con `--prune` los archivos viejos solo se borraban al terminar de copiar los nuevos; con los IDs nuevos
  (título primero) el parche entero cambió de nombre y no cabían los dos (30 GB + 30 GB): "not enough space".
- **Arreglo**: `--prune-first` (guarda en el PC los viejos sin copia idéntica, los quita y luego copia). Esta vez el
  usuario vació la carpeta a mano y se copió todo desde cero; `make_dirs` crea en la Switch todas las carpetas del
  camino (MTP no crea `romfs/Songs/audio` si falta `romfs`), que era el "se esperaba 0 B" de DBI.

### B-68 · MEDIO · Copias por MTP cortadas por fallos sueltos de DBI
- **Dónde**: `tools/switch_update.py`.
- **Causa**: DBI a veces responde "Access denied" o no entrega un archivo (al reemplazar o al respaldar) y la copia se
  detenía entera.
- **Arreglo**: `kio_retry` reintenta hasta 4 veces con pausa creciente; volver a ejecutarla sigue donde quedó.

### B-69 · ALTO · El mod de saltar intro cerraba el juego al abrirlo
- **Dónde**: mod de saltar intro (`main.npdm`), hoy en su repositorio: https://github.com/leleletus/letssing2026-skip-intro.
- **Causa**: se instaló solo `subsdk9` con el `main.npdm` del juego, que no permite las llamadas al sistema que exlaunch
  usa para escribir sus ganchos: "Undefined System Call 0x74" (`svcMapProcessMemory`) en `atmosphere/crash_reports`.
- **Arreglo**: `main.npdm` del juego (convertido con `npdm2json.py` y rehecho con `npdmtool`) con solo 0x40, 0x43,
  0x74 y 0x75 añadidas; comparado campo a campo con el original. Probado en la consola: funciona.

### B-70 · MEDIO · Vista previa en el intro
- **Dónde**: `ConvertFiles.create_audio_preview`.
- **Causa**: sin etiquetas MEDLEY la vista previa empezaba siempre en el segundo 60 (en BBHMM, con 76 s de intro,
  sonaban ruidos del video).
- **Arreglo**: `preview_window`: `#PREVIEWSTART` si existe; si no, 1 s antes de la primera nota dorada (coro) del vxla;
  si no hay coro, la primera nota. Se corta del audio convertido; canciones de menos de 30 s: la canción entera.
  Prueba: `PreviewWindowTest`.

### B-71 · MEDIO · Something About Us con la letra 1,08 s tarde
- **Dónde**: biblioteca (txt de USDB sincronizado con un video que ya no existe; el audio se bajó de otro).
- **Causa**: la revisión de voz la marcó como "desfase" y quedó para revisión manual en vez de corregirse.
- **Arreglo**: `#GAP` −1080 ms (coincidencia con la voz 30% → 75%, veredicto ok). Video oficial alineado con
  `tools/align_video.py`.

### B-72 · MEDIO · Estribillos de Genius perdidos
- **Dónde**: `UltrastarToSingit.genius_get_choruses`.
- **Causa**: el texto de la página se saca con `get_text(separator="\n")`; cuando una cabecera lleva nombres con
  enlace (`[Coro: <a>Luis Fonsi</a>, <a>Demi Lovato</a>]`) queda partida en varias líneas y la expresión de
  `[Chorus…]` no la encuentra. 75 de las 597 cachés con página tienen `"choruses": []` (Sofia, Échame la culpa…).
- **Impacto**: en esas canciones los estribillos (y sus notas doradas del modo clásico) salen de la detección
  automática, que a veces da trozos de 3–5 s.
- **Arreglo**: la página se lee con `SongSections.parse_lyrics` (`<br>` → salto de línea; `choruses_from_sections`).
  `upgrade_genius_cache` relee solo las cachés con página y sin estribillos (de la página ya guardada por
  SongSections o de Genius) y las marca `reread`; esa marca entra en la firma del vxla, así que solo esas canciones
  regeneran su vxla. Resultado: 72 releídas, 51 con estribillos (las otras 21 no tienen sección de estribillo en
  Genius), 39 vxla regenerados (los demás eran canciones de DLC, que usan su letra oficial), 7 vistas previas
  movidas al estribillo encontrado. Prueba: `test_choruses_of_a_page_with_linked_names_in_the_headers`.

### B-73 · ALTO · El modo Feat cerraba el juego
- **Dónde**: `ConvertFiles` (no generaba `Songs/vxla_feat` ni `Songs/beats`) y `handle_xml_or_json` (`coopfriendly`).
- **Causa**: el juego carga `Singable.AssetType.VxlaFeat` en Feat; las canciones oficiales traen
  `<id>_feat.vxla` (y `beats/<id>.json`). `"Coop"` marca las canciones con segunda voz.
- **Arreglo**: `FeatVxla.py` + `SongSections.py` (ver `13_MODO_FEAT.md`); `coopfriendly` = `"Coop"` solo con segunda
  voz; `validate_patch.py` exige `vxla_feat` en 2026. Probado en la consola: Sofia y Un año sin lluvia en Feat.

### B-74 · ALTO · usdb_syncer no reconocía las canciones descargadas
- **Dónde**: `~/.config/bohning/usdb_syncer.conf` (no el conversor). Causado al arreglar B-63 el 2026-11-01.
- **Causa**: la carpeta se escribió a mano como texto (`song_dir=/home/.../songs`). usdb_syncer guarda un `Path` y su
  `_Settings.get` devuelve el valor por defecto (`~/songs`, que no existe) cuando el tipo no coincide: buscaba los
  `.usdb` en una carpeta vacía y dejaba su tabla `sync_meta` vacía, así que ninguna canción salía como descargada.
- **Arreglo**: `settings.set_song_dir(Path(...))` con el Python de usdb_syncer (copia
  `usdb_syncer.conf.antes_song_dir_20261105`) y su propia sincronización de carpeta: 271 canciones reconocidas. Para
  cambiar la carpeta: el botón de usdb_syncer, nunca editar el `.conf`.

### B-75 · MEDIO · SongMaker: letras pegadas y palabras fuera de sitio
- **Dónde**: canciones fabricadas con `SongMaker.py`. Reportado por el usuario en la consola con Goma de Mascar
  (2026-11-05), la única que ha probado.
- **Síntoma**: palabras que salen pegadas y palabras que aparecen donde no se canta.
- **Pistas a revisar** (sin confirmar): `assign_syllables` junta en la última nota las sílabas que sobran cuando hay
  menos notas que sílabas (pueden quedar varias palabras en una nota); el reparto de sílabas por ataques puede poner
  una sílaba en una nota que es un adorno o un ruido de la voz separada; los tiempos por línea de LRCLIB son de otra
  versión y el desfase global no corrige diferencias dentro de la canción.
- **Hecho (2026-11-05)**: el generador de notas se rehízo midiendo las oficiales (una nota por sílaba, sin unir
  sílabas sobrantes en una nota: `assign_syllables` ya no existe; rap como rap) y las 62 canciones se regeneraron
  (`tools/remake_notes.py`, sin tocar videos). El editor permite borrar sílabas/líneas y corregir el texto.
- **Falta**: en líneas ligadas (sin silencios entre sílabas) un 25 % de las sílabas llega a más de 0,3 s de su sitio;
  LRCLIB incluye coros entre paréntesis ("(yikes)", "(oye)") que la voz principal no canta.

