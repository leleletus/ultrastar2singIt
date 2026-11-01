# 09 — Historial de bugs

Resumen al 2026-11-01: **62 bugs registrados, 61 cerrados, 1 pendientes**. El detalle de cada uno (causa, impacto, arreglo) está en [03_BUGS.md](03_BUGS.md); las regresiones del historial de git en [04_REGRESIONES.md](04_REGRESIONES.md) y el día a día en [05_BITACORA.md](05_BITACORA.md).

## Pendientes

| ID | Severidad | Área | Problema | Estado |
|---|---|---|---|---|
| B-61 | ALTO | GUI | La ventana se congeló una vez (hilo principal bloqueado, con el video de BBHMM abierto) | ABIERTO (vigilante hang_trace.log en 6e74b01) |

## Mejoras pendientes (no son bugs)

| Qué | Estado |
|---|---|
| Mod para Let's Sing 2026: saltar el intro (3 s antes de la letra) y terminar al acabar la letra | En investigación: volcado IL2CPP hecho; el juego ya tiene `Lyrics.firstNoteStartTime`, `TryGetLastNote`, `Seek` |
| Revisión de sincronía de las 274 canciones UltraStar contra la voz (`tools/sync_scan.py`) | En marcha en segundo plano; informe en `~/LetsSing/informe_sincronia.csv` |
| Bitch Better Have My Money: audio de otra versión | Sincronizada a mano por partes; lo ideal es bajar el audio de https://youtu.be/B3eAMGXFw1o |
| Varios idiomas por canción (el juego guarda una lista, p. ej. "Korean, English") | Por probar en la consola |
| Tema real por canción (Love/Deep/Party) | Todas siguen con los tres (no hay datos oficiales de 2026 para calcularlo sin equivocarse); dificultad y voz ya se calculan (603b4cd) |
| Archivos `beats/<id>.json` y `vxla_feat` que traen los DLC oficiales de 2026 | Sin generar (el juego funciona sin ellos) |

## Cerrados

