# 01 — Informe técnico

Estado del código: rama `linux-wine-support`, 2026-11-01. La auditoría original (commit `4e1cb35`) y los bugs que
encontró están en [03_BUGS.md](03_BUGS.md); este documento describe el programa **tal como es ahora**.

## 1. Qué hace el programa

Convierte carpetas de canciones UltraStar (`Artista - Título/` con `.txt` + audio + video + portada) al formato de los DLC
de **Let's Sing** (Nintendo Switch) y genera un parche LayeredFS (`<TitleID del DLC>/romfs/...`) que se copia a
`sd:/atmosphere/contents/` de la consola.

Dos formatos de salida, decididos por `dlc.json_name` (lo completa la base de datos de DLC):

| Formato | Juegos | Metadatos | Video | Imágenes extra |
|---|---|---|---|---|
| `XML` (`json_name` vacío) | 2018–2023 | `SongsDLC.tsv` (core) + `<id>_meta.xml` + `name.txt` con lista de IDs | `.mp4` (libx264) | `_InGameLoading.png`, `_Result.png`, `_long.png` |
| `JSON` (`json_name` = `songs_xx`) | 2024+ | `songs_xx.json` + `name.txt` con el nombre del JSON | `.bk2` (Bink 2 vía RAD Video Tools) | — |

Común a ambos: `<id>.ogg` (audio normalizado), `<id>_preview.ogg` (30 s), `<id>.png` (256×256), `<id>.vxla` (letras/notas).

### Solo para Let's Sing 2026

Se activa por la edición del juego (`cfg.core.edition`, de `data.db`). Las demás ediciones generan lo mismo de siempre.

| Qué | Dónde | Por qué |
|---|---|---|
| ID de juego con el título primero (`ControlZW`) | `naming.game_song_id`, `ConvertFiles.game_ids_for` (`GAME_ID_EDITIONS`) | el juego ordena la lista "Título" por el ID |
| Idioma real (English/French/Spanish/German/Korean/Other) | `ConvertFiles.song_language` (`REAL_LANGUAGE_EDITIONS`) | filtro por idioma del juego |
| Géneros del juego (HipHop, RnB, Latin…) | `ConvertFiles.match_genre` | "Rap" no existe en 2026 |
| Dificultad calculada de las notas | `ConvertFiles.song_difficulty` | ajustada con 59 canciones oficiales |
| Voz (Men/Women/Both) | `ConvertFiles.singer_gender` + `<canciones>/_artist_genders.json` | filtro de cantante |

Dentro de la carpeta de cada canción la caché sigue usando el `name_id` de siempre. El ID de juego solo se usa para
los nombres de los archivos dentro del parche.

## 2. Mapa de módulos

```
LetsSingUltraStarConverter.py   entrada: --cli → CLI (argparse) | --tool <nombre> → tools/<nombre>.py | sin flag → GUI
├── Gui.py                      ventana PySide6: formulario, tabla (modelo/vista), log, worker QThread, vigilante de cuelgues
│   ├── ToolsPanel.py           "5. Opciones avanzadas": herramientas de tools/ en un proceso aparte, de una en una
│   ├── SyncEditor.py           editor de sincronía (video, carril de notas, cortes, análisis de voz, modo cantar)
│   │   └── SyncModel.py        modelo de tiempos sin Qt (también lo usa tools/sync_scan.py): txt/vxla, YIN, Demucs
│   ├── GuiElement.py           iconos Tabler (pytablericons) renderizados con QtSvg
│   └── i18n.py + locales/es.json   traducción (tr(); la clave es el texto en inglés)
├── ConvertFiles.py             orquestador: fuentes, ffmpeg, binkc, caché con firmas, registro TSV/JSON/XML, copia al parche
│   ├── naming.py               name_id (caché), ID de juego (2026), IDs antiguos, sufijos de los archivos generados
│   ├── UltrastarToSingit.py    parser UltraStar → vxla (notas, letras, páginas, pasajes, estribillos medley/Genius/auto)
│   ├── OfficialVxla.py         reutiliza el vxla oficial de una canción de DLC (letssing_original.vxla)
│   ├── PitchAnalyzer.py        tono: fast (por octavas) | slow (CREPE, Demucs opcional) | #LETSSINGPITCHOFFSET
│   ├── SupportedFormats.py     extensiones aceptadas
│   └── data/repository/DlcRepository.py + data.db   catálogo de juegos/DLC 2018–2026 (TitleIDs, json_name, edición)
├── ConfigLoader.py             config_default.yml (empaquetado) + config.yml (junto al programa) → Munch
└── version.py
tools/                          herramientas de la biblioteca (CLI y apartado 5 de la GUI); ver 02_REFERENCIA_SCRIPTS.md
tests/test_conversion.py        pruebas de regresión: python -m unittest discover -s tests -t .
```

