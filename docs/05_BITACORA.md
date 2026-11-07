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
- Aplicado: 215 años reales (183 MusicBrainz, 32 iTunes; 25 sin dato fiable se dejan), 230 portadas de DLC con la
  carátula del single/álbum (4 sin resultado conservan la suya), portadas en blanco reemplazadas. Swish Swish duplicada
  movida al archivo. Parche regenerado entero con los IDs de juego (660 canciones, 729 `.bk2` intactos; el único
  `.bk2` rescatado era el de la versión quitada, guardado en `archivo/rescatados_al_convertir`).
- Pendiente con el usuario: copiar el parche nuevo a la Switch (`switch_update.py --apply --prune`: copia todo con
  los nombres nuevos y quita los viejos que conoce la foto).

### 2026-10-31 / 11-01 — Trabajo largo sin la consola
- Revisión de voz de las 274 canciones UltraStar + 20 oficiales de referencia (Demucs, ~4 min por canción).
  Calibración con las oficiales: los falsos "desfases" eran líneas sueltas (frases repetidas); ahora solo cuenta un
  bloque de 3+ líneas desplazadas igual, y "dudosa" solo bajo 30 % de coincidencia (las oficiales van de 38 a 77 %).
  Resultado: 278 bien, 11 con una parte desfasada, 1 entera (Daft Punk −1,1 s), 3 dudosas; 0 falsas alarmas de
  desfase en las 20 oficiales. La columna Sinc. de la interfaz muestra el resultado de cada canción.
- Datos para 2026: géneros reales (tienda iTunes, 419 canciones; antes 613 "Pop"), dificultad estimada de las notas
  (ajustada con 59 canciones oficiales), voz por artista (MusicBrainz, invitados del título y control por el tono:
  ante la duda "Both"), portadas originales (sin recopilatorios ni singles de otra canción; oficiales primero).
- Validador del parche (`tools/validate_patch.py`): 675 canciones, 0 problemas. 729 `.bk2` intactos.
- Bugs cerrados: B-20, B-35, B-41 (ejecutable de PyInstaller probado: la GUI arranca), B-42 (instalación limpia
  probada; faltaba numpy). Queda B-61.
- Incidente: el sistema cerró VS Code por falta de memoria. Causa: `/tmp` (y la carpeta de trabajo) está en RAM y
  tenía 5,2 GB de archivos temporales, más dos separaciones de voz en paralelo y una compilación. Corregido: los
  temporales de la separación van a `~/.cache/letssing_converter`, las tareas pesadas de una en una y con
  `MemoryMax`.
- Pendiente con el usuario: copiar el parche nuevo a la Switch (`switch_update.py --apply --prune`, ~30 GB por
  los nombres nuevos); revisar a mano las 15 canciones del informe; mod (diseño en `10_MOD_SALTAR_INTRO.md`).

### 2026-11-01 — Videos reales, biblioteca al estilo usdb_syncer, limpieza, mod funcionando
- Herramientas en la app: apartado **5. Opciones avanzadas** (`ToolsPanel.py`, 10 herramientas como proceso aparte,
  de una en una, las pesadas con límite de memoria) y clic derecho → "Volver a codificar el video" / "Añadir un video
  (archivo o enlace)" (`tools/align_video.py`: compara el sonido, recorta, no guarda si es otra versión o imagen fija).
- usdb_syncer: apuntaba al disco dañado (B-63); 658 de 660 carpetas con nombres "Artista - Título" como los deja
  usdb_syncer (`usdb_restore_names.py`, el `.usdb` los reconoce); la del directo de Madonna de 2003 se queda con
  nombres cortos (ruta demasiado larga para Windows).
- Videos: 28 `.bk2` eran la portada fija aunque había videoclip (B-66). Recodificadas 27 desde los `video.mp4`
  recortados por el usuario (intactos), Merry Christmas con su `.bk2` oficial de 2024, Maria y Something About Us con
  videoclip alineado. Quedan 14 sin video (`~/LetsSing/VIDEOS_PENDIENTES.md`). El conversor ahora rehace solo un `.bk2`
  fijo cuando la carpeta tiene un video con movimiento, con cualquier nombre (el viejo va a `_replaced_videos`).
