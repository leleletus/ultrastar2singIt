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

### 2026-10-24 — Biblioteca organizada en el disco local y scripts viejos neutralizados
- La biblioteca rescatada se copia de RetroROMs (que queda intacto como respaldo) a `~/LetsSing`: `songs/` (entrada
  del conversor), `output/`, `workspace/`, `juegos/`, `archivo/`. Sin las 583 copias `.mp4` redundantes. Los vxla
  oficiales y renombrados de la copia de trabajo se añaden sin sobrescribir; después se verifica todo contra el respaldo.
- Comprobado antes de copiar: los 678 `.bk2` del parche anterior están también en las carpetas de las canciones.
- Scripts que podían pisar o borrar canciones (`2cb47d6`): el extractor y `reverse_vxla` no tocan carpetas existentes;
  `clean_audio_cache` solo borra audio generado y pide `--apply`; el script de iTunes ya no sobrescribe el json. Tres
  scripts sueltos sin versionar que borraban `.bk2` se movieron (no borrados) a `archivo/scripts_viejos_NO_EJECUTAR`.
- Conversión de prueba (copias, carpeta temporal) de One Kiss, Symphony, Be the One, Side To Side y Because You
  Loved Me: las tres reconstruidas usan su vxla oficial (letra completa, tono 55–79); `.bk2` idénticos (md5).
  Encontrado y cerrado B-49 (palabras pegadas). El tono `#p1` del rap de Side To Side es correcto: el juego usa la
  misma marca (3187 notas en 48 vxla oficiales).
