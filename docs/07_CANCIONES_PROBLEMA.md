# 07 — Canciones con problemas reportados

Reportadas el 2026-10-21 tras probarlas en la consola. **Ninguna se pudo abrir todavía**: el disco con `songs_custom`
no estaba conectado (en `/run/media/djvemo/EADE-F56A` había otro disco). La tabla indica la causa más probable según
el código y qué arreglo ya la cubre; la columna "Verificar" es lo que hay que mirar con el disco conectado.

| Canción | Síntoma reportado | Causa probable | Cubierto por | Verificar |
|---|---|---|---|---|
| Because… / Love Me | letras adelantadas | GAP del txt o audio distinto al que esperaba el txt (B-08: el audio se elegía al azar entre los archivos de la carpeta) | B-08 (`30669e3`) para conversiones nuevas; el `.ogg` ya cacheado se mantiene | qué audio usó el `.ogg` cacheado; comparar duración con el `#MP3`; ajustar con Fix Sync |
| Please Please Please | la letra nunca aparece, mucho gap | GAP/VIDEOGAP enorme, o audio equivocado (B-08), o letras borradas por la codificación (B-46) | B-08, B-46 | valores `#GAP`/`#VIDEOGAP`; si hay varios audios en la carpeta |
| Puro Chantaje | tonos mal | corrección "fast" no basada en octavas (B-06) | B-06 (`8426e7e`) | tono resultante tras regenerar el vxla |
| Wolves ("Wolf") | la letra se acaba enseguida | probablemente canción reconstruida desde DLC: espacios/sílabas mal leídos (B-34), páginas mal cortadas | B-34 (`27f8a17`) para extracciones nuevas | si su txt tiene la huella del extractor (BPM 300); volver a extraerla desde el vxla oficial |
| Side to Side | una octava abajo | heurística de tono (B-06) | B-06 | idem |
| Be The One | tono muy alto | reconstruida desde DLC: −36 al extraer y +48 al convertir = **+12** (B-06/B-34) | `8426e7e` + `27f8a17` + `tools/mark_extracted_songs.py` | ejecutar la herramienta de marcado |
| Bitch Better Have My Money | desfase | GAP/VIDEOGAP o audio equivocado (B-08) | B-08 | Fix Sync |
| Don't Stop the Music | tono | B-06 | B-06 | idem |
| One Kiss | letra "dual", rápida y pegada | reconstruida desde DLC (posible dueto en el vxla oficial) + espacios no detectados (B-34) | `27f8a17`; duetos: el parser toma solo P1 (`cd87f8d`) | estructura de su vxla oficial (¿dos capas de notas?) |
| Symphony | letra rápida y casi no se ve | reconstruida: las sílabas no se encontraban por tiempo exacto → quedaban como `~` y se ocultaban (B-34) | `27f8a17` (comparación con tolerancia) | volver a extraer y comparar |
| Portadas repetidas | la misma portada en varias canciones | archivo temporal compartido entre hilos (B-02) | `30669e3` | **las portadas ya cacheadas siguen mal**: borrar solo los `.png` de esas canciones (Clear cache conserva los `.bk2`) |
| Nombres/artistas inventados | datos de canción incorrectos | el script viejo `fix_dlc_artists_metadata.py` (quitado) tomaba el **primer** resultado de iTunes a partir del ID en CamelCase | corregido con `rename_songs.py` y los `fix_*` | contrastar con la letra (Genius) antes de corregir; ver plan abajo |
| Francés / apóstrofes "todo mal" | letras con caracteres perdidos | B-46 (letras borradas) + B-40 (tildes quitadas) | `cd87f8d` | si algún `.txt` ya fue reescrito sin acentos por un script anterior, hay que recuperar el original |

## Pasos con el disco conectado

1. `python tools/mark_extracted_songs.py <songs_custom>` → revisar la lista → repetir con `--apply`.
2. Convertir con "Forzar regenerar letras/notas" **no hace falta**: el cambio de versión del generador regenera todos los
   vxla solo (los `.bk2` no se tocan).
3. Para las portadas repetidas: borrar `<id>.png` de las canciones afectadas (o Clear cache sin marcar los videos).
4. Revisar en `error.log` y en el resumen final las canciones omitidas y su motivo.
5. Pasar las canciones de esta tabla una por una y anotar el resultado aquí.

## Plan para los metadatos inventados (pendiente)

- Detectar canciones cuyo artista/título vino de iTunes (`fix_dlc_artists_metadata.py` deja rastro en el JSON combinado).
- Para cada una: buscar en Genius con la **primera línea de la letra** del vxla/txt y aceptar solo si el título coincide
  con el ID y la letra coincide (similitud alta); si no, dejarla marcada para revisión manual.