- Apagón a mitad de la recodificación: 17 terminadas intactas, se borraron los `.avi` a medias de las 2 cortadas y se
  reanudó con las 10 que faltaban.
- Limpieza (con confirmación del usuario): borrados `workspace`, `archivo`, volcados de 2018–2024/ABBA/Country/Queen
  (todo verificado en el servidor), `_replaced_videos` y `.bak`; libres 119 GB. Se quedan `songs`, `output` y
  `juegos/Let's Sing 2026`. Desde ahora la limpieza mueve a `_papelera` (el usuario se molestó porque 505 restos se
  borraron sin una confirmación final).
- Rendimiento: "Recomendado: N" junto a Hilos, medido en el PC (2 a la vez codifican 0,7 min de video por minuto).
- Switch: copia completa desde cero tras vaciar la carpeta (B-67), con reintentos por MTP (B-68). Verificada.
- Mod de saltar intro (`mods/skip_intro`): ZR/ZL durante el intro → 3 s antes de la primera nota. Primero cerraba el
  juego (B-69, faltaban permisos en `main.npdm`); ya funciona y está publicado:
  https://github.com/leleletus/ultrastar2singIt/releases/tag/skip-intro-v1
- Vistas previas desde el coro (B-70); Something About Us −1080 ms (B-71); BBHMM: 10 líneas del final ajustadas a la
  voz (79% → 82%), quedan 59/78/80 y dos ad-libs para revisar a oído.
- Pendiente: copia de las vistas previas a la Switch (en curso), Citron con la actualización y el DLC (al cerrarlo
  se configura `external_content_dirs`), mejoras del mod (fin al acabar la letra, video sin acelerar).

### 2026-11-01 (noche) — Proyecto portable, mod en su repositorio, docs al día
- Mod de saltar intro: repositorio propio `leleletus/letssing2026-skip-intro` (código, `build.sh` reproducible,
  compatibilidad detallada: solo la actualización v131072, build ID `1C344DD17322D4FA3E8F50063340C7D0`). En este
  proyecto `mods/` queda en `.gitignore`. `build.sh` desde cero: `main.npdm` idéntico al release y `subsdk9` con el
  mismo código máquina (solo cambian las rutas de compilación incrustadas en `.rodata`).
- Sin rutas del PC del autor: yt-dlp (`YT_DLP`, PATH, usdb_syncer o módulo), RAD bajo `$WINEPREFIX`, `start_linux.sh`
  sin venv obligatorio, `config.yml.antes_limpieza` fuera de git (`config.yml.*` ignorado), guías con marcadores
  `<proyecto>`/`<canciones>`/`<salida>`.
- `switch_update.py --first-copy` (y "Primera copia" en el apartado 5): en un PC sin foto de la Switch copia el parche
  entero, solo si la carpeta del DLC en la Switch falta o está vacía. Probado con `kioclient` sobre carpetas locales
  (inexistente, vacía, con archivos → se niega, segunda pasada).
- 01, 02 y 06 reescritos con el estado actual; índice de `docs/` con 11 y 12; tabla de 03 con B-63…B-71.
- Pruebas: 51 OK.

### 2026-11-02 — Citron: arranque con el mod y micrófono
- Citron (nightly `308bc267c`) lanzado con `APPIMAGELAUNCHER_DISABLE=1` dentro de una unidad de systemd
  (`MemoryMax=10G`); la carpeta de contenido externo apunta a la del juego. Carga la actualización 0.2.0 (v131072), el
  DLC 3 y el mod (`[exlaunch] [ skipintro ]`); el juego llega al menú sin errores (~5 GB).
- Micrófono del PC en Citron: no funciona y no es configuración. El juego (FMOD) pide la lista de micrófonos al
  servicio `audin` cada segundo (`ListAudioInsAutoFiltered`) y nunca abre ninguno (`OpenAudioIn`), con cubeb y con
  SDL, con el micrófono automático o fijado por nombre. Es una limitación de la emulación de la entrada de audio.
  En la consola real, un micrófono USB va por esa misma ruta (`MicrophoneFmod`).

