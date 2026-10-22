# 01 — Informe técnico

## 1. Qué hace el programa

Convierte carpetas de canciones UltraStar (`Artista - Título/` con `.txt` + audio + video + portada) al formato de los DLC
de **Let's Sing** (Nintendo Switch) y genera un parche LayeredFS (`<TitleID>/romfs/...`) que se copia a la consola.

Dos formatos de salida, decididos por `dlc.json_name`:

| Formato | Juegos | Metadatos | Video | Imágenes extra |
|---|---|---|---|---|
| `XML` (`json_name` vacío) | 2018–2023 | `SongsDLC.tsv` (core) + `<id>_meta.xml` + `name.txt` con lista de IDs | `.mp4` (libx264) | `_InGameLoading.png`, `_Result.png`, `_long.png` |
| `JSON` (`json_name` = `songs_xx`) | 2024+ | `songs_xx.json` + `name.txt` con el nombre del JSON | `.bk2` (Bink 2 vía RAD Video Tools) | — |

Común a ambos: `<id>.ogg` (audio 48 kHz normalizado), `<id>_preview.ogg` (30 s), `<id>.png` (256×256), `<id>.vxla` (letras/notas).

## 2. Mapa de módulos

```
LetsSingUltraStarConverter.py   punto de entrada: --cli → CLI (argparse) | sin flag → Gui.main()
├── Gui.py                      ventana principal PySide6 (formulario, tabla, logs, worker QThread)
│   ├── PreviewTable.py         QTableWidget con checkbox en cabecera y orden en 3 estados
│   ├── GuiElement.py           iconos generados con PIL (círculo/cuadro/check/cruz) + combinación de iconos
│   ├── SyncEditor.py           diálogo "Fix Sync": reproduce audio/video y ajusta #GAP del .txt
│   ├── i18n.py + locales/es.json   traducción (tr()) — solo es/en
│   └── tools/cache_recovery.py, tools/unpacker.py   (menú Tools)
├── ConvertFiles.py             orquestador de la conversión (ffmpeg, binkc, TSV/JSON/XML, copia al parche)
│   ├── UltrastarToSingit.py    parser UltraStar → vxla (notas, letras, páginas, estribillos vía medley/Genius/auto)
│   ├── PitchAnalyzer.py        corrección de tono: fast (heurística) | slow (CREPE + Demucs opcional)
│   ├── SupportedFormats.py     extensiones aceptadas
│   └── data/repository/DlcRepository.py + data.db   catálogo de juegos/DLC (TitleIDs, json_name)
├── ConfigLoader.py             config_default.yml (empaquetado) + config.yml (usuario) → Munch
└── version.py
```

Scripts sueltos (no los usa la app): `tools/*.py` (salvo los dos del menú), `experimental_tools/*.py`, `fix_songs.py`,
`clean_output_files.py`, `clean_output_json.py`. Varios tienen rutas personales fijas (`/run/media/djvemo/EADE-F56A/...`).

## 3. Flujo de una conversión

```
Gui.start_conversion
  └─ required_fields_missing()          (validación — actualmente desactivada, ver B-01)
  └─ save_config() → config.yml          (se escribe en el CWD, ver B-18)
  └─ ConversionWorker(QThread).run → ConvertFiles.main(cfg, stop_event, progress_callback)
       resolve_config     dlc.id → core.id + json_name desde data.db
       _init_paths        ffmpeg/ffprobe/rad, input/output + "escudo _Patch"
       (si tweaks desactivados → conversion_tweaks = valores por defecto)
       delete_output_folder   rmtree(output) si clear_output
       find_folders_to_convert   subcarpetas con " - " que no empiezan por "_" o "."
       convert_files
         copia opcional de medios del DLC base (Songs/ junto al songs_xx.json)
         por canción (_process_single_song, secuencial o ThreadPoolExecutor):
           1. renombrado temporal si la carpeta termina en "." (bug de Wine)
           2. name_id = iniciales del artista + título en minúsculas ASCII
           3. parse_file(txt) → tags + notas
           4. video:  XML → create_video (2 pasadas x264, 1280×720, 25 fps)
                      JSON → AVI intermedio (x264) → create_video_bink (wine radvideo64 binkc)
           5. audio  → create_audio (adelay/atrim por VIDEOGAP + dynaudnorm)
           6. preview → create_audio_preview (medley o PREVIEWSTART o 60 s)
           7. imágenes → PIL limpia la portada → ffmpeg escala/recorta
           8. sin video o fallo → video estático desde portada (_cover.avi) → bk2 / mp4
           9. vxla → PitchAnalyzer + UltrastarToSingit.main (con caché por mtime)
          10. valida que existan todos los archivos requeridos
          11. registra en name.txt + TSV/XML o JSON
          12. copia los archivos a <output>/<dlc_id>/romfs/Songs/...
         progress_callback(completadas, total)
  └─ señales: log_message → Gui.log, progress → barra, finished/error → reactivar UI
```

