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
| Nombres/artistas inventados | datos de canción incorrectos | `experimental_tools/fix_dlc_artists_metadata.py` toma el **primer** resultado de iTunes a partir del ID en CamelCase | pendiente | contrastar con la letra (Genius) antes de corregir; ver plan abajo |
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
