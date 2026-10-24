# 05 — Bitácora

## Estado del repositorio (2026-10-21)

- Rama de trabajo: `linux-wine-support` @ `4e1cb35`, **4 commits sin subir** a `origin` (`362d058`, `b98ea4a`, `0844bc6`, `4e1cb35`).
- `origin` = fork `leleletus/ultrastar2singIt`; `upstream` = `ratnapatka/ultrastar2singIt` (`main` @ `69f8814`, v1.0.2).
  No hay commits de `upstream/main` pendientes de integrar. La rama `upstream/18-add-support-for-duets` (duetos) no está fusionada.
- `main` local = `fd9fe37` (1 commit por delante de upstream).
- Sin versionar en la raíz: `fix_songs.py`, `clean_output_files.py`, `clean_output_json.py` (scripts puntuales con rutas fijas).
- `version.py` = 1.1.0, pero existe el tag `v2.0.0` en `9ba81f4` → versión inconsistente.
- Archivos pesados o ajenos en la carpeta (ignorados por git): `python-installer.exe` (29 MB), `venv/`, `unity_env/`, `build/`, `dist/`,
  `error.log` (760 KB), `test_dir_`, `test_dir___1`, `recovered_lyrics/` (vacía), `textasset_names.txt` (vacío).

## Historia por fases (según git)

| Fase | Periodo | Autor | Commits clave | Resumen |
|---|---|---|---|---|
| 0. Origen | 2025-08 | ratnapatka | `ca85be0`… | scripts `ultrastar2singit.py` + `convertFiles.py` (base de dh4rry/kosei) |
| 1. Afinado | 2026-01 → 02 | ratnapatka, omnialord | `4df360c`, `da53b6c`, `5b415ce`, `a1a1a72`, `5e3feff`, `9504770` | 2025 por defecto, analizador de tono (slow), fast por defecto, saneado de nombres de carpeta, mejor detección de estribillos, `--no-video` |
| 2. GUI | 2026-03 | ratnapatka | `403de92` → `ee4e26c` (v1.0.0) | GUI PySide6, BD de DLC, stop event, plugins para slow, compilación |
| 3. Mantenimiento upstream | 2026-04 → 05 | ratnapatka, omnialord | `7fee587`, `b75a6fa`, `c4c569c`, `78a5b28`, `3e46d42` (v1.0.2) | DLC 2025/2026, `~`→`-`, barra de progreso, no copiar conversiones incompletas, workflow de release, **revertido** el renombrado de archivos |
| 4. Fork Linux | 2026-09-17 | leleletus | `fd9fe37` | soporte Linux/Wine, bug de idioma del JSON |
| 5. Gran revisión | 2026-09-29 → 30 | djvemo | `5f0d14e`, `a4779e2`, `eb32bc7`, `4765477` | Sync Editor, multihilo, herramientas, CI Win+Linux, detector de desfase. Origen de R-01 |
| 6. Pulido y herramientas | 2026-10-02 → 03 | djvemo | `2b47edb`, `4cb04ff`, `8930b27`, `3f60d56`, `8f7a37f`…`2c2beb9`, `fa8c111` (tag v2.0.0), `3f07553`, `77a1358`, `1194ff6`, `37f8212`, `eaa98b7`, `0899b0f`, `1e04eba`, `edddba3` | pasajes/espacios, Play, `-bf 0`, dynaudnorm, i18n, bpm en JSON, JSON base desacoplado de la copia de medios, reverse vxla. Origen de R-03, R-06, R-07, R-09 |
| 7. Correcciones (sin subir) | 2026-10-03 → 05 | djvemo | `362d058`, `b98ea4a`, `0844bc6`, `4e1cb35` | escudo `_Patch`, ExtractorPro, IDs solo ASCII (cuelgues en Switch), AVI para binkc bajo Wine, limpieza EXIF. Origen de R-02, R-04, R-05 |

## Evidencia de campo (`error.log`, 2026-09-17 → 2026-10-05)

| Fallo | Veces | Bug |
|---|---|---|
| `No module named 'tensorflow'` | 362 | B-38 |
| `Extra data` (JSON destino corrupto) | 119 | B-03 |
| `Unexpected UTF-8 BOM` | 106 | B-03 |
| `Failed to generate … from binkc` | 38 | B-44 |
| `Could not find '<búsqueda>'` (Genius) | 24 | B-39 |
| `Expecting value` (JSON vacío/corrupto) | 8 | B-03 |
| `IndexError: list index out of range` (create_audio) | 5 | B-15 |
| `can't register atexit after shutdown` | 5 | B-45 |
| `Demucs vocal isolation failed` | 5 | B-38 |
| `could not convert string to float: b''` (ffprobe) | 1 | B-15 |
| `module 'ConvertFiles' has no attribute 'main'` | 2 (09-17) | histórico, ya resuelto |

---

## Entradas