## 4. Caché (carpetas de entrada)

Los archivos convertidos se guardan **dentro de cada carpeta de canción** con el prefijo `name_id` y se reutilizan si existen:

| Archivo | Lo crea | Se reutiliza si… | Lo borra "Clear cache" |
|---|---|---|---|
| `<id>.ogg`, `<id>_preview.ogg` | create_audio / create_audio_preview | existe | sí |
| `<id>.png`, `_long.png`, `_InGameLoading.png` | create_cover* | existe | sí |
| `<id>.mp4` (XML) / `<id>.bk2` (JSON) | create_video / create_video_bink | existe | sí |
| `<id>.avi` (intermedio JSON) | create_video | existe | **no** (B-28) |
| `<id>_cover.avi` (video estático) | create_still_video_from_cover_image | existe | **no** (B-28) |
| `<id>.vxla` | UltrastarToSingit | mtime(vxla) > mtime(txt) y sin force_reconvert | sí |
| `<txt>_genius_cache.json` | genius_get_choruses | existe | **no** |
| `demucs_out/` | PitchAnalyzer (slow + aislamiento vocal) | — | **no** |

Consecuencia importante: la caché **no guarda con qué parámetros** se generó (formato, tono, medley, tamaño, still video),
así que cambiar opciones no regenera nada salvo con "Clear cache" o "Force re-generate" (solo vxla). Ver B-12, B-13.

## 5. Configuración

- `config_default.yml` (empaquetado, `bundle_dir()`): valores base. **Faltan** claves que el código usa:
  `clear_output`, `force_reconvert`, `multithreading`, `multithreading_workers`, `vocal_isolation`, `language`
  (el código las lee con `getattr(..., default)`).
- `config.yml` (usuario): lo lee `load_config()` desde `app_dir()` pero lo escribe `Gui.save_config()` en el **CWD** (B-18).
- `deep_override_config` ignora valores `None` del usuario.
- Si "Advanced settings" está desmarcado, `ConvertFiles.main` reemplaza **todos** los tweaks por los por defecto
  (incluidas las rutas de DLC base y el multihilo).

## 6. Dependencias externas

| Herramienta | Uso | Notas |
|---|---|---|
| ffmpeg / ffprobe | todo el audio, imágenes, video x264, duraciones | ffprobe se busca como `ffprobe.exe` junto a ffmpeg o en PATH (B-16) |
| RAD Video Tools `radvideo64.exe binkc` | `.bk2` para 2024+ | en Linux vía `wine` fijo; necesita `gst-plugins-good` (ver README_Linux.md) |
| Genius (web) | detección de estribillos | scraping de HTML + API `search/multi`; sin caché negativa (B-39) |
| CREPE / TensorFlow / librosa | modo `slow` | se cargan desde `plugins/` o el entorno; no están en el venv actual (362 errores en error.log) |
| Demucs | aislamiento vocal en modo slow | `sys.executable -m demucs` — no funciona en el ejecutable congelado |
| SQLite `data/repository/data.db` | catálogo de DLC | `raw_data.xlsx` es la fuente manual |