- Segunda tanda de prueba (Please Please Please, Wolves, Chantaje, Don't Stop the Music, BBHMM): todas convierten,
  `.bk2` idénticos. Wolves con su vxla oficial (letra completa); tonos de Chantaje y Don't Stop dentro de la tesitura.
  Nuevas `tools/usdb_sources.py` y `tools/sync_check.py`: BBHMM tiene el audio de otro video (no se arregla con GAP);
  Please Please Please queda 1,55 s tarde (`#GAP:75990`).

### 2026-10-25 — Biblioteca en ~/LetsSing verificada y primer parche completo
- Copia terminada y verificada contra RetroROMs (0 diferencias; 729 `.bk2` = 729). Se cortó dos veces (apagado y
  cierre de sesión de KDE): ahora corre como servicio de usuario con linger.
- Please Please Please: `#GAP:75990` (copia `.txt.bak`). Respaldo de los 729 `.bk2` con enlaces duros en
  `~/LetsSing/archivo/respaldo_bk2_2026-10-25` (sin ocupar espacio).
- Conversión completa: 661/661 en ~8 min, sin codificar ningún video (todas tenían `.bk2`); ningún `.bk2` cambió
  (mismo inode que el respaldo). Parche en `~/LetsSing/output/0100EE4020D19003` (30 GB, 676 canciones en
  `songs_int.json` = 661 + las 15 oficiales del DLC, como el parche anterior).
- Revisando el parche se encontró y cerró B-50 (letra entera pegada en 112 vxla v2.0); B-49 ajustado al formato oficial.
- Revisión del audio del parche: 48 `.ogg` regenerados (#START/#END y cambios), 613 reutilizados; 659/661 coinciden
  en duración con su fuente. Excepciones: BBHMM (audio de otra versión, ya conocido) y Rockefeller Street, cuyo
  `audio.ogg` era una copia del audio ya convertido (con los 10,94 s de `#VIDEOGAP` incluidos): el parche está bien,
  pero el txt apunta ahora al `.m4a` original (copia `.txt.bak`) para que una regeneración no duplique el silencio.
  En 225 de 272 carpetas `audio.ogg` es idéntico al `<id>.ogg` convertido (copias de un script anterior; sin
  VIDEOGAP no afecta). Es la única canción de la biblioteca con `#VIDEOGAP`.

### 2026-10-31 — Editor de sincronización nuevo
- B-51 cerrado (las letras no aparecían). Editor rehecho como un pequeño editor de video: video, carril de notas
  estilo juego, karaoke, transporte completo con atajos (Espacio, J/L, coma/punto, ↑/↓, Inicio, F, ←/→ para el GAP,
  Ctrl+S) y modo cantar con micrófono para comprobar el tono de las notas.
- Verificado sin pantalla con copias de BBHMM (aviso "la letra termina 15,7 s después del audio") y Take On Me
  (vxla oficial, solo lectura); micrófono simulado una octava abajo: cuenta como acierto, igual que el juego.
- Editor, segunda versión (`SyncModel.py` sin Qt + `SyncEditor.py`): controles con íconos; **cortes** (✂: desde
  una línea, las flechas mueven solo esa parte y lo siguiente; al guardar se mueven los tiempos de esas notas en
  pulsos, con copia `.bak`, y no deja guardar si una parte se monta sobre la anterior); **Analizar voz** (Demucs,
  guardado en `<id>.voice.npz`): la voz se dibuja sobre las notas, un mapa colorea cada línea según coincida con la
  voz y la varita mueve la parte a donde está la voz. Verificado con BBHMM: línea 8 movida +2,24 s → coincide 97 %;
  el txt guardado solo cambia los tiempos (letras, tonos y duraciones idénticos).
- `tools/sync_scan.py`: el mismo análisis para toda la biblioteca, con informe CSV (ok / desfase / parcial /
  otra_version / dudosa). Demucs tarda ~6 min por canción en CPU: las 274 canciones UltraStar, ~18-20 h.
- Editor, partes independientes (pedido tras sincronizar BBHMM): **✂ Inicio** abre una parte en la línea que suena
  y la selecciona; **✂ Fin** la cierra antes de la línea que suena sin mover lo siguiente; mover una parte ya no
  arrastra las demás; cortar nunca mueve nada (la parte nueva conserva su desplazamiento). La parte que mueven las
  flechas queda fija aunque se navegue por la canción; se cambia con clic en el mapa, `[` `]` o **Toda la letra** (G).
  Verificado con una copia del BBHMM guardado: línea 71 de 4:07.02 a 4:08.02 sin tocar el GAP ni las otras partes.
- BBHMM sincronizada a mano por partes (aceptable para jugar). Revisión de las 274 canciones UltraStar lanzada
  como servicio con CPU en modo idle (`~/LetsSing/informe_sincronia.csv`), sospechosas primero.
- La ventana se congeló una vez con el video de BBHMM abierto: hilo principal bloqueado (`futex_wait`, sin CPU),
  no por memoria. Sin permiso de ptrace no se pudo ver el punto exacto; se agregó un vigilante que escribe
  `hang_trace.log` (pila de todos los hilos) si la ventana no responde en 10 s.
- `install_linux_launcher.sh` (acceso en el menú) y `docs/08_USO_EN_LINUX.md`.

### 2026-10-31 (tarde) — Lo que dice el código de Let's Sing 2026 y arreglos de datos
- Volcado IL2CPP de Let's Sing 2026 v131072 (Il2CppDumper bajo Wine; `global-metadata.dat` sacado con nxdumptool).
  Del código: idiomas = English/French/Spanish/German/Korean/Other; temas = Love/Deep/Party (fijos, no se pueden crear
  nuevos sin mod); géneros = Pop/HipHop/Ballad/Rock/RnB/Electro/Country/Latin/Summer; `SpokenLanguages` y `Themes`
  son listas. `SortTypeComparer.Compare` (desensamblado): "Título" ordena por `Singable.Id`, "Artista" por
  `GameSong.Artist`, "Año" por `Year` y luego Id → B-56.
- Primera actualización por MTP sin copiar todo (179 archivos, 12,8 MB); DBI no sobrescribe (B-62).
- Prueba en la consola del usuario: letras y acentos bien; búsqueda de texto busca en artista y título; navegar por
  letra en "Título" seguía al artista (B-56); portadas en blanco/recopilatorio (B-58); Swish Swish duplicada (B-59).
- B-52…B-62 registrados; resumen en `09_HISTORIAL_BUGS.md`.

<!-- Plantilla para nuevas entradas:
### AAAA-MM-DD — Título
- Cambios: …
- Bugs cerrados: B-xx (commit)
- Regresiones detectadas: …
- Pruebas realizadas: …
- Pendiente: …
-->