### 2026-11-02 — Modo Feat (B-73) y secciones de Genius
- En Feat el juego se cerraba con cualquier canción convertida. Comparando las 15 oficiales del DLC 3 con el código
  (`Singable.AssetType`, `FeatSegment`, `SongBeats`): faltaba `vxla_feat/<id>_feat.vxla` y `"coopfriendly": "Coop"`
  significa "tiene segunda voz". Todo en `docs/13_MODO_FEAT.md`.
- `FeatVxla.py`: letra feat como las oficiales (15/15 capas idénticas), segmentos que cubren la canción con cortes en
  inicio de página (estribillos juntos; estrofas por sección y por la pausa más larga: 96/133 cortes oficiales),
  segunda voz y beats (numpy + ffmpeg; tempo 12/15, pulsos 76 %). Líneas repetidas como estribillo si no hay otra
  fuente; tramos juntos a menos de 8 s se unen.
- `SongSections.py`: secciones y cantantes de Genius (también por línea: normal / cursiva / negrita), caché
  `<txt>_genius_sections.json`. Duetos de UltraStar: voz `P2`.
- Probado en la consola: Sofia y Un año sin lluvia en Feat (antes se cerraban). Citron no sirve para probar Feat: pide
  mantener una nota en el micrófono antes de empezar.
- Las 660 convertidas dos veces (la segunda en 75 s, todo en caché): 0 errores, 724 `.bk2` intactos, validador sin
  problemas. Tramos juntos por canción: 3 la más común (321), mediana 26 s; 5 sin ninguno; 106 con segunda voz.
- Encontrado B-72: la búsqueda de estribillos antigua no lee cabeceras de Genius con nombres enlazados (75 canciones).
- Pruebas: 61 OK.

### 2026-11-02 (2) — B-72 y copia a la Switch
- B-72 cerrado: la búsqueda de estribillos lee Genius como SongSections. Solo se releen las 75 cachés con página y
  sin estribillos (72 releídas, 51 con estribillos) y solo esas canciones regeneran su vxla (39; las demás son de DLC
  y usan su letra oficial). Conversión completa: 0 errores, 724 `.bk2` intactos, validador sin problemas.
- Copia a la Switch: 1356 archivos (46 MB): 658 vxla_feat, 658 beats, 30 vxla, 7 vistas previas, la lista. Ningún video.

### 2026-11-05 — usdb_syncer (B-74) y canciones que USDB no tiene (SongMaker)
- usdb_syncer no marcaba ninguna canción como descargada: la carpeta que escribí a mano el 1-11 como texto la ignora
  (usa `~/songs`). Guardada como `Path` con su propia API y sincronizada: 271 reconocidas.
- SongMaker (`SongMaker.py`, `tools/make_song.py`, Herramientas → Crear una canción que no está en USDB…): videoclip
  de YouTube (sin cortar si contiene la canción seguida; rehecho por tramos si hay escenas en medio), letra con tiempos
  de LRCLIB (la versión y el desfase que mejor encajan con la voz), notas desde la voz (Demucs), sílabas en español,
  inglés y coreano romanizado. Ver `docs/14_CANCIONES_SIN_USDB.md`.
- Hechas: Paty Cantú (Goma de Mascar, Afortunadamente No Eres Tú, Clavo Que Saca Otro Clavo, Suerte), TWICE (SIGNAL,
  Strategy), LE SSERAFIM (Smart, SPAGHETTI, BOOMPALA). Coincidencia con la voz 43–64 %, desplazamiento mediano 0,00 s
  en todas. SIGNAL tiene 15/76 líneas a más de 1 s: revisar en el editor.

### 2026-11-05 (2) — 41 canciones nuevas en la Switch
- Lista de 67 canciones pedidas (`~/LetsSing/canciones_pedidas.json`, informe `ESTADO_CANCIONES_PEDIDAS.md` con
  `tools/song_status.py`): 23 ya estaban, 2 de USDB (Bailando, Milkshake), 39 fabricadas con SongMaker (Paty Cantú,
  TWICE, LE SSERAFIM, BLACKPINK, LISA, JENNIE, (G)I-DLE, IZ*ONE, MOMOLAND, latinas y japonesas en romaji), 3 fuera.
- Incidencias: corte de internet (17 fallaron → fase `--fetch-only` que espera a la red), apagado por batería (scripts
  en /tmp perdidos → `tools/make_songs.py` reanudable y perfil de energía "performance" retenido), videoclip que empieza
  después de la canción (Sin Aliento), duetos sin P2 en el modo clásico (`merge_duet`).