### 2026-10-21 — Auditoría completa
- Lectura completa de los 27 scripts Python (5 734 líneas), configuración, spec, workflows, `.gitignore`, documentación y `error.log`.
- Pruebas puntuales con el venv del proyecto:
  - `QThread.finished` se emite aunque se redefina en la subclase → confirma B-24 (mensaje de éxito tras error).
  - `QLineEdit.setText(None)` no falla (descartado como bug).
  - Corrección fast: notas 80/85/95 → +48; notas 20/30/40 → +41 → confirma B-06.
- Lectura con salto de línea universal: los `\r` de archivos CRLF **no** llegan a los valores de los tags (descartado).
- Creada la documentación en `docs/` (este directorio). Ningún cambio de código todavía.
- Pendiente de decidir con el responsable: orden de ataque (ver plan en `06_BACKLOG_Y_MEJORAS.md`), si se suben los 4 commits locales
  antes de empezar, y qué hacer con los scripts sueltos de la raíz.

### 2026-10-21 (2) — Primera tanda de arreglos
- Directivas del responsable: **nunca borrar ni invalidar los `.bk2`** (días de codificación); confirmar antes de cualquier
  borrado; "IA" solo para las funciones de IA del programa (voz, tonos, notas largas).
- Los 4 commits locales sin subir se conservan (aportan el arreglo de Wine y de los IDs que colgaban la Switch); sus
  regresiones se corrigen encima.
- Commits: `cd87f8d` letras/codificación, `8426e7e` tono por octavas, `30669e3` integridad del parche y protección de videos,
  `7fc2657` interfaz, `27f8a17` herramientas de extracción, `cd77032` .pyc, `b779bc6` Recover cache.
- Bug nuevo encontrado y cerrado: **B-46** (las letras con acentos se borraban). Explica los problemas del francés.
- Pruebas de punta a punta en una carpeta temporal con copias: JSON (con Bink real vía Wine) y XML; segunda ejecución sin
  ninguna recodificación (`.bk2` con el mismo mtime); rescate de `.bk2` huérfanos antes de limpiar la salida; ida y vuelta
  vxla → txt → vxla con 0 diferencias de tono; prueba de la GUI sin pantalla (validación, Clear cache con y sin
  confirmación, orden de la tabla, idioma).
- Pendiente: conectar el disco de canciones (no estaba montado) y revisar las canciones de `07_CANCIONES_PROBLEMA.md`;
  probar el resultado en la consola; build con PyInstaller.

### 2026-10-23 — Rescate del disco, interfaz nueva y diagnóstico de la biblioteca
- Disco de canciones (exFAT) corrupto por apagados inseguros: rescatados 53 284 archivos (324 GB, verificados
  uno por uno) a RetroROMs con `~/rescate/rescate_exfat.py`. Windows se clonó al disco de 512 GB y Linux
  ocupa el disco de 1 TB completo.
- Interfaz rediseñada (`80b4a59`): tabla rápida, estados por canción, convertir marcadas, traducción completa.
- Comparación con archivos oficiales de Let's Sing 2024: passages y UTF-8 como el juego; uso directo de los vxla
  oficiales (`7b5a82a`). Soporte de #START/#END (`b074be4`). Opción para no usar internet (Genius).
- Diagnóstico de las 678 canciones con solo sus .txt: 404 reconstruidas de DLC, ~50 sin letra, ~8 con letra pegada,
  355 con tono transpuesto por el método viejo, 31 con #START, 21 con artista/título equivocado.
- Pendiente: bajar los vxla oficiales del megapack (~25 MB), devolver la biblioteca al disco local con Wi‑Fi y
  aplicar las herramientas en el orden de `07_CANCIONES_PROBLEMA.md`; probar en la consola.

### 2026-10-24 — Revisión del historial: regresiones en video, caché e ID interno
- Revisados los 28 commits del fork contra `upstream/main` (diff por archivo). Nuevas regresiones: R-11 (tasa `/D` de
  Bink perdida), R-12 (copias "de caché" del extractor), R-13 (cambios del algoritmo del ID). Historia completa del ID en
  `04_REGRESIONES.md`.
- Bugs cerrados: B-47 (`b9d454f`), B-48 (`b9d454f` + extractor/reverse_vxla). `rename_songs` respeta `Artista - Título`
  (`52791fe`).
- Medición en RetroROMs (solo tamaños y cabeceras PNG): 583 copias `.mp4` redundantes (28,15 GB), 596 portadas de tamaño
  incorrecto; 0 IDs repetidos en las 661 carpetas.
- Pruebas: 28 unitarias OK; extractor con un megapack de prueba (sin copias, portada encontrada por el ID oficial);
  simulacro de `rsync --exclude-from` con archivos vacíos (583 excluidos, `video.mp4` y `.bk2` intactos).
- Pendiente: restaurar con Wi‑Fi usando la lista de exclusión; convertir y probar en la consola.

<!-- Plantilla para nuevas entradas:
### AAAA-MM-DD — Título
- Cambios: …
- Bugs cerrados: B-xx (commit)
- Regresiones detectadas: …
- Pruebas realizadas: …
- Pendiente: …
-->