- Nunca renombrar carpetas automáticamente: el nombre de la carpeta define el ID y la caché (`.bk2`).

## Diagnóstico completo (2026-10-23, con los .txt de las 678 canciones)

Herramienta: `python tools/diagnose_library.py <songs_custom> --csv informe.csv` (solo lee).

| Tipo | Cantidad |
|---|---|
| Reconstruidas desde DLC / juego base de ediciones anteriores | 404 |
| UltraStar reales (USDB u otras) | 274 |
| Tono que el método viejo transponía (no era octava) | 355 |
| Sin letra (todas las sílabas `~`) | ~50 |
| Letra pegada (sin espacios, extractor viejo) | ~8 |
| Usan `#START` (letra muy tarde si no se aplica) | 31 |
| Artista/título equivocado (iTunes) | 21, ver `docs/correcciones_metadatos.csv` |

### Causas confirmadas de la lista reportada

| Canción | Causa | Arreglo |
|---|---|---|
| Please Please Please | `#START:58.2` ignorado y audio ya recortado; además el audio viene de otro video (`Yl_thbk40A0` en vez de `cF1Na4AIecM`) y queda 1,55 s tarde (mismo valor en las dos mitades de la canción) | soporte de #START (`b074be4`) + `#GAP:75990` (pendiente de aplicar después de verificar la copia) |
| Bitch Better Have My Money | el sincronizador USDB no pudo bajar el video con el que se hizo el txt (`B3eAMGXFw1o`) y usó otro (`zGnY6Tq_zzo`), una versión con otras partes: la letra no cabe (termina 15,7 s después del audio) y ningún GAP la arregla | volver a bajar el audio de https://youtu.be/B3eAMGXFw1o con el sincronizador |
| Because You Loved Me | GAP 60 ms para un audio que no es el del txt | Sync Editor |
| Be the One, Wolves, Symphony, One Kiss | reconstruidas: tono +43/+38 y sílabas perdidas | vxla oficial (`attach_official_vxla.py`) |
| Side To Side, Don't Stop the Music, Chantaje | método viejo +51/+52 (fuera de tonalidad) | tono por octavas (`8426e7e`) |

### Orden recomendado cuando la biblioteca vuelva al disco local

0. Hecho el 2026-10-24: biblioteca en `~/LetsSing/songs` (ver `~/LetsSing/LEEME.txt`), copiada sin las 583 copias
   `.mp4` redundantes y con los vxla oficiales ya puestos (el paso 1 ya no hace falta).
1. `python tools/attach_official_vxla.py <songs_custom> <megapack_completo> --apply`
2. `python tools/mark_extracted_songs.py <songs_custom> --apply` (las reconstruidas sin vxla oficial)
3. Revisar y aplicar `python tools/rename_songs.py <songs_custom> docs/correcciones_metadatos.csv --apply`
4. Convertir: todos los vxla y audios afectados se regeneran solos; los .bk2 se reutilizan.

### Nota sobre los "desync" reportados
En la Switch, con muchas canciones instaladas, reiniciar una canción desde el menú de pausa a veces desfasa el
audio del video; saliendo y volviendo a entrar se corrige. Es rendimiento de la consola, no del archivo. Antes de
tocar el GAP de una canción marcada "desync", confirmar entrando de nuevo a la canción (sin reiniciarla) y comparar con
el diagnóstico (`audio dura X s, la letra termina a Y s`): solo si el archivo está mal se corrige.

### Herramientas de sincronía (2026-10-24)
- `python tools/usdb_sources.py <songs>`: canciones de USDB cuyo audio no viene del video con el que se sincronizó la
  letra. En la biblioteca: Bitch Better Have My Money, Please Please Please y Daft Punk - Something About Us.
- `python tools/sync_check.py <carpeta de canción>`: separa la voz (Demucs) y mide qué parte de las notas cae sobre
  voz real, con el GAP actual y con el mejor desplazamiento; solo propone un GAP si el desfase es el mismo en las dos
  mitades. Úsala antes de tocar una canción marcada "desync" (ver la nota sobre el rendimiento de la Switch).
  Daft Punk: 95 % con el GAP actual, sin desfase fijo → se deja como está.
- `python tools/sync_scan.py <songs> --report informe.csv`: revisa todas las canciones UltraStar contra la voz y
  las clasifica (ok, desfase, parcial, otra_version, dudosa). Continúa donde quedó (la voz se guarda por canción) y
  con `--only-analyzed` rehace el informe en segundos. Después, cada canción se arregla en el editor (corte +
  "Ajustar a la voz").

