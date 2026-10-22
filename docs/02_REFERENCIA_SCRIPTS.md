# 02 — Referencia script por script

Formato: `línea` · función · qué hace · notas (bugs relacionados entre corchetes).

---

## LetsSingUltraStarConverter.py (132 líneas) — punto de entrada

| Línea | Función | Qué hace / notas |
|---|---|---|
| 4 | `main` | `--cli`/`-c` → CLI; si no → GUI |
| 11 | `_run_cli` | argparse con grupos (game, tools, folders, tweaks, dlc songs); sobrescribe `config` solo para esa ejecución. No expone `multithreading`, `clear_output`, `force_reconvert`, `vocal_isolation` [M-07] |
| 120 | `_run_gui` | En Windows oculta la consola; importa `Gui` |

## ConfigLoader.py (60) — configuración

| Línea | Función | Qué hace / notas |
|---|---|---|
| 7 | `plugins_dir` | `app_dir()/plugins` (dependencias del modo slow) |
| 10 | `bundle_dir` | `_MEIPASS` en ejecutable congelado, si no carpeta del script |
| 16 | `app_dir` | carpeta del ejecutable o del script |
| 22 | `deep_override_config` | fusión recursiva; ignora `None` |
| 36 | `load_default_config` | solo `config_default.yml` |
| 43 | `load_config` | default + `config.yml` de `app_dir()` [B-18: la GUI escribe en el CWD] |

## ConvertFiles.py (962) — orquestador

| Línea | Función | Qué hace / notas |
|---|---|---|
| 5 | `json_lock` | lock global solo para el JSON [B-05: TSV y name.txt sin lock] |
| 39 | handler `error.log` | se añade al **importar** el módulo, ruta relativa al CWD [B-37] |
| 54 | `_init_paths` | rutas globales; escudo `_Patch` si la salida contiene algo que no sea un TitleID [B-16, B-17] |
| 82 | `resolve_config` | completa `core.id` y `json_name` desde data.db |
| 93 | `get_output_format` | JSON si hay `json_name` |
| 102 | `sanitize_name` | limpia nombres de carpeta (solo lo usa la función muerta de abajo) |
| 112 | `rename_folders_physically` | **código muerto** (upstream revirtió el renombrado, `3e46d42`); además usa `return` en vez de `continue` [B-43] |
| 142 | `strip_accents` | NFD + ø/œ/æ/ß/& (la línea de ñ es inalcanzable: NFD ya la descompone) |
| 153 | `construct_name_id_from_directory_name` | iniciales del artista + título minúsculas ASCII [B-30] |
| 170 | `find_folders_to_convert` | subcarpetas con `" - "` sin prefijo `_`/`.` (sin ordenar) |
| 177 | `delete_output_folder` | `rmtree(output)` si `clear_output` (por defecto True) |
| 192 | `get_duration` | ffprobe → `float(stdout)`; revienta si sale vacío [B-15] |
| 203 | `is_video_still_image` | `freezedetect`; >95 % congelado = imagen fija; división por cero si duración 0 |
| 225 | `create_still_video_from_cover_image` | video 1280×720 con fondo desenfocado desde `#COVER` o primera imagen; `IndexError` si no hay imágenes |
| 254 | `create_in_game_loading_picture` | 512×512 |
| 263 | `create_cover_long` | 191×396 (el fallback desde video usa 308×424 — tamaños inconsistentes) |
| 273 | `get_clean_image_path` | PIL → JPG limpio en **un único archivo temporal compartido** [B-02] |
| 293 | `create_cover` | 256×256 |
| 302 | `create_audio_preview` | medley → PREVIEWSTART → 60 s; recorta a la duración real |
| 338 | `create_audio` | adelay/atrim por VIDEOGAP + `dynaudnorm,volume=-2.5dB`; `IndexError` sin audio ni video [B-15] |
| 362 | `create_video` | x264 2 pasadas, `-bf 0`, 1280×720, 25 fps |
| 384 | `create_video_bink` | copia a tmp, `wine radvideo64 binkc`; **ignora `compression_percentage`** [B-11]; sin timeout ni log de salida [B-44] |
| 431 | `match_genre` | Pop/Rap/Rock/Ballad/Electro por subcadena |
| 439 | `handle_xml_or_json` | arma metadatos; `int(year)` sin control [B-04]; valores fijos (gender, language…) [M-10] |
| 471 | `create_meta_xml` | `<id>_meta.xml` UTF-8 BOM + CRLF |
| 493 | `add_song_to_json` | lee/crea `songs_xx.json`, reemplaza por ID; lee con `utf-8` [B-03] |
| 520 | `add_data_to_songsdlc_tsv` | TSV del core; UID ≥ 200; sin lock, sin encoding [B-05] |
| 586 | `add_data_to_name_txt` | XML: añade ID (sin deduplicar); JSON: escribe el nombre del JSON |
| 609 | `get_required_files` | lista de archivos que deben existir antes de registrar |
| 625 | `validate_converted_files` | devuelve los que faltan |
| 633 | `convert_files` | copia de medios del DLC base + bucle de canciones (secuencial o pool) |
| 681 | `_process_single_song` | todo el pipeline por canción (ver 01 §3) [B-04, B-08, B-09, B-10, B-12, B-13, B-14] |
| 912 | selección de multihilo | lee `multithreading`/`multithreading_workers` |
| 937 | `main` | resolve → init → reset tweaks si desactivados → borrar salida → convertir |

