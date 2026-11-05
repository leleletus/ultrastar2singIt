# 13 — Modo Feat de Let's Sing 2026

Estado: 2026-11-02. Solo Let's Sing 2026 (`FEAT_EDITIONS` en `ConvertFiles.py`); las demás ediciones no tienen este
modo y su salida no cambia.

## Qué pasaba

En modo Feat, "Un año sin lluvia" (y cualquier canción convertida) cerraba el juego. Dos causas (B-73):

1. Faltaba `Songs/vxla_feat/<id>_feat.vxla`. El juego carga por canción `Singable.AssetType` `Audio`, `Instru`,
   `Preview`, `Video`, `Cover`, `Vxla`, **`VxlaFeat`** y **`Beat`**; el conversor solo generaba los primeros.
2. Todas las canciones decían `"coopfriendly": "Coop"`. En las oficiales `"Coop"` = la canción tiene segunda voz
   (10 de 15); las nuestras no la tenían.

## Lo que muestran los archivos oficiales (DLC 3, 15 canciones)

| Archivo | Contenido |
|---|---|
| `vxla_feat/<id>_feat.vxla` | El vxla normal **sin notas doradas** (`#g5`), sin `practice`/`passages`, con capas `segments`, `pages`, `lyrics`, `notes_full`, **`notes2_full`, `lyrics2`, `pages2`** (segunda voz) y `language`. UTF-8, CRLF |
| `beats/<id>.json` | `song`, `spectrumBands` (3 bandas de 512 bins con su bin más fuerte), `spectrumIndexSelection` (5 bins), `bpm` (`[{startTime, value}]`), `beats` (tiempos de cada pulso) |

- **Segunda voz**: escrita a mano (coros, respuestas, armonías: en 2 Be Loved la voz 1 canta "Am I ready" y la 2
  responde "Girl, there ain't a doubt"). En 5 de las 15 está vacía y el juego la acepta. Es lo que se ve "multicolor":
  cada voz la canta un jugador, con su color.
- **`segments`** (`FeatSegment`: `Basic`, `Chorus`, `Empty`, con voz forzada): cubren la canción entera sin huecos y
  **todos los cortes caen al inicio de una página** (133/133). `feat` = estribillo, se canta a la vez (mediana 30 s,
  4–18 páginas, 2–4 por canción); `''` = trozo de estrofa, se canta por turnos (mediana 13 s, 2–10 páginas);
  `1`/`2` = parte forzada a una voz (poco frecuente, no se genera). Los cortes oficiales caen tras una pausa mediana
  de 0,9 s (el resto de líneas, 0,3 s).
- Las letras oficiales de 2024/2025 no tienen `segments`, pero sí `structure` (`intro`, `couplet`, `refrain`,
  `pont`, `outro`).
- `SongBeats.Invalid`: sin `beats` la canción funciona; solo lo usan efectos que siguen el ritmo (`BeatLinker`).

## Lo que genera el conversor

`FeatVxla.py` (letra feat y beats) y `SongSections.py` (secciones y cantantes de Genius), desde `ConvertFiles.feat_sources`:

| Qué | De dónde (en este orden) |
|---|---|
| Estribillos (`feat`) | Canciones de DLC: `structure` oficial (si marca al menos 2). Si no: secciones de Genius (`chorus`, `post-chorus`). Si no: los estribillos detectados por el conversor, uniendo los trozos a menos de 4 s |
| Cortes de las estrofas | Cambios de sección (oficial o Genius); una parte de más de 22 s se corta en su pausa más larga; partes de 8 s como mínimo |
| Segunda voz | Duetos de UltraStar: la voz `P2` del txt (y en el modo clásico el vxla lleva las líneas de los dos cantantes: `merge_duet`, P1 gana si se pisan). Canciones con varios artistas: las líneas que Genius atribuye al segundo artista (por la sección o, dentro de una sección, por el formato: normal / *cursiva* / **negrita** = "ambos"). Si no, vacía |
| `coopfriendly` | `"Coop"` si la segunda voz tiene 20 notas o más (la oficial GoodNews, con 6, es `""`) |
| Beats | Detector propio con numpy + ffmpeg (sin librosa): espectrograma mel, tempo por autocorrelación, pulsos por programación dinámica |

Cantantes: `SongSections.song_singers` toma el primer artista como voz 1 y el resto (otros artistas, `feat.`/`ft.`
del artista o del título) como voz 2. Una sección sin nombres conserva los cantantes de la anterior.

Genius: la página se guarda junto al txt como `<txt>_genius_sections.json` (también "no encontrada", se reintenta a
los 30 días) y se reutiliza la URL de `<txt>_genius_cache.json`. Solo la primera conversión necesita internet; sin
"Buscar estribillos en internet" se usa lo que ya esté en caché.

## Fiabilidad, medida con las 15 canciones oficiales

| Qué | Resultado |
|---|---|
| Capas de la letra feat (páginas, letra, notas sin dorado, idioma) | idénticas en 15/15 |
| Cortes de segmentos (con los estribillos oficiales) | 96/133 en el mismo sitio, 39 de más (antes de usar pausas: 85/133) |
| Tempo de los beats | 12/15 (dos al doble, uno en tresillo) |
| Pulsos a menos de 70 ms del oficial | mediana 76 % (9 canciones > 70 %; en 3 se engancha al contratiempo) |

Canciones de prueba (biblioteca): Sofia pasó de 0 a 5 tramos juntos (sus estribillos detectados eran trozos de 3–5 s);
1, 2, 3 (Sofía Reyes ft. Jason Derulo & De La Ghetto) casa 116/131 líneas con Genius y tiene 344 notas en la voz 2;
Échame la culpa y Save Your Tears (duetos de UltraStar) llevan su `P2`.

## Pendiente

- Duetos oficiales de DLC antiguos (`<id>_duet.vxla`): no están en la biblioteca; habría que sacarlos de los NSP del
  servidor.
- Validar con más canciones oficiales: volcar con Citron el RomFS del juego base de 2026 y de "mit Deutschen Hits"
  (clic derecho → Volcar RomFS) y repetir las mediciones.
