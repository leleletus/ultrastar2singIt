# 11 — Qué cambió, cómo probarlo y qué falta (2026-11-01)

Parche de Let's Sing 2026 (DLC `0100EE4020D19003`): 675 canciones (660 propias + 15 oficiales), validado sin problemas.
Biblioteca: `~/LetsSing/songs` (271 descargadas con usdb_syncer + 389 sacadas de los DLC y juegos anteriores).

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
| usdb_syncer | Apuntaba al disco dañado | Apunta a `~/LetsSing/songs`; las canciones nuevas se convierten sin pasos extra |
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

Abre el programa con el icono de KDE o con `~/ultrastar_official/start_linux.sh`.

- **Apartado 5 (abajo a la izquierda)**: elige *Comprobar el parche antes de copiarlo a la consola* → *Ejecutar*: en
  menos de un minuto debe decir "675 songs checked: 0 problem(s)". *Ver progreso* abre la ventana con la salida.
- **Solo listar**: elige *Arreglar portadas repetidas o malas* sin marcar *Aplicar los cambios*: lista lo que
  cambiaría y no toca nada.
- **Detener**: lanza *Revisar la sincronía de cada canción con la voz* marcando *Solo las canciones ya analizadas*,
  pulsa *Detener*: el informe `~/LetsSing/informe_sincronia.csv` queda completo.
- **Bloqueo**: mientras corre una herramienta, *Iniciar conversión* está desactivado (y al revés).
- **Volver a codificar un video**: clic derecho en *Madonna - La isla bonita (Radio Edit)* → *Volver a codificar el
  video desde su fuente…*. Pide confirmación, mueve el `.bk2` actual a `~/LetsSing/_replaced_videos/` y convierte
  solo esa canción (unos minutos). Luego, apartado 5 → *Actualizar el parche en la Switch* con *Aplicar los cambios*.
- **usdb_syncer**: ábrelo con `usdb_syncer`; en sus ajustes la carpeta de canciones debe ser
  `/home/djvemo/LetsSing/songs`. Descarga una canción nueva, pulsa *Actualizar* en el programa: debe aparecer en la
  tabla y convertirse con *Convertir solo esta canción*.

## 4. Qué quedó a medias / qué falta

1. **28 canciones con la portada fija como video** aunque tienen su videoclip (`video.mp4` puesto después de la
   primera conversión; B-66): La isla bonita, Mamma Mia, Ironic, Everybody, everything i wanted, Buy Me a Boat,
   Maneater, Blue (Da Ba Dee), Missing, Lose You to Love Me, Down to the Honkytonk, Best Shot, Sunny and 75,
   Alejandro, Bloody Mary, Someone You Loved, Mambo No. 5, Friends, Think a Little Less, Bohemian Rhapsody,
   The Invisible Man, We Will Rock You, Who Wants To Live Forever, There's Nothing Holdin' Me Back, All I Wanna Do,
   In Hell I'll Be In Good Company, Wake Me Up Before You Go-Go (+ Swish Swish por revisar). Volver a codificarlas
   tarda horas (RAD bajo Wine); los `.bk2` actuales se guardan en `_replaced_videos`. Necesita tu permiso.
2. **Revisar a mano** las 15 canciones marcadas por la revisión de voz (lista en `docs/07_CANCIONES_PROBLEMA.md` e
   `informe_sincronia.csv`): Something About Us (−1,08 s), Bad Decisions, ExtraL, Thumbs y 11 "parcial".
3. **Bitch Better Have My Money**: el audio es de otra versión; lo ideal es bajarlo de https://youtu.be/B3eAMGXFw1o.
4. **Mod saltar intro / terminar al acabar la letra**: diseño en `docs/10_MOD_SALTAR_INTRO.md`; falta permiso para
   descargar la plantilla exlaunch y probarlo en la consola.
5. **Temas** (Amor/Profunda/Fiesta): todas siguen con los tres (no hay datos oficiales para calcularlo bien).
6. **Varios idiomas por canción** ("Korean, English"): el juego lo admite, sin probar.
7. **beats / vxla_feat** de los DLC oficiales 2026: sin generar (el juego funciona sin ellos).
8. **B-61**: la ventana se congeló una vez; si pasa otra vez, el programa deja `hang_trace.log` en su carpeta.
9. **Canciones viejas de USDB**: sus archivos tienen nombre genérico (`audio.ogg`, `video.mp4`, `cover.png`); se
   convierten bien, pero si vuelves a descargar una en usdb_syncer, este reescribe su txt (se pierden los arreglos
   de esa canción). Las nuevas no tienen este problema.
10. Algunos años de canciones de Vocaloid salen 2000 (Melt es de 2007, Senbonzakura de 2011): por corregir.

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

Las tareas corren de una en una, como proceso aparte (la ventana no se congela). Detener una no pierde nada:
al volver a ejecutarla sigue donde se quedó. Los `.bk2` nunca se tocan.
