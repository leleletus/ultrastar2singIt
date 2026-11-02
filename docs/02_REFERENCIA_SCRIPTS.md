# 02 — Referencia script por script

Estado: 2026-11-01. Formato: `línea` · función · qué hace (bugs relacionados entre corchetes). Los números de línea
envejecen con cada cambio: para la línea actual, `grep -n "def <nombre>" <archivo>`.

---

## LetsSingUltraStarConverter.py (147) — punto de entrada

| Línea | Función | Qué hace |
|---|---|---|
| 4 | `main` | `--tool <nombre>` → herramienta; `--cli`/`-c` → CLI; si no → GUI |
| 13 | `_run_cli` | argparse (juego, herramientas, carpetas, ajustes, canciones del DLC); sobrescribe la config solo para esa ejecución |
| 122 | `_run_tool` | ejecuta `tools/<nombre>.py` (solo las de `ToolsPanel.TASKS` y `align_video`); así el ejecutable empaquetado también corre las herramientas |
| 135 | `_run_gui` | en Windows oculta la consola; `Gui.main()` |

## ConfigLoader.py (60) — configuración

| Línea | Función | Qué hace |
|---|---|---|
| 7 | `plugins_dir` | `app_dir()/plugins` (dependencias opcionales del tono slow) |
| 10 | `bundle_dir` | `_MEIPASS` en el ejecutable, si no la carpeta del script |
| 16 | `app_dir` | carpeta del ejecutable o del script (ahí van `config.yml`, `error.log`, `encode_stats.json`) |
| 22 | `deep_override_config` | fusión recursiva; ignora `None` |
| 36 / 43 | `load_default_config` / `load_config` | `config_default.yml` / default + `config.yml` de `app_dir()` [B-18 cerrado] |

## naming.py (146) — IDs y nombres de archivos generados

| Línea | Función | Qué hace |
|---|---|---|
| 12 | `strip_accents` | NFD + ø/œ/æ/ß/& |
| 26 | `construct_name_id_from_directory_name` | ID de caché: iniciales del artista + título, solo ASCII; `Song<md5>` si queda vacío. **Congelado** (nombra los `.bk2`) [B-30] |
| 47 | `game_song_id` | ID de juego (2026): título primero + iniciales del artista ("2BeLovedLR") [B-56] |
| 69 | `legacy_name_ids` | IDs de versiones anteriores del algoritmo (para reutilizar su caché) |
| 95–122 | sufijos | `AUDIO_SUFFIX`, `VXLA_META_SUFFIX`, `VIDEO_BK2_SUFFIX`, `VOICE_SUFFIX`… y `GENERATED_SUFFIXES`, `PROTECTED_SUFFIXES` (`.bk2`), `OFFICIAL_VXLA_NAME` |
| 133 | `is_generated_file` | si un archivo lo escribió el conversor para alguno de los IDs |

## ConvertFiles.py (1878) — orquestador