El mod del juego (saltar el intro) vive en su propio repositorio: ver [10_MOD_SALTAR_INTRO.md](10_MOD_SALTAR_INTRO.md).

## 3. Flujo de una conversión

```
Gui.start_conversion(only=None | [carpetas])
  └─ required_fields_missing()            campos obligatorios y rutas válidas
  └─ confirm_output_clearing()            conversión completa: pide confirmación si la salida tiene contenido
  └─ save_config() → <programa>/config.yml
  └─ ConversionWorker(QThread).run → ConvertFiles.main(cfg, stop_event, progress, song_callback, only_dirs)
       resolve_config        dlc.id → core.id, json_name y edición desde data.db
       _init_paths           ffmpeg/ffprobe/binkc/wine, entrada/salida; safe_output_dir (escudo _Patch)
       (si "Opciones de conversión" está desmarcado → conversion_tweaks por defecto)
       find_folders_to_convert   subcarpetas con " - " que no empiezan por "_" o "."
       only_dirs → solo esas carpetas, el parche existente se actualiza (no se vacía)
       si no   → delete_output_folder (antes rescata los .bk2 sin copia en su carpeta: _rescue_unbacked_videos)
       convert_files
         _copy_dlc_base_media (opcional: medios del DLC base)
         _find_name_id_collisions  → la segunda carpeta con el mismo ID se omite con aviso
         game_ids_for              → ID dentro del parche (2026: título primero, único)
         por canción (secuencial o ThreadPoolExecutor, "Hilos"):
           1. renombrado temporal si la carpeta termina en "." (Wine)
           2. adopt_legacy_cache   reutiliza archivos de IDs antiguos y un .bk2 único de una carpeta renombrada
           3. choose_txt_file + parse_file; resolve_song_sources (#AUDIO/#MP3, #VIDEO, #COVER; nunca archivos generados)
           4. audio: audio_window (#START/#END) + VIDEOGAP → create_audio si cambió la firma (<id>.ogg.meta.json)
           5. sin portada → fotograma del video o portada con artista y título (_autocover.png)
           6. video: XML → create_video (x264); JSON → intermedio .avi → create_video_bink (wine + binkc, /D por tamaño)
              · un .bk2 existente NUNCA se recodifica, salvo si es la portada fija (is_still_bk2) y la carpeta tiene
                un video con movimiento (has_motion): el viejo se mueve a _replaced_videos (keep_replaced_video)
              · sin video o binkc falló → video estático desde la portada (_cover.avi → .bk2 / _cover.mp4)
           7. imágenes: create_cover (256×256) y, en XML, _long y _InGameLoading (se rehacen si el tamaño no es el del juego)
           8. vxla: letssing_original.vxla → OfficialVxla.convert; si no, PitchAnalyzer + UltrastarToSingit.main;
              solo si cambia la firma (<id>.vxla.meta.json) o "Forzar"
           9. preview_window → create_audio_preview (#PREVIEWSTART, primer coro o primera nota)
          10. validate_converted_files → si falta algo, SongError (la canción se omite, no rompe las demás)
          11. copia al parche (con el ID de juego) y DESPUÉS registro (registry_lock): name.txt + TSV/meta.xml o JSON;
              si el registro falla se borran las copias de esa canción
         song_callback(carpeta, running|ok|skipped|failed|stopped) → estado de la fila en la tabla
       log_summary → convertidas / omitidas / fallidas con motivo
  └─ señales: log → panel de log, progress → barra + ETA, finished/error → reactivar la interfaz
```

Stop: `stop_event` + `stop_running_processes()` termina los ffmpeg/binkc lanzados por la conversión (solo los
suyos). Cerrar la ventana durante una conversión pide confirmación y espera al worker.

## 4. Caché (dentro de cada carpeta de canción)

Los archivos convertidos se guardan junto a la canción con el prefijo `name_id` (sufijos en `naming.py`):