- Sincronía de las 39: desplazamiento mediano 0,00 s en todas, coincidencia con la voz 40–79 %. Repasar en el editor:
  SaWaDiKa, SIGNAL, You & Me, Fiel (Remix), AS IF IT'S YOUR LAST, New Woman, Dutty Love, BOOMPALA. Video = portada fija:
  Koi no Uta, Maladie. Aviso: Gyal You a Party Animal (letra 6,5 s más larga que el audio).
- Parche: 716 canciones, 0 problemas; 765 `.bk2`. Switch: 288 archivos (1,3 GB) copiados y verificados.

### 2026-11-05 (3) — LISA, notas como las oficiales y editor de letra
- Lote de LISA (23 canciones, solistas y colaboraciones, `~/LetsSing/cola_lisa.json`): descargadas, fabricadas y
  convertidas sin fallos (unidad `letssing-lisa`, perfil "performance").
- Queja del usuario tras probar LISA y Goma de Mascar: notas que saltan demasiado, letra donde no se canta, rap sin
  tratar. Medido en vez de supuesto (`tools/note_style.py`, 387 oficiales frente a 61 fabricadas): las oficiales
  tienen ~1 nota por sílaba, notas de 0,24 s (1 % por debajo de 0,12 s), 9 % de saltos de 5+ semitonos y el rap en
  notas sin tono (`#p1`, 4,5 % de las notas); las fabricadas, 1,22 notas por sílaba, 0,15 s, 41 % cortas y 17 % de
  saltos grandes.
- Nuevo generador de notas (`SongMaker.make_notes`, versión 2), afinado contra 20 oficiales con su voz analizada
  (`tools/note_calibrate.py`: recibe solo las líneas de la letra y la voz y se compara con las notas oficiales):
  sílabas en los ataques de la voz (programación dinámica por línea), una nota estable por sílaba, semitonos en la
  tonalidad de la canción, temblores y errores del detector nivelados, octavas por línea, rap detectado (deslizamiento
  del tono, voz sin tono, notas que tiemblan; líneas seguidas). Resultado: 388 notas por canción (oficial 394), salto
  medio 1,84 semitonos (1,86), rango 20,5 (21), 2 % de notas cortas, tono ±1 semitono 79 % (el detector de tono da
  83 % como mucho con los tiempos oficiales), inicio de sílaba a 0,13 s de mediana (antes 0,19).
- `tools/remake_notes.py`: rehechas las 62 canciones fabricadas (txt anterior en `~/LetsSing/_papelera/notas_v1/`)
  y reconvertidas (solo vxla y Feat; los `.bk2` no se tocan). Parche: 739 canciones, 0 problemas.
- Editor de sincronía: borrar la sílaba seleccionada con sus notas (Supr), borrar la línea (Ctrl+Supr), corregir el
  texto de una nota (doble clic) o de la línea (T, un trozo por nota separado por `|`); las notas de rap se pueden
  seleccionar.
- Letras (versión 3 de las notas): ninguna oficial lleva paréntesis y 541 de 3367 líneas fabricadas (16 %) traían
  coros de LRCLIB entre paréntesis cantados como sílabas de la voz principal → se quitan (`SongMaker.lead_vocal`).
  Palabras pegadas: 0 (la unión de sílabas sobrantes de la versión 1 ya no existe); sílabas sobre silencio: 0,3 %.
  Las 62 rehechas otra vez (txt de la versión 2 en `_papelera/notas_v2`) y reconvertidas; parche 739, 0 problemas.
- Versión 4 de las notas: lo quitado fue el 6,6 % de las palabras (1421 de 21 599): ecos («Baila (baila)»), coletillas
  («(yeah)», «(woh)») y firmas («(ATL Jacob)», «(Mr. Doble U)»); el estribillo nunca se tocó. Pero 36 líneas enteras
  entre paréntesis desaparecían y varias sí se cantan solas (el gancho de vocales de «aiue», «(El destino nos unió)»
  en Destino): una línea entera entre paréntesis ahora se conserva sin ellos (si no se canta, se borra en el editor
  con Ctrl+Supr; una línea quitada no se puede volver a añadir allí). Rehechas las 12 afectadas (txt anteriores en
  `_papelera/notas_v3`) y reconvertidas, sin tocar los .bk2; parche 739, 0 problemas.