| Línea | Función | Qué hace |
|---|---|---|
| 41 | `VXLA_GENERATOR_VERSION` | subirla regenera todos los vxla (no los videos) |
| 53 | `_setup_error_log` | `error.log` en `app_dir()` (solo ERROR); silencia librerías ruidosas [B-37] |
| 100 / 123 | `_run` / `stop_running_processes` | subprocesos que Stop puede terminar (solo los de la conversión) [B-24] |
| 133 | `_ffmpeg` | escribe en un nombre temporal y renombra al final: nunca queda un archivo a medias |
| 159 | `safe_output_dir` | escudo `_Patch` si la salida tiene algo que no sea un TitleID [B-17] |
| 172 | `_init_paths` | rutas de ffmpeg/ffprobe/binkc/wine, entrada y salida |
| 194 | `resolve_config` | completa `core.id`, `json_name` y edición desde `data.db` |
| 227 | `_rescue_unbacked_videos` | antes de vaciar la salida, copia a su carpeta todo `.bk2` que solo esté en el parche |
| 276 | `delete_output_folder` | vacía la salida si `clear_output` |
| 310 | `is_video_still_image` | ffmpeg `freezedetect`: > 95 % congelado = imagen fija |
| 330 | `CleanImage` | portada limpia (RGB, sin EXIF) en un temporal propio por canción [B-02] |
| 367 | `create_still_video_from_cover_image` | video 1280×720 con fondo desenfocado desde la portada |
| 403 | `create_placeholder_cover` | portada con artista y título para canciones sin imagen |
| 442 / 455 | `_image_is_current` / `_image_has_size` | rehacer la imagen si no tiene el tamaño del juego o la fuente es más nueva [B-48] |
| 470–478 | `create_cover`, `create_cover_long`, `create_in_game_loading_picture` | 256×256, 191×396, 512×512 |
| 487 | `preview_window` | inicio de la vista previa: `#PREVIEWSTART`, 1 s antes del primer coro del vxla, o la primera nota [B-70] |
| 516 | `create_audio_preview` | corta 30 s del audio convertido |
| 525 | `create_audio` | aplica VIDEOGAP y #START/#END; `dynaudnorm` |
| 550 | `create_video` | x264 1280×720, 25 fps, `-bf 0` |
| 574 / 579 / 587 | `is_still_bk2` / `has_motion` / `moving_video` | detectar un `.bk2` de portada fija y un video real en la carpeta [B-66] |
| 595 | `keep_replaced_video` | mueve el `.bk2` reemplazado a `_replaced_videos` (nunca borra) |
| 612 / 631 | `_record_encode` / `recommended_workers` | mide cada codificación y calcula "Recomendado: N" |
| 662 | `_big_temp_dir` | `~/.cache/letssing_converter` (en disco; `/tmp` suele estar en RAM) |
| 671 | `create_video_bink` | `wine radvideo64 binkc` con `/D` según "Tamaño máximo"; timeout; valida el tamaño mínimo; un `.bk2` existente nunca se pisa [B-44, B-47] |
| 755 | `match_genre` | género del juego desde `#GENRE` (lista de 2026 solo para 2026) [B-55] |
| 768 | `parse_year` | año tolerante (`1985-03`, vacío…) [B-04] |
| 796 / 819 / 839 | `singer_gender` / `sung_median_pitch` / `song_difficulty` | voz y dificultad para 2026 |
| 865 | `game_ids_for` | `{carpeta: ID dentro del parche}`; únicos con un número si coinciden |
| 912 / 924 | `detect_language` / `song_language` | idioma por `#LANGUAGE` o por las palabras de la letra [B-52] |
| 962 | `_remove_old_patch_copies` | quita del parche las copias con el ID de caché tras pasar al ID de juego |
| 987 | `handle_xml_or_json` | `meta.xml` (XML) o registro en `SongsDLC.tsv` / `songs_xx.json` |
| 1038 / 1046 | `_atomic_write_text` / `_read_text` | escritura atómica; conserva BOM y codificación [B-03, M-06] |
| 1056 / 1090 / 1149 | `add_song_to_json` / `add_data_to_songsdlc_tsv` / `add_data_to_name_txt` | registro bajo `registry_lock`, sin duplicados [B-05] |
| 1173 / 1187 | `last_note_time` / `audio_window` | fin de la letra; cómo aplicar `#START`/`#END` |
| 1220 / 1236 | `get_required_files` / `validate_converted_files` | archivos que deben existir antes de copiar |
| 1276 | `choose_txt_file` | el txt UltraStar (no `[MULTI]`/`[DUET]`, no txt ajenos) |
| 1286 | `resolve_song_sources` | audio/video/portada: etiquetas primero, nunca archivos generados [B-08] |
| 1317 | `adopt_legacy_cache` | reutiliza archivos de IDs antiguos y un `.bk2` único de una carpeta renombrada [B-65] |
| 1342 / 1361 | `_vxla_cache_params` / `_vxla_is_current` | firma del vxla [B-13] |
| 1375 | `_copy_dlc_base_media` | copia los medios del DLC base al parche (opción "Incluir canciones del DLC") |
| 1408 | `_find_name_id_collisions` | dos carpetas con el mismo ID: la segunda se omite |
| 1421 | `convert_files` | bucle de canciones (secuencial o hilos) y `_convert_song` (ver 01 §3); devuelve el resumen ok/omitidas/fallidas |
| — | `uses_feat_mode` / `feat_sources` | 2026: qué sabe la letra feat además del vxla (estructura oficial, Genius, P2) |
| 1840 | `main` | resolve → rutas → ajustes por defecto si están desactivados → vaciar salida (o `only_dirs`) → convertir |

