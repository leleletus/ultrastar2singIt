# 14 — Canciones que no están en USDB (SongMaker)

Estado: 2026-11-05. Módulo `SongMaker.py`, herramienta `tools/make_song.py` y en la app **Herramientas → Crear una
canción que no está en USDB…**.

## Qué hace

Fabrica una carpeta UltraStar normal (`Artista - Título/` con `.txt`, `.m4a`, `.mp4` y portada `[CO].jpg`) para una
canción que USDB no tiene. Después se convierte como cualquier otra (Clásico, Feat, beats, `.bk2`) y se revisa en el
editor de sincronía.

1. **Video y audio** de YouTube (yt-dlp, como usdb_syncer). Si además se da el **audio oficial**, se compara con el
   videoclip (`align_video.measure`, cuatro partes):
   - el clip contiene la canción entera y seguida → se queda **sin cortar**, con su propio audio y la intro incluida
     (la letra empieza en `#GAP`; el mod de saltar intro salta las intros largas);
   - hay escenas que rompen la canción (a mitad o al final) → audio oficial y el video **rehecho por tramos**
     (`cut_video_to_audio`: cada 8 s del audio se busca en el clip; el desfase solo puede crecer —una escena añadida
     empuja el resto— y cada salto se afina a 0,5 s).
2. **Letra con tiempos por línea** de LRCLIB (lrclib.net). Hay varias versiones (disco, video, en vivo): se prueban
   todas las de la duración de la canción (±25 s) y cada desfase (±20 s alrededor del inicio medido) contra la voz, y se
   queda la que mejor encaja (las líneas empiezan donde empieza a cantar).
3. **Voz** separada con Demucs y seguida cada 20 ms (energía y tono, `SyncModel`); se guarda como `<id>.voice.npz`,
   la misma que usa el editor.
4. **Letra de la voz principal**: lo que LRCLIB pone entre paréntesis o corchetes (coros, "(yeah)", "(oye)") se
   quita, como en las oficiales (ninguna de 387 lleva paréntesis); una línea que solo es coro no lleva notas.
5. **Notas** (versión 3, 2026-11-05), escritas como las oficiales (medido en 387 con `tools/note_style.py`: ~1 nota
   por sílaba, 0,24 s de nota típica, el tono quieto o en pasos de 1–2 semitonos, el rap sin tono):
   - las sílabas de cada línea van a los ataques de la voz (subida de volumen tras una bajada, cambio de tono, inicio
     tras un silencio) con programación dinámica: cada sílaba espera una duración de 0,12–0,35 s según su longitud;
     dentro de la línea solo cuenta como voz lo que suena a más del 25 % de su parte fuerte (no la reverberación);
   - cada sílaba es **una nota estable** hasta la siguiente (o hasta que calla la voz); solo una sílaba de 0,45 s o
     más cuyo tono se mueve 2 semitonos y se queda se parte en dos;
   - tono = el semitono que más suena en el centro de la nota; semitonos enteros en la tonalidad de la canción
     (Krumhansl); una nota corta a un semitono de dos vecinas iguales toma el suyo (temblor) y una a 5+ de dos vecinas
     cercanas también (fallo del detector); octavas elegidas por línea y respecto a la canción; notas de 0,12 s como
     mínimo cuando cabe;
   - **rap**: líneas cuya voz desliza el tono dentro de la sílaba, tiene poco tono claro y tiembla, y van rápidas,
     cuando la de al lado también lo es (el rap viene por estrofas): se escriben como notas de rap (`R`, `#p1` en el
     juego: puntúa la voz, no el tono).
6. **Sílabas**: español con sus reglas (diptongos, hiatos, grupos `pr`, `bl`, `ch`, `ll`, `rr`, `qu`/`gu` mudas);
   inglés aproximado (grupos de vocales); coreano **romanizado** (romanización revisada, una sílaba por bloque de hangul,
   como lo muestra Let's Sing: "Muneul ppakchamyeon"); japonés **en romaji** (Hepburn con `pykakasi`, una sílaba por
   mora: "Ko-ko-ro ga sa-ke-n-de-ru"; la っ pequeña dobla la consonante: "Cho-tto ma-tte"). Cada sílaba va al inicio de nota con el ataque más fuerte; si hay
   más notas que sílabas, las demás son `~` (nota sostenida); si hay menos, se parten las más largas.
