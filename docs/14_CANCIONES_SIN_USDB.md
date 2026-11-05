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
4. **Notas**: en cada línea, la voz se corta en notas por silencios (60 ms) y saltos de tono (1,2 semitonos durante
   60 ms); notas de 80 ms como mínimo; tono = mediana de la nota, con los errores de octava corregidos respecto a la
   línea.
5. **Sílabas**: español con sus reglas (diptongos, hiatos, grupos `pr`, `bl`, `ch`, `ll`, `rr`, `qu`/`gu` mudas);
   inglés aproximado (grupos de vocales); coreano **romanizado** (romanización revisada, una sílaba por bloque de hangul,
   como lo muestra Let's Sing: "Muneul ppakchamyeon"); japonés **en romaji** (Hepburn con `pykakasi`, una sílaba por
   mora: "Ko-ko-ro ga sa-ke-n-de-ru"; la っ pequeña dobla la consonante: "Cho-tto ma-tte"). Cada sílaba va al inicio de nota con el ataque más fuerte; si hay
   más notas que sílabas, las demás son `~` (nota sostenida); si hay menos, se parten las más largas.
6. `.txt` con `#BPM:400` (37,5 ms por pulso), `#GAP` = primera nota, una página por línea de la letra, y
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

## Fiabilidad

- Goma de Mascar: las notas coinciden con la voz real un 62 % (mediana por línea; las canciones oficiales dan 38–77 %)
  y el mejor desplazamiento es +0,00 s (la letra no va adelantada ni atrasada).
- Lo automático acierta los tiempos de las líneas y la melodía general; los fallos típicos son sílabas en la nota de al
  lado, adornos (melismas) y alguna octava. Se corrigen en el editor de sincronía (mover partes, mover notas en
  vertical, modo cantar).
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
