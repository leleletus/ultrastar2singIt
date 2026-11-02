# 12 — Añadir canciones nuevas (usdb_syncer → programa → Switch)

Biblioteca: `<canciones>`, la carpeta de canciones de usdb_syncer, que es también la carpeta de entrada del programa
(en usdb_syncer: ajustes → *Song directory*). Parche: `<salida>/<TitleID del DLC>` (por ejemplo `0100EE4020D19003`,
el DLC 3 de Let's Sing 2026).

## 1. Descargar

Abrir `usdb_syncer` (comando en la terminal) y descargar las canciones. Cada una queda en su carpeta
`Artista - Título/` con `Artista - Título.txt`, `.m4a`, `.mp4`, `[CO].jpg`, `[BG].jpg` y `<id>.usdb`. No hace falta
renombrar ni mover nada.

## 2. Convertir solo las nuevas

1. Abrir el programa (icono del menú o `<proyecto>/start_linux.sh`). Si ya estaba abierto, **Actualizar**.
   Las canciones nuevas salen como **Pendiente**.
2. Arriba de la lista: marcar **Solo pendientes** → **Marcar todas las visibles** → **Convertir marcadas**.
   - "Convertir marcadas" **añade** las canciones al parche que ya existe (no vacía la salida, no toca las demás).
   - No usar "Iniciar conversión" para esto: convierte todas (los videos ya hechos se reutilizan, pero tarda más y,
     con "Vaciar la salida", rehace la carpeta de salida entera).
   - El video de cada canción nueva se codifica a `.bk2` (varios minutos por canción). Junto a **Hilos** está
     **Recomendado: N**: cuántas canciones a la vez rinden más en este PC.
3. Al terminar, quitar "Solo pendientes" y marcar **Solo problemas** para revisar las nuevas:
   - **Triángulo naranja en Video**: el video es la portada fija (USDB no tenía video). Clic derecho →
     **Añadir un video (archivo o enlace)…**, pegar el enlace de YouTube del videoclip; el programa lo recorta al
     segundo exacto. Luego clic derecho → **Convertir solo esta canción**.
   - **Sinc. naranja**: posible desfase. Clic en la columna Sinc. abre el Sync Editor (mover la letra, mover notas en
     vertical, Analizar voz / Ajustar a la voz).

Opcional, en **5. Opciones avanzadas** (marcar la casilla para desplegarlo), antes de convertir:
- **Averiguar si cada cantante es hombre o mujer**: solo pregunta por los artistas nuevos (segundos).
- **Añadir el género** a las que no traen `#GENRE` (unos segundos por canción).
- Estas dos cambian datos de la lista del juego; si se hacen después de convertir, volver a convertir esas canciones.

## 3. Pasar a la Switch (solo lo nuevo)

1. **5. Opciones avanzadas** → **Comprobar el parche antes de copiarlo a la consola** → Ejecutar: debe decir
   `0 problem(s)`.
2. En la Switch: **DBI → Run MTP responder** y conectar el cable.
3. **5. Opciones avanzadas** → **Actualizar el parche en la Switch (MTP, DBI)**, marcar **Aplicar los cambios** →
   Ejecutar. Necesita Linux con KDE (`kioclient`).
   - **La primera vez en este PC** (todavía no hay foto de lo que tiene la Switch): marcar también **Primera copia**.
     Copia el parche entero, solo si la carpeta del DLC en la Switch no existe o está vacía; si tiene archivos de
     una copia anterior hecha a mano, vaciarla antes con DBI.
   - Copia **solo los archivos nuevos o cambiados**: audio, vista previa, portada, video y letra de las canciones
     nuevas, y al final `songs_int.json` (la lista de canciones). Las carpetas no se copian enteras.
   - La lista se copia la última: si el cable se suelta, la consola sigue con la lista anterior completa; volver a
     ejecutarla continúa donde quedó (y reintenta solo los fallos sueltos de MTP).
   - Si dice que hay archivos "no longer in the patch" (por ejemplo una canción nueva con el mismo ID que una que ya
     estaba: el programa añade un número al ID), marcar también **Quitar de la Switch los archivos de canciones que ya
     no están en el parche**.
4. Salir de DBI, abrir Let's Sing y probar las canciones nuevas.

## A tener en cuenta

- **No volver a descargar en usdb_syncer una canción ya arreglada**: reescribe su txt (se pierden la sincronía
  ajustada, `#GENRE`, `#YEAR`, la portada elegida) y puede renombrar la carpeta. El `.bk2` ya convertido se reutiliza.
- **Nunca se borra un `.bk2`** al convertir: solo se rehace uno que sea la portada fija cuando la carpeta tiene un video
  con movimiento (el viejo se guarda en `<canciones>/../_replaced_videos`).
- Ningún paso necesita internet salvo la descarga, "Añadir un video" con enlace y las herramientas de datos (internet).