| Archivo | Lo crea | Se rehace cuando… | "Limpiar caché" |
|---|---|---|---|
| `<id>.ogg` + `<id>.ogg.meta.json` | create_audio | cambian #START/#END/VIDEOGAP (firma) o falta | sí |
| `<id>_preview.ogg` + `_preview.ogg.meta.json` | create_audio_preview | cambia el audio o la ventana | sí |
| `<id>.png`, `_long.png`, `_InGameLoading.png` | create_cover* | falta, tamaño distinto al del juego o fuente más nueva | sí |
| `<id>_autocover.png` | create_placeholder_cover | falta | sí |
| `<id>.vxla` + `<id>.vxla.meta.json` | UltrastarToSingit / OfficialVxla | cambia la firma: versión del generador, formato, tono, medley, tildes, Genius, txt, duración | sí |
| `<id>.mp4` (XML) | create_video | falta | sí |
| `<id>.bk2` (JSON) | create_video_bink | **nunca**, salvo portada fija + video con movimiento (se mueve, no se borra) | **solo con doble confirmación** |
| `<id>.avi`, `<id>_cover.avi`, `<id>_cover.mp4` | intermedios | falta | sí |
| `<id>.voice.npz` | SyncModel.analyze_voice (editor / sync_scan) | cambia el audio | sí |
| `<id>.sync.json` | tools/sync_scan.py | cambia el txt | sí |
| `<txt>_genius_cache.json` | genius_get_choruses | — (también guarda "no encontrado") | sí |
| `letssing_original.vxla` | tools/attach_official_vxla.py | — (es una fuente, no caché) | no |

`VXLA_GENERATOR_VERSION` (ConvertFiles.py) se sube cada vez que cambia el vxla generado: todos se regeneran solos
en la próxima conversión y los videos no se tocan.

Fuera de las carpetas de canciones:

| Ruta | Qué |
|---|---|
| `<canciones>/../_replaced_videos/<carpeta>/` | `.bk2` de portada fija reemplazados por un video real |
| `<canciones>/../_papelera/<fecha>/` | lo que quita `tools/clean_song_folders.py` (nunca borra) |
| `<canciones>/../informe_sincronia.csv` | informe de `tools/sync_scan.py` |
| `<salida>/../<dlc>.switch.json`, `switch_backup_<fecha>/` | foto de lo que tiene la Switch y respaldo de `tools/switch_update.py` |
| `~/.cache/letssing_converter/` | temporales grandes (copias de videos para Wine, separación de voz): en disco, no en `/tmp` |
| `<programa>/encode_stats.json` | velocidad medida de cada codificación (para "Recomendado: N") |

## 5. Configuración

- `config_default.yml` (empaquetado, `bundle_dir()`): todas las claves con su valor por defecto.
- `config.yml` (usuario, `app_dir()`): lo escribe `Gui.save_config()` y lo lee `load_config()`, los dos en la carpeta
  del programa. No se versiona (`.gitignore`). `deep_override_config` ignora los valores `None`.
- Ventana: tamaño, posición, anchos de columna y filtros en `QSettings("LetsSingUltraStarConverter", "Converter")`.
- Si "Opciones de conversión" está desmarcado, `ConvertFiles.main` usa los `conversion_tweaks` por defecto.

| Clave | Para qué |
|---|---|
| `dlc.id`, `dlc.json_name`, `core.id` | DLC que se parchea; el resto sale de `data.db` si el DLC está en el catálogo |
| `tools.ffmpeg_path`, `tools.rad_path`, `tools.wine_path` | vacíos → se buscan solos (ver §6) |
| `folders.input`, `folders.output` | vacíos → `Input/` y `Output/` junto al programa |
| `conversion_tweaks.*` | tono, tamaño máximo del video, medley, video fijo, vaciar salida, forzar, tildes, Genius, hilos, aislamiento de voz |
| `language` | idioma de la interfaz (`en`/`es`) |

## 6. Dependencias externas

| Herramienta | Uso | Cómo se encuentra |
|---|---|---|
| ffmpeg / ffprobe | audio, imágenes, video x264, duraciones, detección de imagen fija | `tools.ffmpeg_path`, si no `ffmpeg` del PATH, `<programa>/ffmpeg/bin/ffmpeg.exe`, `C:\ffmpeg\bin`; ffprobe junto a ffmpeg o en el PATH |
| RAD Video Tools `radvideo64.exe binkc` | `.bk2` para 2024+ | `tools.rad_path`; si no, `Program Files (x86)/RADVideo/` (en Linux dentro de `$WINEPREFIX`, por defecto `~/.wine`) |
| Wine (Linux) | ejecutar binkc | `tools.wine_path` o `wine` del PATH; necesita `gst-plugins-good` (README_Linux.md) |
| Genius (web) | estribillos | opcional ("Buscar estribillos en internet"); caché también de "no encontrado" |
| CREPE / TensorFlow / librosa | tono "slow" | `requirements-slow.txt` o `plugins/`; importación perezosa |
| Demucs (+ torch) | análisis de voz (editor, sync_scan), tono slow con aislamiento | `requirements-slow.txt`; `python -m demucs` (no funciona en el ejecutable empaquetado) |
| yt-dlp | "Añadir un video" con enlace | `YT_DLP`, PATH, el de usdb_syncer (pipx) o el módulo `yt_dlp` |
| kioclient (KDE) + DBI | `tools/switch_update.py` (MTP) | PATH; solo Linux con KDE |
| systemd-run | límite de memoria de las herramientas pesadas | PATH; si no existe, se ejecutan sin límite |
| MusicBrainz / iTunes (web) | años, géneros, voz, portadas | herramientas `fix_*` y `artist_genders` |
| SQLite `data/repository/data.db` | catálogo de DLC | `DlcRepository.init()` lo rehace desde la lista del código |