## UltrastarToSingit.py (660) — UltraStar → vxla

| Línea | Función | Qué hace / notas |
|---|---|---|
| 26 | `replacements` | comillas tipográficas, ligaduras, guiones |
| 38 | `normalize_text` | reemplazos + **quita todos los acentos** de las letras [B-40] |
| 45 | `normalize_for_url` | slug para URL de Genius |
| 54 | `detect_encoding` | chardet sobre 4 KB |
| 60 | `parse_file` | `#TAG:valor` → dict (claves sensibles a mayúsculas); notas `split(" ", 4)` [B-29] |
| 80 | `find_refrains` | estribillos automáticos por similitud entre páginas (≥20 caracteres, ≥85 %, separadas ≥10 s) |
| 136 | `merge_intervals` | une intervalos contiguos del mismo valor |
| 151 | `map_data` | tiempos = beat·60/BPM/4 + GAP + VIDEOGAP; notas `#p<tono>#.<sílaba>` (+`#g5` dorada/estribillo); `F/R` → `#p1#.`; páginas; estructura (medley → Genius → auto); pasajes `long`/`speed` |
| 299 | `get_lyrics_for_beat_range` | texto entre beats |
| 302 | `clean_artist_name` | corta en feat/ft/&/,/x |
| 310 | `sanitize_for_genius` | quita paréntesis, `+ artista`, `$→s`, `!→i` |
| 322 | `genius_search_for_correct_path` | API `search/multi` con 3 consultas, timeout 10 s |
| 379 | `genius_get_choruses` | caché `<txt>_genius_cache.json`; URL directa → búsqueda → regex de `[Chorus]` multilenguaje [B-39] |
| 475 | `recover_repeats_from_txt` | repeticiones del estribillo dentro del txt (≥90 %) |
| 521 | `match_choruses_to_beats` | ventana deslizante + Levenshtein (≥0.7) |
| 568 | `word_positions_to_beats` | índice de palabra → beats |
| 576 | `write_intervals` | `<Interval t1 t2 value>` con 3 decimales |
| 582 | `write_metadata_file` | **código muerto** (escribe en `titleid/romfs/`) |
| 603 | `write_vxla_file` | capas: segments (JSON) / structure+challenge (XML), pages, passages (fusionados), lyrics, notes_full, language="english" fijo; Windows-1252 con `&#NNN;` para el resto |
| 655 | `main` | parse → map → write |

## PitchAnalyzer.py (152) — corrección de tono

| Línea | Función | Qué hace / notas |
|---|---|---|
| 10 | `_slow_deps_available` | importa numpy/librosa/crepe **al cargar el módulo** [B-38] |
| 23 | `get_pitch_correction_suggestion_slow` | mediana CREPE del audio − mediana del txt; Demucs opcional (`htdemucs_ft`, CPU) |
| 76 | `get_txt_pitch_values` | media/mediana/min/max de notas `:`/`*`; división por cero sin notas [B-07] |
| 101 | `get_audio_pitch_values` | sobre notas MIDI válidas (confianza ≥ 0.9) |
| 115 | `analyze_pitch_from_audio` | librosa 16 kHz + CREPE tiny |
| 132 | `get_pitch_correction_suggestion_fast` | heurística heredada de upstream: +48 por defecto, o `81−max` / `43−min` [B-06] |