## UltrastarToSingit.py (836) — UltraStar → vxla

| Línea | Función | Qué hace |
|---|---|---|
| 52 | `normalize_lyric` | conserva todo lo que admite Windows-1252 (é, ñ, ¿…), translitera el resto [B-40, B-46] |
| 90 / 115 | `detect_encoding` / `read_text_file` | archivo completo: UTF-8 estricto → chardet → cp1252 → latin-1; nunca `errors='ignore'` [B-46] |
| 124 | `parse_file` | etiquetas en mayúsculas, líneas tolerantes, `#RELATIVE`, duetos (solo P1) [B-29] |
| 183 | `find_refrains` | estribillos automáticos por similitud entre páginas |
| 254 | `_end_word` | espacio al final de cada palabra, como los vxla oficiales [B-49] |
| 260 | `map_data` | tiempos (BPM, GAP, VIDEOGAP, `time_offset` de #START), notas `#p<tono>#.<sílaba>`, doradas, rap (`#p1`), páginas, estructura |
| 423 | `build_passages` | pasajes `long`/`speed` como los oficiales |
| 492 / 551 | `genius_search_for_correct_path` / `genius_get_choruses` | estribillos de Genius con caché (también "no encontrado") y modo sin conexión [B-39] |
| 660 / 706 | `recover_repeats_from_txt` / `match_choruses_to_beats` | repeticiones del estribillo y su posición en beats |
| 788 | `write_vxla_file` | capas segments (JSON) / structure+challenge (XML), pages, passages, lyrics, notes_full |
| — | `is_duet` / `voice_layers` | dueto con P2 / notas, letra y páginas de la voz 2, con los tiempos y el tono del vxla |
| 829 | `main` | parse → map → write |

## OfficialVxla.py (131) — vxla oficial de canciones de DLC

| Línea | Función | Qué hace |
|---|---|---|
| 21 | `_utf8_text` | archivos UTF-8 que declaran Windows-1252 [B-54] |
| 36 | `read_layers` | capas `{nombre: [(t1, t2, valor)]}` y versión (v2/v3) |
| 76 | `to_sing_it` | v2/v3 → estructura de `write_vxla_file`; el texto visible sale de la capa `lyrics` [B-50] |
| 119 | `convert` | escribe el vxla de la canción desde `letssing_original.vxla` |

## FeatVxla.py — modo Feat de Let's Sing 2026

| Elemento | Qué hace |
|---|---|
| `build_segments` | segmentos que cubren la canción, cortes al inicio de página: estribillos `feat`, estrofas por cambio de sección y luego por la pausa más larga (8–22 s) |
| `pauses_before_pages` | silencio antes de cada página (para elegir dónde cortar) |
| `feat_layers` / `write_feat_vxla` | capas de la letra feat desde el vxla normal (sin `#g`, segunda voz de P2 o de Genius); devuelve segmentos y notas de la voz 2 |
| `song_beats` / `write_beats` | beats con numpy + ffmpeg: `_analyze` (flujo mel y espectro), `_tempo_period`, `_track` (Ellis 2007), `_spectrum_bands`; `ONSET_DELAY_S` corrige 65 ms |
| `COOP_MIN_NOTES` | notas de la voz 2 para `"coopfriendly": "Coop"` |

## SongSections.py — secciones y cantantes (Genius)

| Elemento | Qué hace |
|---|---|
| `parse_lyrics` | página de Genius → secciones (`kind`, cantantes con su formato, líneas con su formato normal/cursiva/negrita) |
| `get_sections` | con caché `<txt>_genius_sections.json`; reutiliza la URL de `<txt>_genius_cache.json` |
| `song_singers` | (voz 1, voz 2) desde el artista y el título (`&`, `,`, `feat.`, `ft.`, `(feat. X)`) |
| `align_pages` | cada página de la canción → (sección, tipo, voces), en orden; una página puede ser media línea de Genius |

## PitchAnalyzer.py (201) — corrección de tono

| Línea | Función | Qué hace |
|---|---|---|
| 20 | `_slow_deps_available` | importación perezosa de numpy/librosa/crepe [B-38] |
| 37 | `get_explicit_pitch_offset` | `#LETSSINGPITCHOFFSET` (canciones reconstruidas desde DLC) |
| 48 | `choose_octave_shift` | múltiplo de 12 que deja menos notas fuera de `[43, 81]` [B-06] |
| 64 | `get_pitch_correction_suggestion_slow` | CREPE sobre el audio (Demucs opcional), redondeado a octavas |
| 132 / 152 / 167 | `get_txt_pitch_values` / `get_audio_pitch_values` / `analyze_pitch_from_audio` | estadísticas de tono [B-07] |
| 185 | `get_pitch_correction_suggestion_fast` | offset explícito o `choose_octave_shift` |

## Gui.py (2081) — ventana principal

| Línea | Elemento | Qué hace |
|---|---|---|
| 55 | `QtLogHandler` | logging → señal Qt (seguro entre hilos) |
| 66 | `ConversionWorker` | QThread que llama a `ConvertFiles.main`; señales de log, progreso, estado por canción y resumen |
| 105 | `SongRow` | estado de una carpeta: fuentes, caché, sincronía, último resultado |
| 137 / 153 | `voice_check` / `is_doubtful_sync` | resultado de `sync_scan` (`<id>.sync.json`) o aviso heurístico |
| 170 / 229 | `scan_song_folders` / `ScanWorker` | escaneo de la entrada en un hilo de fondo [B-25] |
| 252 | `COL_*`, `HEADERS` | columnas: marca, canción, estado, video, audio, imagen, letra, sinc., play |
| 259 / 421 | `SongTableModel` / `SongFilterModel` | modelo/vista; filtros búsqueda, "Solo pendientes", "Solo problemas" [G-01, G-03] |
| 496 | `MainWindow` | ventana |
| 566 | `t` | texto traducido que se actualiza al cambiar de idioma [B-20] |
| 602 / 768 / 817 / 958 | `init_elements` / `build_menus` / `create_left_panel` / `create_right_panel` | widgets, menús (Idioma, Herramientas, Ayuda), apartados 1–5, tabla y log |
| 1065 / 1077 | `restore_window_state` / `save_window_state` | QSettings |
| 1083–1195 | validadores `*_fv` | TitleID (`fullmatch` hex), rutas, JSON del DLC… [B-36] |
| 1204 | `set_defaults` | carga la config en el formulario (hilos e idioma incluidos) [B-19] |
| 1256 / 1269 / 1281 | `prefill_ffmpeg_path` / `prefill_rad_path` / `prefill_input_output_paths` | rutas por defecto (PATH, `$WINEPREFIX`, `Input/`/`Output/` junto al programa) |
| 1292 | `save_config` | `app_dir()/config.yml` |
| 1344 / 1372 | `scan_input_folder` / `refresh_single_song` | escaneo completo en fondo / una fila tras convertirla |
| 1438 | `on_table_context_menu` | Play, Arreglar sincronización, Abrir carpeta, Convertir solo esta, Volver a codificar el video, Añadir un video |
| 1465 / 1484 | `add_video` / `reencode_video` | `tools/align_video.py` / mover el `.bk2` a `_replaced_videos` y convertir |
| 1527 / 1545 | `song_audio_files` / `play_song_audio` | el audio convertido o el original [B-27] |
| 1563 | `open_sync_editor` | abre `SyncEditorDialog` con el txt elegido por `choose_txt_file` |
| 1622 | `sync_watched_folders` | vigila solo la carpeta de entrada (altas, bajas, renombres) |
| 1662 | `clear_cache` | borra los generados de las marcadas; los `.bk2` solo con petición explícita y doble confirmación |
| 1727 | `required_fields_missing` | validación antes de convertir [B-01] |
| 1779 | `update_recommended_workers` | "Recomendado: N" |
| 1797 | `on_tool_state_changed` | no se puede convertir mientras corre una herramienta (y al revés) |
| 1805 / 1810 | `start_checked_conversion` / `start_conversion` | convertir marcadas (añade al parche) / todo |
| 1854 | `confirm_output_clearing` | confirmación antes de vaciar la salida |
| 1902 / 1936 / 1944 | `on_conversion_finished` / `on_conversion_error` / `stop_conversion` | resumen real, error, Stop [B-24] |
| 1958 | `closeEvent` | confirmación y espera al worker [B-45] |
| 2005 / 2015 | `tool_recover_cache` / `tool_unpack_output` | menú Herramientas |
| 2037 | `start_hang_watchdog` | `hang_trace.log` si la ventana no responde 10 s [B-61] |
| 2073 | `main` | QApplication, tema, ventana |

## ToolsPanel.py (477) — apartado "5. Opciones avanzadas"

| Línea | Elemento | Qué hace |
|---|---|---|
| 30 / 38 | `Option` / `Task` | descripción de cada herramienta: opciones, tiempo estimado, si es pesada, programas que necesita |
| 55–110 | `TASKS` | `validate_patch`, `switch_update`, `sync_scan`, `usdb_sources`, `fix_covers`, `fix_years`, `fix_genres`, `usdb_restore_names`, `clean_song_folders`, `artist_genders` |
| 118 | `tool_command` | `python LetsSingUltraStarConverter.py --tool <nombre> …` (o el ejecutable) |
| 125 / 136 | `available_memory_gb` / `demucs_installed` | para desactivar lo que no puede correr |
| 141 | `ToolRunWindow` | salida en vivo |
| 169 | `ToolsPanel` | una herramienta a la vez, en un proceso aparte; las pesadas con `systemd-run -p MemoryMax` en Linux |
| 377 | `run_tool` | herramientas fuera de la lista (p. ej. `align_video` desde la tabla) |
| 459 | `stop` | termina el proceso (o la unidad de systemd) |

## SyncEditor.py (1200) y SyncModel.py (383) — editor de sincronía

| Archivo:línea | Elemento | Qué hace |
|---|---|---|
| SyncEditor:33 | `looks_still` | si el video es una imagen fija (3 fotogramas) |
| SyncEditor:74 | `NoteLane` | notas como barras (como el juego), voz aislada y tono cantado; arrastrar una nota cambia su tono |
| SyncEditor:209 | `SyncMap` | toda la canción en una franja, cada línea coloreada según coincida con la voz; cortes |
| SyncEditor:270 | `Microphone` | tono del micrófono (modo cantar) |
| SyncEditor:338 | `SyncEditorDialog` | reproductor, cortes (`cut_start`/`cut_end`), mover partes (`adjust`), `auto_adjust` (ajustar a la voz), `analyze_voice`, `save` (conserva codificación y finales de línea, `.bak` la primera vez) [B-26, B-51] |
| SyncModel:41 | `detect_pitch` | YIN |
| SyncModel:108 / 134 | `load_txt` / `load_official` | notas y sílabas de un txt / de un vxla oficial (solo lectura en el editor) |
| SyncModel:170 / 200 / 214 | `isolate_voice` / `analyze_voice` / `load_voice` | Demucs → `<id>.voice.npz` |
| SyncModel:227 / 273 / 290 | `line_report` / `runs_out_of_time` / `song_verdict` | coincidencia por línea, bloques desfasados, veredicto (ok/parcial/desfase/dudosa/otra_version) |
| SyncModel:316 | `rewrite_txt` | `#GAP` y notas movidas por cortes, en pulsos |

## GuiElement.py (107), i18n.py (22), SupportedFormats.py (3), version.py

- `GuiElement`: iconos Tabler (`pytablericons`) renderizados con QtSvg; sin el paquete, puntos de color.
- `i18n.load_language/tr`: diccionario plano; claves = texto en inglés.
- `SupportedFormats`: extensiones de video (`.mp4 .mpeg .avi .flv .divx .mkv .webm .bk2`), audio
  (`.mp3 .ogg .aac .wav .flac .m4a .opus`), imagen (`.jpg .jpeg .png .bmp`) y txt.

## data/

- `DlcEntity` (dataclass) y `DlcRepository` (`init`, `get_by_dlc_id`, `get_edition_by_core_id`, `get_all`,
  `get_by_core_edition`, `get_core_editions`) sobre `data.db`. `init()` rehace la tabla con la lista del código
  (2018–2026; 2026: aus/fr/int/spa/uk) [B-35].

## tools/

Todas se ejecutan con `python tools/<script>.py --help`. Las que cambian archivos solo listan hasta `--apply`
(los txt quedan con `.txt.bak`); ninguna borra un `.bk2`.

| Script | Uso | Notas |
|---|---|---|
| `validate_patch.py` | revisa un parche JSON (2024+) antes de copiarlo; en 2026 exige `vxla_feat` y avisa sin `beats` | solo lee |
| `switch_update.py` | copia a la Switch por MTP (KDE `kioclient` + DBI) solo lo que cambió | foto `<dlc>.switch.json`, `--first-copy` (Switch sin parche), respaldo antes de reemplazar, `--prune`/`--prune-first`, reintentos [B-62, B-67, B-68] |
| `sync_scan.py` | revisa toda la biblioteca contra la voz (Demucs), informe CSV y `<id>.sync.json` | continúa donde quedó; `--only-analyzed` [B-64] |
| `sync_check.py` | lo mismo para una canción, con propuesta de GAP | solo lee |
| `usdb_sources.py` | canciones de USDB cuyo audio viene de otro video | solo lee |
| `align_video.py` | recorta un videoclip (archivo o enlace de YouTube) al audio de la canción | yt-dlp: `YT_DLP`, PATH, el de usdb_syncer o el módulo |
| `fix_covers.py` | portada propia: USDB, oficial, single/álbum de iTunes | `--extracted`, `--dlc`, `--blank`, `--song` [B-53, B-58] |
| `fix_years.py` | año real: datos oficiales, MusicBrainz, iTunes | [B-57] |
| `fix_genres.py` | `#GENRE` desde iTunes | |
| `artist_genders.py` | voz por artista (MusicBrainz) → `_artist_genders.json` | |
| `usdb_restore_names.py` | nombres de archivo como los deja usdb_syncer | |
| `clean_song_folders.py` | mueve restos a `_papelera` | nunca borra |
| `diagnose_library.py` | informe de salud de la biblioteca (solo los txt) | |
| `attach_official_vxla.py` | empareja canciones reconstruidas con su vxla oficial | |
| `mark_extracted_songs.py` | marca reconstruidas con `#LETSSINGPITCHOFFSET:36` | |
| `rename_songs.py` | renombra carpeta + caché (videos incluidos) desde un CSV | |
| `LetSing_ExtractorPro.py` | megapack de Let's Sing → carpetas UltraStar | no toca carpetas existentes [B-34, B-48] |
| `reverse_vxla.py` | variante del extractor | [B-33] |
| `unpacker.py` | menú Herramientas → Desempaquetar (usa la lógica del extractor) | [B-32] |
| `cache_recovery.py` | menú Herramientas → Recuperar caché desde la salida | nunca sobrescribe [B-31] |

Quitados el 2026-11-01 (siguen en el historial de git, `git show fb416d5:<ruta>`): `desync_detector.py` (sustituido
por `sync_scan.py`), `mass_test.py` (sustituido por `tests/`), `merge_dlc_json.py` (lo hace el conversor con
"Copiar DLC"), `experimental_tools/` entero y `README_PULL_REQUEST.md`.

## tests/test_conversion.py (632)

60 pruebas (`python -m unittest discover -s tests -t .`): nombres e IDs, parser y codificaciones, tono por octavas,
fuentes y caché (incluido usdb_syncer y `.bk2` protegidos), escudo de salida, registro con hilos, #START/#END,
espacios y pasajes, vxla oficial, ida y vuelta vxla → txt → vxla, modelo de sincronía, idioma, IDs de juego,
dificultad/voz, base de datos, hilos recomendados, vista previa, edición de tono, modo Feat y secciones de Genius.
