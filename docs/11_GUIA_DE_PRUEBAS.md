# 11 — Qué cambió, cómo probarlo y qué falta (2026-11-01)

Parche de Let's Sing 2026 (DLC `0100EE4020D19003`): 675 canciones (660 propias + 15 oficiales), validado sin problemas.
Biblioteca: `~/LetsSing/songs` (271 descargadas con usdb_syncer + 389 sacadas de los DLC y juegos anteriores).

Es la foto de la biblioteca del autor ese día (canciones, cantidades, `~/LetsSing`). En otro PC, `<canciones>` es tu
carpeta de entrada y `<proyecto>` la carpeta del repositorio; los pasos del apartado 3 valen igual.

## 1. Qué cambió

| Área | Antes | Ahora |
|---|---|---|
| Orden "Título" del juego | Salía ordenado por artista (el juego ordena por el ID y el ID empezaba por el artista) | ID con el título primero (`ControlZW`, `GoodAsHellL`); solo en 2026, las demás ediciones siguen igual |
| Idioma | Todas "English" | Idioma real: English 567, Spanish 50, French 30, German 15, Korean 10, Other 3 |
| Género | Todas "Pop"; "Rap" no existe en 2026 | Géneros del juego (Pop, Rock, Electro, Country, RnB, HipHop, Latin, Ballad) desde el #GENRE o la tienda iTunes |
| Dificultad | Fija | Calculada de las notas (fórmula ajustada con 59 canciones oficiales) |
| Voz (filtro cantante) | Todas "Both" | Hombre/Mujer/Ambos por artista (MusicBrainz) y control por el tono; ante la duda, Ambos |
| Año | 240 canciones de DLC con 2020 | Año real (datos oficiales, MusicBrainz, iTunes) |
| Portadas | 79 repetidas (una por artista), blancas o fotogramas borrosos | Portada propia: USDB, oficial o single/álbum (nunca recopilatorios) |
| Letras | Palabras pegadas ("We'retalkingaway"), caracteres rotos ("Ã©") | Espacios y acentos correctos |
| Sync Editor | No mostraba la letra | Editor nuevo: carril de notas, cortes por partes, ajustar a la voz, modo cantar |
| Columna "Sinc." | — | Resultado de la revisión con la voz (ok / parcial / desfase / dudosa) |
| Herramientas | Solo por terminal | Apartado **5. Opciones avanzadas: herramientas de la biblioteca** en la app |
| usdb_syncer | Apuntaba al disco dañado | Apunta a la carpeta de entrada del programa; las canciones nuevas se convierten sin pasos extra |
| Videos `.bk2` | Ninguna forma segura de rehacer uno | Clic derecho → "Volver a codificar el video desde su fuente" (el viejo se **mueve** a `_replaced_videos`, no se borra) |

## 2. Qué probar en la consola

Abre Let's Sing 2026 con la Switch ya actualizada (al terminar la copia por MTP).

1. **Cuenta de canciones**: deben aparecer las 675.
2. **Orden por título**: ordena por "Título" y ve a la C: `(You Drive Me) Crazy`, `CHANEL`, `Cake By the Ocean`,
   `California Gurls`, `Call Me Maybe`… *Control* (Zoe Wees) debe estar en la C, no en la Z; *Good as Hell* (Lizzo)
   en la G, no en la L.
3. **Filtro de idioma**: Coreano → BLACKPINK (BOOMBAYAH, DDU-DU DDU-DU, Kill This Love, Lovesick Girls);
   Otro → Hatsune Miku (Melt, Senbonzakura, Rolling Girl); Alemán → Farbenspiel des Winds, Signal, Willkommen Zurück;
   Francés → Voilà, Facile.
4. **Filtro de género**: Latin → En El Coche, China, La bicicleta; HipHop → Crazy In Love, Con calma; RnB → Stand By Me.
5. **Dificultad**: Muy difícil → Turn Off The Light, Barbie Girl, Bad Decisions; Muy fácil → ALL MY LOVE (Coldplay),
   Soak Up The Sun, Wish You The Best.
6. **Cantante**: Hombre → ALL MY LOVE, Belong Together; Mujer → Control, Good as Hell, Voilà.
7. **Año**: Mamma Mia 1975, Take On Me 1985, Stand By Me 1987 (antes eran 2020).
8. **Portadas**: Thunder y Bones (Imagine Dragons) con su single, no la misma; For You (Liam Payne & Rita Ora) no
   en blanco; Stand By Me; las de Ariana Grande cada una la suya.
9. **Letras**: Take On Me → "We're talking away" con espacios; Voilà y Facile con acentos (à, é); thank u, next.
10. **Sincronía**: Bitch Better Have My Money (arreglada a mano por partes).
11. **Videos**: La isla bonita todavía muestra la portada (ver pendiente 1); el resto con su videoclip.

Si algo falla, anota la canción y qué se ve: con eso se busca en `docs/03_BUGS.md`.

## 3. Qué probar en el PC

Abre el programa con el icono de KDE o con `<proyecto>/start_linux.sh`.