## Gui.py (1 650) — interfaz principal

| Línea | Elemento | Qué hace / notas |
|---|---|---|
| 21 | import QtMultimedia | el `.spec` lo excluye [B-41] |
| 47 | `QtLogHandler` | logging → señal Qt |
| 58 | `ConversionWorker` | QThread; añade/quita el handler; `finished` se emite siempre (también tras error/stop) [B-24] |
| 93 / 104 | `strip_accents` / `construct_name_id…` | **copias** de ConvertFiles [B-30] |
| 122 / 127 | `set_element_enabled` / `mark_field_valid` | borde rojo por propiedad dinámica `has_border` |
| 134 / 142 | barra de título oscura (Windows) / tooltips por tema | `apply_theme_change` **acumula** hojas de estilo en cada cambio de tema |
| 185 | `MainWindow.__init__` | menús Language/Tools, paneles, watcher con debounce 500 ms, QMediaPlayer, carga config |
| 273-324 | validadores `*_fv` de Game info | regex TitleID laxa [B-36]; `dlc_json_name_input_fv` re-escanea la carpeta cada vez [B-25] |
| 326 | `create_left_panel` | grupos Game info / Conversion tools / Input-Output / Advanced settings (checkable) / Help |
| 490 | `create_right_panel` | tabla + logs (alto fijo 150 px) |
| 521 | `create_preview_table` | búsqueda, tabla, leyenda, barra de progreso, botones |
| 602-668 | validadores de rutas | `output_path_fv` aplica el escudo `_Patch` [B-17] |
| 670 | `include_dlc_checkbox_refresh` | activa campos XML o JSON |
| 693 | `set_defaults` | carga config en el formulario; **no carga** multithreading/workers [B-19] ni idioma [B-20] |
| 759 / 780 | `prefill_ffmpeg_path` / `prefill_rad_path` | rutas típicas Windows/Linux/Wine |
| 816 | `sanitize_name` | **código muerto** |
| 825 | `scan_input_folder` | lista canciones, iconos de entrada/caché, botones Play y Fix Sync; parsea cada txt [B-25]; filtro `_cover.mp4` obsoleto [B-09] |
| 963 | `play_song_audio` | primer `*.ogg`/`*.mp3` [B-27]; llama a `log_message` inexistente [B-21] |
| 994 | `is_doubtful_sync` | marca ⚠ si GAP<0, BPM fuera de 50–400 o primera letra < 0.5 s |
| 1019 | `open_sync_editor` | `glob('*.txt')[0]` [B-26]; `log_message` inexistente [B-21] |
| 1068-1101 | watcher | vigila raíz + subcarpetas; refresco completo en cada evento, también durante la conversión [B-25] |
| 1128 | `clear_cache` | borra solo la lista `outputs` [B-28] |
| 1174 | `required_fields_missing` | **`return` mal indentado: no valida nada** [B-01] |
| 1205 | `set_controls_enabled` | deshabilita todo; al reactivar pone `SingleSelection` [B-23] |
| 1247 | `start_conversion` | guarda config, lanza el worker |
| 1284-1336 | progreso / fin / error | ETA por media; "finished successfully" incluso tras error/stop [B-24] |
| 1338 | `stop_conversion` | `stop_event` + `pkill -9 -f radvideo*` (Linux) — no mata ffmpeg [B-24] |
| 1355 / 1376 | ayuda | `Guide.md` → HTML con `markdown` |
| 1388 | `init_elements` | crea todos los widgets |
| 1450 / 1456 | idioma | `update_ui_language` cubre ~30 textos; clave en español para include_dlc [B-20] |
| 1507 | `set_tooltips` | mezcla inglés y español |
| 1552 / 1568 | Tools → Recover cache / Unpack | ver tools/ [B-31, B-32] |
| 1586 | `save_config` | escribe `config.yml` en el **CWD** [B-18] |
| 1644 | `main` | QApplication, tema, show (no usa `qdarktheme`, importado sin uso) |

## PreviewTable.py (228)