7. `.txt` con `#BPM:400` (37,5 ms por pulso), `#GAP` = primera nota, una página por línea de la letra, y
   `songmaker.json` (enlace, versión de LRCLIB, desfase, ajuste). Las descargas auxiliares quedan en
   `<canciones>/_songmaker_downloads/` (el conversor ignora las carpetas que empiezan por `_`).

## Uso

En la app: **Herramientas → Crear una canción que no está en USDB…** (artista, título, enlace del videoclip, enlace del
audio oficial opcional, idioma, año, género). Al terminar: **Actualizar**, **Solo pendientes** → convertir.

Terminal:

```
python tools/make_song.py <canciones> "Paty Cantú" "Goma de Mascar" "https://www.youtube.com/watch?v=qztOuGQiZ9g" \
    --language Spanish --year 2009 --genre Pop
python tools/make_song.py <canciones> "TWICE" "SIGNAL" "<videoclip>" --audio "<audio oficial>" --language Korean
```

Necesita internet, ffmpeg, yt-dlp y pykakasi (`requirements.txt`) y Demucs (`requirements-slow.txt`). Tarda 2–3 minutos por canción (Demucs en CPU)
más la conversión del video a `.bk2`.

### Con conexión inestable: descargar primero

`--fetch-only` (`SongMaker.fetch_song`) baja todo lo que necesita internet y lo deja en la carpeta: videoclip, audio
oficial, versiones de la letra (`lrclib.json`) y las páginas de Genius (las cachés que usa luego la conversión para
estribillos y secciones). Si se cae la conexión, espera a que vuelva (cada 30 s, hasta 3 h) y reintenta. Después,
`make_song.py` sin `--fetch-only` fabrica la canción sin internet y la conversión tampoco lo necesita. Así se pueden
descargar todas de una vez y fabricar/convertir en paralelo.

## Fiabilidad

- Medido contra 20 canciones oficiales con su voz analizada (`python tools/note_calibrate.py <canciones> --each`: el
  generador recibe solo las líneas de la letra oficial y la voz): tono a ±1 semitono el 79 % del tiempo (con los
  tiempos oficiales el detector de tono llega al 83 %), 388 notas por canción (oficial 394), salto medio entre notas
  1,84 semitonos (1,86), rango 20,5 (21), inicio de sílaba a 0,13 s de la oficial (mediana).
- Rap: con el umbral elegido apenas marca rap en canciones cantadas (0–3 % del tiempo); en U Can't Touch This
  encuentra el 61 % del rap.
- Para rehacer las notas de canciones ya fabricadas con el generador actual (sin internet, sin tocar videos):
  `python tools/remake_notes.py <canciones>` (el txt anterior va a `<canciones>/../_papelera/notas_v1/`; las
  corregidas a mano en el editor, con `.bak`, se saltan salvo `--force`) y convertir.
- Goma de Mascar: las notas coinciden con la voz real un 62 % (mediana por línea; las canciones oficiales dan 38–77 %)
  y el mejor desplazamiento es +0,00 s (la letra no va adelantada ni atrasada).
- Lo automático acierta los tiempos de las líneas y la melodía general; los fallos típicos son sílabas en la nota de al
  lado (en líneas muy ligadas llegan tarde), adornos y coros entre paréntesis que LRCLIB incluye. Se corrigen en el
  editor de sincronía: mover partes, mover notas en vertical, **borrar una sílaba o una línea con sus notas** (Supr,
  Ctrl+Supr), **corregir el texto** (doble clic en una nota, o T para la línea), modo cantar.
- El inglés se silabea de forma aproximada.

## Canciones hechas (2026-11-05)

| Canción | Video | Letra (LRCLIB) |
|---|---|---|
| Paty Cantú – Goma de Mascar | videoclip oficial | 179 s, +1,6 s |
| Paty Cantú – Afortunadamente No Eres Tú | videoclip oficial | 189 s |
| Paty Cantú – Clavo Que Saca Otro Clavo | videoclip oficial | 204 s, −13,8 s |
| Paty Cantú – Suerte | videoclip sin cortar (la canción entra a los 52 s) | 184 s |
| TWICE – SIGNAL | rehecho por tramos (el clip mete ~37 s de escena a partir del segundo 132) | 197 s |
| TWICE – Strategy | videoclip sin cortar (10,7 s) | 230 s (con Megan Thee Stallion) |
| LE SSERAFIM – Smart | videoclip sin cortar (7,4 s) | 166 s |
| LE SSERAFIM – SPAGHETTI | videoclip sin cortar (26 s) | — |
| LE SSERAFIM – BOOMPALA | videoclip sin cortar (18,6 s) | — |