- **Apartado 5 (abajo a la izquierda)**: elige *Comprobar el parche antes de copiarlo a la consola* → *Ejecutar*: en
  menos de un minuto debe decir "675 songs checked: 0 problem(s)". *Ver progreso* abre la ventana con la salida.
- **Solo listar**: elige *Arreglar portadas repetidas o malas* sin marcar *Aplicar los cambios*: lista lo que
  cambiaría y no toca nada.
- **Detener**: lanza *Revisar la sincronía de cada canción con la voz* marcando *Solo las canciones ya analizadas*,
  pulsa *Detener*: el informe `<canciones>/../informe_sincronia.csv` queda completo.
- **Bloqueo**: mientras corre una herramienta, *Iniciar conversión* está desactivado (y al revés).
- **Volver a codificar un video**: clic derecho en *Madonna - La isla bonita (Radio Edit)* → *Volver a codificar el
  video desde su fuente…*. Pide confirmación, mueve el `.bk2` actual a `<canciones>/../_replaced_videos/` y convierte
  solo esa canción (unos minutos). Luego, apartado 5 → *Actualizar el parche en la Switch* con *Aplicar los cambios*.
- **Añadir un video**: clic derecho en una canción sin videoclip (lista del autor: `~/LetsSing/VIDEOS_PENDIENTES.md`) → *Añadir un video (archivo o
  enlace)…* → pega el enlace; la ventana dice en qué segundo empieza la canción y si encaja; luego *Convertir solo esta
  canción*.
- **usdb_syncer**: ábrelo con `usdb_syncer`; en sus ajustes la carpeta de canciones debe ser
  la carpeta de entrada del programa. Descarga una canción nueva, pulsa *Actualizar* en el programa: debe aparecer en la
  tabla y convertirse con *Convertir solo esta canción*.

## 4. Qué quedó a medias / qué falta (actualizado 2026-11-01 por la noche)

Hecho y probado en la consola: videos nuevos (La isla bonita…), orden por título, filtros de idioma, años por
décadas, letras con acentos, portadas, dificultad y el mod de saltar intro (ZR/ZL).

1. **14 canciones con la portada fija como video**: `~/LetsSing/VIDEOS_PENDIENTES.md` (enlaces y nombre del archivo);
   clic derecho → *Añadir un video (archivo o enlace)*. Swish Swish (Album Version) hay que montarla a mano (el
   videoclip oficial está en `~/LetsSing/VIDEOS_PENDIENTES/`).
2. **BBHMM**: revisar a oído en el Sync Editor las líneas 59, 78 y 80 y los ad-libs 18 y 48; si la letra sigue
   pareciendo adelantada desde el principio, probar la calibración de latencia del juego.
3. **Mod**: terminar la canción al acabar la letra; que el video salte directo (ahora acelera un momento).
4. **Citron**: al cerrarlo se configura la carpeta de actualización y DLC (`~/LetsSing/juegos/Let's Sing 2026`);
   el mod ya está en `~/.local/share/citron/load/0100EE4020D18000/skipintro`.
5. **Análisis de voz de las canciones de USDB**: al cambiar su audio a la `.m4a` original, su análisis guardado se ve
   "por rehacer" (se valida por tamaño); la columna Sinc. vuelve con *Revisar la sincronía* del apartado 5 (horas).
6. **Temas** (Amor/Profunda/Fiesta) y **beats / vxla_feat**: sin cambios. **B-61**: si la ventana se congela, queda
   `hang_trace.log`.
7. **Bohemian Rhapsody** sale con año 1985 (dato oficial del juego de Queen); la canción es de 1975.
8. **Micrófono con el móvil**: necesita la cuenta Nintendo en línea (ver bitácora); alternativa: micrófono USB.

## 5. Tareas largas desde la app (apartado 5)

| Tarea | Tiempo | Cambia archivos |
|---|---|---|
| Comprobar el parche | ~1 min | No |
| Actualizar el parche en la Switch | segundos – horas (~30 GB si cambió todo) | En la Switch (con respaldo) |
| Revisar la sincronía con la voz | horas la primera vez, minutos después; 6 GB de memoria máximo | Solo el informe y la columna Sinc. |
| Listar canciones USDB con audio de otro video | segundos | No |
| Arreglar portadas | minutos (internet) | Con "Aplicar": nueva portada, la vieja se conserva |
| Corregir años de relleno | minutos (internet) | Con "Aplicar": #YEAR (.bak) |
| Añadir género | ~3 s por canción sin género | Con "Aplicar": #GENRE (.bak) |
| Hombre/mujer de cada cantante | ~1-2 s por artista nuevo | `_artist_genders.json` |
| Devolver los nombres de usdb_syncer | segundos | Con "Aplicar": renombra audio/video/portada, txt (.bak) y .usdb |
| Quitar restos de las carpetas | segundos | Con "Aplicar": borra logs, temporales, portadas/audios sin usar, `.bk2` duplicados idénticos |

Las tareas corren de una en una, como proceso aparte (la ventana no se congela). Detener una no pierde nada:
al volver a ejecutarla sigue donde se quedó. Los `.bk2` nunca se tocan.