| Línea | Elemento | Notas |
|---|---|---|
| 17 | `CheckBoxHeader` | checkbox tri-estado pintado en la cabecera |
| 79 | `PreviewTable.__init__` | 9 columnas: `"", Play, Song, Sync, Video, Audio, Image, Lyrics, OrigOrder(oculta)`; anchos fijos; cabeceras sin traducir |
| 131 | `on_header_clicked` | asc → desc → original; el "original" ordena por la columna **7** en vez de 8 [B-22] |
| 159 | `toggle_rows` | marcar/desmarcar selección |
| 211 | `mousePressEvent` | seleccionar una fila nueva alterna su checkbox (clic en fila = marcar) — comportamiento poco evidente [G-05] |
| 219 | `keyPressEvent` | Ctrl+A y Espacio |

## SyncEditor.py (281) — "Fix Sync"

| Línea | Elemento | Notas |
|---|---|---|
| 12 | `__init__` | parsea el txt, elige el primer `*.ogg` [B-26], arma reproductores y controles (textos solo en español) |
| 131 | `build_lines` | agrupa notas por `-` |
| 205 | `update_lyrics` | cada 50 ms; resalta sílabas; ignora VIDEOGAP; `note[4]` sin control |
| 254 | `save_gap` | reescribe `#GAP:` en UTF-8 (no respeta la codificación original, no añade GAP si falta) [B-26] |

## GuiElement.py (77), i18n.py (22), SupportedFormats.py (3), version.py

- `GuiElement.Icon`: iconos dibujados con PIL al importar; `get_icon()` los cachea como QIcon; `combine_icons` (doble ancho).
  `pytablericons` se importa pero no se usa.
- `i18n.load_language/tr`: diccionario plano; claves = texto inglés.
- `SupportedFormats`: `.bk2` cuenta como video de entrada pero luego no se procesa [B-14]; falta `.jfif`, `.webp`, `.m4v`, `.mov`.

## data/

- `DlcEntity` (dataclass), `DlcRepository`: consultas a `data.db`. `init()` hace `drop table dlc` sin `IF EXISTS` [B-35].
  Catálogo 2018–2026 (2026: aus/fr/int/spa/uk).

## tools/

| Script | Uso | Estado / notas |
|---|---|---|
| `cache_recovery.py` | menú Tools → copia medios del parche de vuelta a la caché | name_id antiguo; `os.walk` puede encontrar primero el romfs del core [B-31] |
| `unpacker.py` | menú Tools → vxla → txt | **roto**: `NameError safe_artist` (l.102); BPM inconsistente; formato de notas no coincide [B-32] |
| `reverse_vxla.py` | script, rutas fijas | `NameError name_id` (l.154) si hay video [B-33] |
| `LetSing_ExtractorPro.py` | CLI `--megapack --output` | solo capa `notes`; detección de espacios casi nula [B-34] |
| `desync_detector.py` | script (Demucs + CREPE) | se ejecuta al importar; lee `config.yml` del CWD; escribe `reporte_desync.md` |
| `merge_dlc_json.py` | script, rutas fijas | fusiona megapack en `songs_int_combined.json` |
| `mass_test.py` | script, rutas fijas | no es una prueba real; compara nº de notas |

## experimental_tools/ y scripts sueltos de la raíz

| Script | Notas |
|---|---|
| `clean_audio_cache.py` | borra **todos** los `.ogg` que no sean el `#MP3` — riesgo de borrar originales con `#AUDIO` (formato 1.1) |
| `compare_durations.py` | m4a vs ogg (detectar desfase introducido por la conversión) |
| `fix_dlc_artists_metadata.py` | repara "Unknown Artist" con tabla fija + iTunes |
| `rebuild_audio.py` | lanza `ConvertFiles.main` con la config |
| `fix_songs.py`, `clean_output_files.py`, `clean_output_json.py` (raíz, sin versionar) | limpiezas puntuales con IDs y rutas fijas; candidatos a borrar o mover a `experimental_tools/` |
| `audios.txt` / `covers.txt` (raíz) | listados de IDs: audio con estilo DLC oficial (`24KMagic`) vs portadas con estilo de este conversor (`BM24kmagic`) — evidencia de la discrepancia de IDs al mezclar con el megapack |