| ID | Severidad | Área | Problema | Arreglo |
|---|---|---|---|---|
| B-01 | CRÍTICO | GUI | La validación de campos antes de convertir está desactivada | (7fc2657) |
| B-02 | ALTO | Conversión | Portadas mezcladas entre canciones con multihilo (archivo temporal compartido) | (30669e3) |
| B-03 | ALTO | Conversión | JSON del DLC con BOM no se puede leer → canciones descartadas | (30669e3) |
| B-04 | CRÍTICO | Conversión | Registro en name.txt/JSON/TSV antes de copiar medios; año no numérico rompe a mitad | (30669e3) |
| B-05 | ALTO | Conversión (XML) | Carrera entre hilos al escribir SongsDLC.tsv y name.txt | (30669e3) |
| B-06 | ALTO | Tono | Corrección "fast": +48 a canciones agudas y transposiciones que no son octavas | (8426e7e) |
| B-07 | MEDIO | Tono | División por cero en canciones sin notas normales/doradas | (8426e7e) |
| B-08 | ALTO | Conversión | Elección de archivos fuente arbitraria: ignora #MP3/#COVER y toma archivos generados | (30669e3) |
| B-09 | MEDIO | Caché | Filtro `_cover.mp4` obsoleto: el video estático cacheado cuenta como video fuente | (30669e3) |
| B-10 | ALTO | Conversión (XML) | En XML se copia un AVI con extensión .mp4 | (30669e3) |
| B-11 | MEDIO | Video (JSON) | "Max video size" no se aplica a los .bk2 | (b9d454f: tasa /D de Bink restaurada, ver B-47) |
| B-12 | MEDIO | Caché | "Still video" contamina la caché (XML) o se ignora (JSON) | (30669e3) |
| B-13 | MEDIO | Caché | El vxla no se regenera al cambiar formato/tono/medley | (30669e3) |
| B-14 | MEDIO | Video (JSON) | Videos fuente .bk2/.mpeg/.m4v se ignoran → video estático | (30669e3) |
| B-15 | MEDIO | Conversión | Excepciones opacas sin audio, sin imagen o con ffprobe vacío | (30669e3) |
| B-16 | BAJO | Rutas | ffprobe se busca como `ffprobe.exe` también en Linux | (30669e3) |
| B-17 | MEDIO | Salida | Escudo `_Patch`: `isfile` relativo al CWD y doble anidado `_Patch/_Patch` | (30669e3 + 7fc2657) |
| B-18 | ALTO | Config | config.yml se guarda en el CWD pero se lee de la carpeta de la app | (7fc2657) |
| B-19 | MEDIO | GUI/Config | Multihilo y nº de hilos no se cargan; al guardar se pisan | (7fc2657) |
| B-20 | MEDIO | GUI/i18n | Idioma no se restaura; textos mezclados; clave española en modo inglés | (7fc2657 + revisión 2026-10-31: 0 textos sin traducir) |
| B-21 | ALTO | GUI | `self.log_message` no existe → excepción en Fix Sync y Play | (7fc2657) |
| B-22 | BAJO | GUI | Volver al "orden original" ordena por la columna Lyrics | (7fc2657) |
| B-23 | BAJO | GUI | Tras convertir se pierde la selección múltiple | (7fc2657) |
| B-24 | MEDIO | GUI | Stop/error informan "finished successfully"; Stop no detiene ffmpeg; pkill global | (30669e3 + 7fc2657) |
| B-25 | ALTO | GUI/Rendimiento | Escaneo completo repetido (parsea todos los txt) incluso durante la conversión | (7fc2657) |
| B-26 | MEDIO | Sync Editor | Audio equivocado, ignora VIDEOGAP, guardado con codificación incorrecta | (7fc2657) |
| B-27 | BAJO | GUI | Play reproduce el primer .ogg (puede ser la preview) | (7fc2657) |
| B-28 | MEDIO | Caché | "Clear cache" no borra los intermedios `.avi` ni `_cover.avi` | (7fc2657) |
| B-29 | MEDIO | Parser | Notas sin sílaba revientan; tags sensibles a mayúsculas; duetos mezclados | (cd87f8d) |
| B-30 | MEDIO | IDs | name_id: colisiones, ID vacío, 6 implementaciones divergentes | (30669e3 + 1b437ba: un solo módulo naming.py, colisiones detectadas) |
| B-31 | MEDIO | Tools | Recover cache no encuentra el romfs correcto en XML ni IDs nuevos | (b779bc6) |
| B-32 | ALTO | Tools | Tools → Unpack está roto (NameError) y genera tiempos erróneos | (27f8a17) |
| B-33 | BAJO | Tools | reverse_vxla: NameError `name_id` | (27f8a17) |
| B-34 | BAJO | Tools | ExtractorPro no lee vxla propios; espacios mal detectados | (27f8a17) |
| B-35 | BAJO | Datos | `DlcRepository.init` falla en BD nueva | (DROP TABLE IF EXISTS; prueba DlcRepositoryTest) |
| B-36 | BAJO | GUI | Regex de TitleID laxa | (7fc2657) |
| B-37 | MEDIO | Logging | error.log en el CWD; spam DEBUG de librerías; log sin límite | (30669e3) |
| B-38 | MEDIO | Tono | Importación pesada de TensorFlow al cargar; Demucs no funciona empaquetado | (8426e7e) |
| B-39 | MEDIO | Rendimiento | Genius sin caché negativa: segundos de espera por canción sin conexión | (cd87f8d) |
| B-40 | MEDIO | Calidad | Las letras pierden tildes y ñ | (cd87f8d) — confirmar en consola |
| B-41 | ALTO | Build | El `.spec` excluye QtMultimedia, que la GUI importa | (7fc2657; build de PyInstaller probado en Linux 2026-11-01: la GUI arranca) |
| B-42 | MEDIO | Repo | requirements.txt y build.yml no versionados; requirements inutilizable | (4c68038: instalación limpia probada) |
| B-43 | BAJO | Código muerto | `rename_folders_physically` con `return` en lugar de `continue` | (30669e3) |
| B-44 | MEDIO | Wine/Bink | binkc sin timeout ni diagnóstico; `wine` fijo | (30669e3) |
| B-45 | MEDIO | GUI | Cerrar la ventana con la conversión en marcha deja hilos vivos | (7fc2657) |
| B-46 | CRÍTICO | Letras | Letras con acentos/apóstrofes **borradas** si aparecen después de los primeros 4 KB del txt | (cd87f8d) |
| B-47 | MEDIO | Video | "Max video size" sin efecto: binkc no recibía la tasa `/D` (R-11) | (b9d454f) |
| B-48 | ALTO | Tools/Caché | Copias del extractor con el ID del conversor tomadas como ya convertidas: portadas a tamaño completo en el parche, 28 GB de `.mp4` duplicados (R-12) | (b9d454f + 1b437ba) |
| B-49 | MEDIO | Letras | Palabras pegadas a mitad de línea en canciones UltraStar ("sideto side"): el espacio de una nota sostenida `~ ` no pasaba a la letra | (28276db, ajustado en 3eca0ac) |
| B-50 | ALTO | Letras | 112 de 224 vxla oficiales v2.0: toda la letra pegada ("We'retalkingaway"), se mostraba `lyrics_cut`, que no tiene espacios | (3eca0ac) |
| B-51 | ALTO | Sync Editor | Las letras no aparecían nunca ("Aquí aparecerán las letras"): un atributo tapaba el método `lyrics_offset_s` (desde `b074be4`) | (d412df5) |
| B-52 | ALTO | Datos | El idioma de todas las canciones salía "English" (fijo en el código): el filtro por idioma del juego no servía | (aa33a0e, e4aeb93; solo 2026) |
| B-53 | ALTO | Portadas | 79 canciones con la portada de otra (una por artista, de un script anterior) | (aa33a0e: tools/fix_covers.py) |
| B-54 | ALTO | Letras | Caracteres rotos ("Ã©", "Â«") en letras oficiales: archivos UTF-8 que declaran Windows-1252 | (e4aeb93) |
| B-55 | MEDIO | Datos | Género "Rap" no existe en 2026 (es "HipHop"); RnB/Latin/Country nunca se usaban | (este commit; solo 2026) |
| B-56 | ALTO | Orden | Lista "Título" del juego ordenada por artista: Let's Sing 2026 ordena por el ID y el nuestro empezaba por las iniciales del artista | (este commit: ID de juego título primero, solo 2026) |
| B-57 | MEDIO | Datos | 240 canciones de DLC con el año del DLC (2020) en vez del de la canción | (este commit: tools/fix_years.py) |
| B-58 | MEDIO | Portadas | Portadas del megapack en blanco, fotogramas borrosos o de recopilatorios | (este commit: fix_covers --blank/--dlc) |
| B-59 | BAJO | Biblioteca | Swish Swish duplicada (normal y Album Version) | (movida a archivo/duplicados_quitados) |
| B-60 | BAJO | Herramientas | Los registros de los servicios no se vaciaban al relanzar (systemd "file:") | (usar "truncate:") |
| B-62 | MEDIO | Switch | DBI no sobrescribe archivos por MTP ("Access denied") | (e4aeb93: borrar ya respaldado y copiar) |