- README: guía completa del editor de sincronía (cada botón, su icono, nombre en español y atajo).

### 2026-11-05 (4) — Sílabas colocadas por un modelo de habla (versión 5) e informe de las fabricadas

- Modelo: MMS forced aligner (wav2vec2 CTC de 1130 idiomas en letras latinas, `MahmoudAshraf/mms-300m-1130-forced-aligner`,
  1,2 GB) cargado con `transformers` (torchaudio no existe para torch 2.14 y no se bajó torch). Viterbi CTC propio por
  línea (`VoiceAlign.align_line`). Las sílabas de SongMaker ya están en letras latinas (coreano romanizado, japonés en
  romaji), así que sirve para todos los idiomas. Sin GPU: ~3 min por canción con Demucs. La descarga por el protocolo
  xet de Hugging Face se quedaba parada en 0 bytes: `HF_HUB_DISABLE_XET=1`.
- Calibrado con 20 oficiales (`note_calibrate.py --align`): cada línea se busca desde 0,6 s antes, nunca antes del
  final de la anterior (si no, la primera sílaba se quedaba con el final de la línea de atrás: 14 % → 5 %); dos sílabas
  a menos de 0,18 s se separan (el modelo pone la primera tarde y la segunda pronto: notas cortas 16 % → 3 %); la nota
  sigue hasta la siguiente sílaba si el hueco es < 0,25 s, con el tono medido solo en la parte cantada; confianza
  < −6 → método anterior (en esas líneas el modelo falla un 35 %). Resultado: sílabas a más de 0,3 s 23 % → 4 %,
  inicio 0,14 → 0,03 s, tono exacto 69 → 72 %, rap en U Can't Touch This 67 → 78 %.
- Fallo arreglado: los punteros del Viterbi eran int8 y desbordaban en líneas de más de 63 letras.
- `tools/align_voices.py` (lote reanudable, unidad `letssing-align`, 82 canciones en 3 h 44 min) y las 62 rehechas
  (txt v4 en `_papelera/notas_v4`) y reconvertidas (62, 0 fallos, ningún `.bk2` tocado); parche 739, 0 problemas.
- Antes, la Switch se actualizó con la versión 4 (23 de LISA + 62; 277 archivos, 596 MB, respaldo
  `switch_backup_2026-11-05_163430`).
- `tools/songmaker_report.py` → `~/LetsSing/INFORME_SONGMAKER.md`. Comprobado con las oficiales que las medidas contra la
  propia voz no son la verdad (las notas oficiales dan 16 % de líneas «desfasadas» y 53 % de coincidencia), así que
  «revisar primero» solo usa lo que no falla con ellas: 82 avisos en 29 canciones; 497 líneas dudosas aparte; 15
  canciones donde el modelo reconoce < 75 % de las líneas (Cut U Off 46 %, Cristina 45 %: ningún desfase global lo
  mejora, es la voz o la letra de LRCLIB).
- Pendiente (B-75): en líneas ligadas un 23 % de las sílabas cae a más de 0,3 s de su sitio; con volumen y tono no
  se distingue dónde acaba una sílaba (haría falta alinear la letra con un modelo de habla).

<!-- Plantilla para nuevas entradas:
### AAAA-MM-DD — Título
- Cambios: …
- Bugs cerrados: B-xx (commit)
- Regresiones detectadas: …
- Pruebas realizadas: …
- Pendiente: …
-->

### 2026-11-06 — Editor: alargar/mover notas, sílaba bajo cada nota, voz de las canciones de SongMaker

- Pedido al revisar Queencard («ni?» más corto que la voz). Arrastrar el borde derecho de una nota la alarga o acorta,
  el izquierdo mueve su inicio y el centro hacia los lados la mueve en el tiempo (el primer movimiento decide: lados =
  tiempo, arriba/abajo = tono); `Alt+←/→` mueve un pulso, `Ctrl+Mayús+←/→` acorta/alarga un pulso. En pulsos enteros y
  sin pasar a las notas vecinas. `SyncModel.rewrite_txt(note_times=…)` escribe inicio y duración (arreglado de paso un
  nombre de variable reutilizado, `rest`, que habría vaciado el texto de la primera nota de una línea movida).