## 7. Mapa de impacto — "si tocas X, revisa Y"

| Si cambias… | Revisa también |
|---|---|
| `construct_name_id_from_directory_name` (ConvertFiles.py:153) | **copia idéntica** en Gui.py:104; versiones divergentes en tools/cache_recovery.py:9, tools/unpacker.py:10, tools/reverse_vxla.py:14, tools/LetSing_ExtractorPro.py:12; los IDs ya publicados en JSON/TSV de la consola; la caché de las carpetas (cambia el nombre de todos los archivos) |
| `strip_accents` / `sanitize_name` | duplicados en Gui.py:93 / Gui.py:816 y ConvertFiles.py:102/142 |
| Nombres de archivos generados (`_cover.avi`, `<id>.avi`, `_preview.ogg`…) | filtros de `files_avi`/`files_mp3`/`files_jpg` en ConvertFiles.py:713-717 y 751; `Gui.scan_input_folder` (Gui.py:864-867) y su lista `outputs` (Gui.py:896) que usa "Clear cache"; `get_required_files` (ConvertFiles.py:609); `tools/cache_recovery.py` |
| Formato del vxla (`write_vxla_file`, `map_data`) | `tools/unpacker.py`, `tools/reverse_vxla.py`, `tools/LetSing_ExtractorPro.py` (lo leen al revés); caché por mtime (no se regenera solo) |
| Corrección de tono (PitchAnalyzer) | constantes `PITCH_MIN/MAX` (ConvertFiles.py:30); el `-36` fijo en reverse_vxla/unpacker/ExtractorPro |
| Cálculo de tiempos (BPM/GAP/VIDEOGAP) | `UltrastarToSingit.map_data`, `ConvertFiles.create_audio` (desplaza el audio por VIDEOGAP), `create_audio_preview`, `SyncEditor.update_lyrics` (ignora VIDEOGAP), `Gui.is_doubtful_sync`, `tools/desync_detector.py` |
| Claves de configuración | `config_default.yml`, `Gui.set_defaults` (carga), `Gui.save_config` (guarda), `LetsSingUltraStarConverter._run_cli` (flags), `ConvertFiles.main/convert_files` (lectura) |
| Textos de la interfaz | `Gui.update_ui_language` + `locales/es.json` (las claves son el texto inglés literal) |
| Columnas de `PreviewTable` | índices fijos en Gui.py (0 checkbox, 1 play, 2 nombre, 3 sync, 4-7 iconos, 8 orden) y `PreviewTable.on_header_clicked` (B-22) |
| Escritura en name.txt / TSV / JSON | orden respecto a la copia de medios (B-04) y bloqueo entre hilos (B-05) |
| Imports de Qt | `excludes` del `.spec` (excluye `QtMultimedia`, que Gui importa — B-41) |
| Ruta de salida / escudo `_Patch` | ConvertFiles._init_paths:73 **y** Gui.output_path_fv:614 (doble aplicación, B-17) |

## 8. Deuda técnica estructural

1. **Lógica duplicada** de nombres/IDs en 6 archivos → divergencias reales (B-30).
2. `convert_files` es una función de ~300 líneas con una clausura anidada; difícil de probar.
3. Estado global en módulo (`_ffmpeg_path`, `_output_dir`…) → impide dos conversiones en el mismo proceso.
4. `subprocess.run` sin `check`, sin timeout y con la salida descartada → los fallos de ffmpeg/binkc solo se detectan
   después, por ausencia de archivo.
5. No hay pruebas automatizadas (`tools/mass_test.py` es un script con rutas fijas).
6. GUI y lógica mezcladas en `Gui.py` (1 650 líneas): validación, escaneo de disco, parseo de txt, reproducción, config.
7. `.gitignore` muy agresivo (`*/`, `*.txt`, `*.json`, `*.spec`): `requirements.txt` y `.github/workflows/build.yml`
   **no están versionados**; en cambio sí lo están `tools/__pycache__/*.pyc`.