Python: `requirements.txt` (programa), `requirements-slow.txt` (IA de voz/tono, varios GB), `requirements-dev.txt`
(PyInstaller). El ejecutable se construye con `Lets Sing Ultrastar Converter.spec` y `.github/workflows/build.yml`.

## 7. Mapa de impacto — "si tocas X, revisa Y"

| Si cambias… | Revisa también |
|---|---|
| `naming.construct_name_id_from_directory_name` | **no cambiarlo**: nombra la caché (`.bk2`) de todas las canciones. Si hiciera falta, añadir la versión vieja a `legacy_name_ids` (y `adopt_legacy_cache` la reutiliza) y probar `NamingTest` |
| `naming.game_song_id` / `game_ids_for` | IDs ya instalados en la consola (puntuaciones, favoritos); `_remove_old_patch_copies`; `tools/switch_update.py --prune` |
| Sufijos de archivos generados (`naming.py`) | `GENERATED_SUFFIXES`, `is_generated_file`, `resolve_song_sources`, `Gui.scan_song_folders`, Limpiar caché, `tools/clean_song_folders.py`, `tools/cache_recovery.py` |
| Formato del vxla (`write_vxla_file`, `map_data`, `OfficialVxla`) | subir `VXLA_GENERATOR_VERSION`; lectores inversos `tools/LetSing_ExtractorPro.py`, `tools/reverse_vxla.py`, `tools/unpacker.py`; `SyncModel.load_official`; `VxlaRoundTripTest` |
| Corrección de tono (PitchAnalyzer) | `PITCH_MIN/MAX` (ConvertFiles.py); `#LETSSINGPITCHOFFSET` que escriben los extractores; `PitchTest` |
| Tiempos (BPM/GAP/VIDEOGAP/#START/#END) | `UltrastarToSingit.map_data`, `ConvertFiles.audio_window`/`create_audio`/`preview_window`, `SyncModel` (editor y sync_scan) |
| Campos de `songs_xx.json` / `meta.xml` / TSV | limitar el cambio a la edición que lo tiene (`*_EDITIONS`); las demás deben quedar byte a byte iguales; probar en la consola |
| Claves de configuración | `config_default.yml`, `Gui.set_defaults`, `Gui.save_config`, flags de `LetsSingUltraStarConverter._run_cli`, `ConvertFiles.main/convert_files` |
| Textos de la interfaz | `locales/es.json` (la clave es el texto en inglés literal; `MainWindow.t()` los vuelve a traducir al cambiar de idioma) |
| Columnas de la tabla | `HEADERS` y constantes `COL_*` de `Gui.py`, `SongTableModel.data`, `SongFilterModel` |
| Herramientas de `tools/` | `ToolsPanel.TASKS` (opciones, si son pesadas), `hiddenimports` del `.spec`, `LetsSingUltraStarConverter._run_tool` |
| Ruta de salida | `ConvertFiles.safe_output_dir` (única), usada por GUI y conversión |

## 8. Deuda técnica conocida

1. `Gui.py` (≈2 100 líneas) y `ConvertFiles.py` (≈1 900) son grandes; `_convert_song` es una clausura de ~280 líneas
   dentro de `convert_files`. `SyncModel.py` (sin Qt) es el modelo a seguir para separar lógica y vista (M-08).
2. Estado global de módulo en ConvertFiles (`_ffmpeg_path`, `_output_dir`…): una sola conversión por proceso.
3. `tools/switch_update.py` depende de KDE (`kioclient`) y del respondedor MTP de DBI.
4. B-61 (un cuelgue de la ventana) sigue abierto: el vigilante escribe `hang_trace.log` si vuelve a pasar.
5. `.gitignore` funciona como lista blanca (`*/` y excepciones): una carpeta nueva queda ignorada hasta añadirla.