- La sílaba se dibuja bajo cada nota.
- Los puntos de la voz no salían en las canciones de SongMaker: su `voice.npz` es del `.m4a` y el editor reproduce el
  `.ogg` convertido, así que `load_voice` lo descartaba por tamaño. Ahora `voice_of_source` lo usa movido al tiempo del
  `.ogg` (VIDEOGAP − recorte de #START; 0 en SongMaker).
- GUI: casilla «Solo hechas con SongMaker».
- Añadir sílabas que faltan: botón «Dividir nota» (S) y «Corregir texto» con más trozos que notas. Lo escrito se compara
  con lo que había (difflib): un trozo añadido divide la nota de antes (la primera versión dividía la nota más larga de
  la línea y corría todas las sílabas; visto al probarlo), uno cambiado cambia su nota y uno quitado deja `~`. Las notas
  nuevas van al final de `all_notes` con `order` (orden en el tiempo); `rewrite_txt(inserted_notes=…)` las escribe
  tras la nota del archivo que siguen.
- Moverse por la canción: rueda del ratón sobre el carril o el mapa (0,5 s; 2 s con Ctrl) y arrastrar un sitio vacío
  del carril.

### 2026-11-07 · Editor: guardar con notas borradas, deshacer paso a paso
- Goma de Mascar no se podía guardar («line 18 would start before the end of line 17»): `rewrite_txt` contaba las
  notas borradas al comprobar si las líneas se pisan (B-76). Arreglado; la edición abierta se rescató inyectando el
  arreglo en el programa en marcha (`sys.remote_exec`, con sudo por `ptrace_scope=1`) y se guardó bien.
- Deshacer: historial de estados (`state`/`restore_state`) grabado una vez por acción (QTimer a 0 tras
  `refresh_labels`; un arrastre se graba al soltar). Ctrl+Z, Ctrl+Y / Ctrl+Shift+Z, hasta 500 pasos. «Deshacer todos
  los cambios» pregunta antes y también se puede deshacer.
- `Gui.open_sync_editor` hace `gc.collect()` al cerrar el editor: los cerrados quedaban vivos en ciclos de referencias.
- Selección de varias notas (pedido del usuario): Ctrl+clic, Shift+clic (tramo), Shift+arrastrar en vacío (recuadro
  por tiempo), Ctrl+A (línea), Esc (ninguna). Arrastrar una seleccionada o Alt+flechas mueve todas juntas
  (`group_range`: hasta la primera nota no seleccionada), Shift+arriba/abajo cambia el tono de todas y Supr las borra.
- Esc cerraba el editor **sin preguntar** (`reject` no pasaba por `closeEvent`): ahora pregunta si hay cambios.

### 2026-11-07 · Cristina: letra completa de Genius colocada por el modelo de habla
- El usuario: Cristina «muy mal», le falta letra («Hay mucha demencia…» al empezar). LRCLIB solo tenía la versión
  del disco TumbaGobierno (3:07, letra hasta 1:38, sin los versos de Justin Quiles y Nacho); el video dura 3:19.
- `SongMaker.lyrics_from_genius`: la letra de `<name>_genius_sections.json` (sin coletillas, `lead_vocal`; líneas de
  más de 40 caracteres partidas por la coma del medio) se busca entera sobre toda la canción con el modelo de habla
  (un Viterbi CTC de 10 000 cuadros, 0,6 s) y cada línea se mide otra vez en su sitio. `songmaker.json` lleva
  `"lyrics": "genius"` y las líneas con tiempo van en `lyrics_aligned.json` (`remake_notes` las usa).
- Cristina: 82 líneas (antes 42), la primera nota a 9,0 s (voz a 9,3 s; antes 14,8 s), letra hasta 3:03 (antes
  1:58), sílabas colocadas por el modelo en el 84 % de las líneas (antes 45 %). 12 líneas dudosas (estribillo con
  coletillas encima).
- Spotify/Shazam: Shazam no da tiempos; la letra con tiempos de Spotify es de Musixmatch y pide sesión. No hace
  falta: con la letra completa el modelo encuentra los tiempos.
- Pasada a todas las de SongMaker (pedido del usuario; Goma de Mascar fuera, corregida a mano): LRCLIB contra Genius
  medidos igual (líneas cuyas sílabas el modelo reconoce en su sitio, y hasta dónde llega la letra frente al final
  de la voz). 26 sin Genius (no la encontró al convertir, casi todas de LISA). Genius solo donde mejora ≥ 5 puntos o
  completa una letra que se cortaba 15 s+ antes: Dutty Love, Virtual Diva, Oddloop, BOOMPALA, SPAGHETTI, New Woman,
  SaWaDiKa, aiue (LRCLIB acababa en 1:04 de 3:41), Suerte, Tempted to Touch, SIGNAL, Strategy (le faltaban 37 s).
  Maladie no: sin la cola acababa antes que LRCLIB.
- Genius trae a veces líneas que esa versión no canta y el modelo las amontonaba tras la última voz (Suerte: 4 en
  1 s): `align_lyrics(voice_end=…)` deja fuera lo que cae más de 1 s después. Genius marca algunas líneas `*así*`:
  se quitan los asteriscos.
- Alcaline y Fiel (Remix), editadas a medias: la versión del usuario sale igual o mejor que la regenerada (100 % y
  93 %), se quedan. Queencard: la del usuario está completa salvo la repetición final «You wanna be the kwinka?» a
  3:10 (el modelo la oye ahí, -1,9), añadida sin tocar lo demás. Copias en `~/LetsSing/_respaldo_editor/`.

### 2026-11-07 · Windows sigue funcionando; release v1.2.0 (exe + AppImage)
- GitHub Actions no corre: la cuenta está bloqueada por un problema de facturación (los releases automáticos de
  septiembre y octubre fallaron por eso en 4 s). Las comprobaciones se hicieron en local.
- Windows probado con un Python de Windows real bajo Wine, en un prefijo aparte (`~/.cache/letssing_wintest`, sin
  tocar `~/.wine`): Python 3.14 no sirve en Windows porque `pytablericons` pide `pygame` y no tiene rueda para 3.14;
  con 3.13 pasan los 78 tests, el programa abre y convierte. Archivos abiertos sin `utf-8` buscados con `ast`: solo
  `tools/song_status.py` importaba (arreglado).
- La misma canción (Paty Cantú - Suerte, ruta con tilde) convertida en Windows (código y .exe) y en Linux (código y
  AppImage) da archivos idénticos byte a byte, también el .bk2 recodificado con RAD Video Tools (directo en el .exe,
  por Wine en el AppImage).
- AppImage: `packaging/build_appimage.sh` lo compila en Debian 12 con podman (glibc 2.36: vale para Linux de los
  últimos años, no solo para CachyOS). Fallo encontrado al probarlo: ffprobe heredaba el `LD_LIBRARY_PATH` del
  empaquetado y no arrancaba; `LetsSingUltraStarConverter._clean_child_environment` lo devuelve a su valor.
- Release v1.2.0 en el fork (leleletus) con `LetsSingConverter-1.2.0-windows.exe` y
  `LetsSingConverter-1.2.0-x86_64.AppImage`. Los ejecutables no llevan Demucs ni el modelo de habla.

### 2026-11-07 · Editor: tono desde la voz (P)
- El usuario movió FANCY (-0,65 s) y Tarantino (+5,3 s) en el tiempo y preguntó si el tono (altura) de las notas
  seguía bien: no, SongMaker lo midió con la voz donde estaban antes. `SongMaker.pitches_from_voice` lo mide otra vez
  donde están ahora, igual que `make_notes` (parte estable, octava de la línea, escala de la canción); botón «Tono
  desde la voz» (P) para lo seleccionado o toda la canción. Control: en Virtual Diva (sin tocar) deja igual el 93 %
  de los tonos y no cambia las medidas; FANCY tono ±1 con la voz 24 % → 71 %, Tarantino 26 % → 69 %. Aplicado a las
  dos (copia en `_respaldo_editor/…_antes_de_tono`).
- Los puntos de la voz se doblaban a la octava de la nota más cercana *tal como está*, así que al subir o bajar una
  nota se movían: ahora usan el tono con el que se abrió la nota.

