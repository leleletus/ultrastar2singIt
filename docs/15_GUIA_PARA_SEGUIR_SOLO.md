# Guía para seguir solo: corregir canciones, rehacer tonos, convertir y pasar a la Switch

Escrita el 2026-11-16. Todo lo de aquí se hace sin ayuda, con tres scripts. Las rutas son las de este PC
(`~/LetsSing/songs` = canciones, `~/LetsSing/output/0100EE4020D19003` = parche); en otro PC se cambian con las
variables `LETSSING_SONGS` y `LETSSING_PATCH`.

| Quiero… | Comando (desde cualquier carpeta) |
|---|---|
| Rehacer los tonos de una canción que corregí, convertirla y validarla | `~/LetsSing/cancion_lista.sh "parte del nombre"` |
| Pasar a la Switch solo lo que cambió, por cable | `~/LetsSing/pasar_a_switch.sh` |
| Lo mismo por Wi-Fi (FTP) | `~/LetsSing/pasar_a_switch.sh 192.168.18.198:5000` |
| Ver cómo va la reconversión de vídeos | `tail -f ~/LetsSing/reencode_videos.log` |
| Continuar la reconversión de vídeos si se cortó | `BORRAR_ANTIGUOS=1 ~/LetsSing/reconvertir_videos.sh` |

(`~/LetsSing/cancion_lista.sh` y `~/LetsSing/pasar_a_switch.sh` son enlaces a `tools/cancion_lista.sh` y
`tools/pasar_a_switch.sh` de este repositorio.)

## 1. Corregir una canción en el programa (tu parte: letra, posición y duración)

1. Abre el programa (menú de aplicaciones, o `~/ultrastar_official/start_linux.sh`).
2. Clic derecho en la canción → **Arreglar sincronización…** (marca *Solo SongMaker* para ver solo las fabricadas).
3. Mueve, alarga, acorta, clona o parte las palabras hasta que caigan donde se cantan. **No hace falta tocar el
   tono**: una nota movida o clonada se queda con el tono del sitio de donde vino, y eso lo arregla el paso 2.
4. Guarda con **Ctrl+S** y cierra el editor.

Qué canciones faltan y qué mirar en cada una: `~/LetsSing/INFORME_SONGMAKER.md` (las ya hechas llevan «✅ revisada»).
Para rehacer ese informe: `venv/bin/python tools/songmaker_report.py ~/LetsSing/songs --md ~/LetsSing/INFORME_SONGMAKER.md`.

## 2. Rehacer los tonos, convertir y validar (un solo comando)

```bash
~/LetsSing/cancion_lista.sh "Suerte"                 # basta una parte del nombre de la carpeta
~/LetsSing/cancion_lista.sh "Suerte" "Iris" "Who Knew"   # o varias de una vez
```

Qué hace, en orden:

1. **Tonos**: mide de nuevo el tono de todas las notas cantadas con la voz que hay donde está ahora cada nota, y
   deja una octava arriba las que de verdad se cantan arriba. Enseña las que cambian en más de un semitono.
2. **Notas que se pisan**: las lista con el minuto y segundo (`overlap at 1:23.45`). Si sale alguna, ábrela otra vez
   en el editor, acorta la nota de antes y repite el comando.
3. **Marca la canción como revisada** (ya no sale como pendiente en el informe).
4. **La convierte al parche**: solo se rehacen la letra y las notas (modo clásico, modo Feat y beats); el vídeo
   `.bk2` no se toca.
5. **Valida el parche entero**: tiene que acabar en `0 problem(s)`.

El txt de antes queda guardado en `~/LetsSing/_respaldo_songmaker/<fecha>_<canción>/`, por si hay que volver atrás
(se copia encima del txt de la canción y se repite el comando).

Para ver qué tonos cambiaría **sin escribir nada**: `PROBAR=1 ~/LetsSing/cancion_lista.sh "Suerte"`.

Dentro del editor, la tecla **P** hace la misma medida de tono sobre las notas seleccionadas (o toda la canción),
por si quieres oír el resultado antes de guardar. Con el comando de arriba no hace falta.

Tarda 2–3 minutos por canción (más mientras la reconversión de vídeos esté en marcha). Si dice que no hay análisis
de voz, abre la canción en el editor, pulsa «Analizar voz» y repite.

## 3. Pasar a la Switch (solo las diferencias)

Por cable: en la Switch abre **DBI → Run MTP responder** y conecta el USB. Por Wi-Fi: abre **ftpd** en la Switch
(pone la IP y el puerto en pantalla).

```bash
VER=1 ~/LetsSing/pasar_a_switch.sh                      # solo lista lo que copiaría (cable)
~/LetsSing/pasar_a_switch.sh                            # copia, por cable
~/LetsSing/pasar_a_switch.sh 192.168.18.198:5000        # copia, por Wi-Fi
```

- Compara el parche con la «foto» de lo que tiene la Switch (`~/LetsSing/0100EE4020D19003.switch.json`) y copia
  **solo los archivos nuevos o distintos**: las letras rehechas, los vídeos reconvertidos y la lista de canciones.
  Cada archivo distinto reemplaza al que había; no hay que borrar nada a mano.
- Antes valida el parche; con problemas no copia nada.
- Se puede cortar (o se puede caer el Wi-Fi) y volver a lanzar: sigue por donde iba.
- Con los vídeos reconvertidos la primera pasada es grande (cientos de vídeos, decenas de GB): mejor por cable y
  mirando antes que la SD tenga sitio, porque los vídeos nuevos pesan más que los antiguos.
- De los archivos pequeños que reemplaza guarda copia en `~/LetsSing/switch_backup_<fecha>/` (se puede borrar cuando
  todo funcione). De los vídeos no guarda copia.
- No juegues mientras copia. Al terminar, cierra y abre el juego.

## 4. La reconversión de vídeos (.bk2 con más calidad)

Trabaja sola en segundo plano (6 vídeos a la vez, perfil de energía «Performance», suspensión bloqueada).

```bash
tail -f ~/LetsSing/reencode_videos.log                 # cómo va y cuántas horas quedan (Ctrl+C para salir de verlo)
~/LetsSing/reconvertir_videos.sh parar                 # parar con calma (termina los que está haciendo)
BORRAR_ANTIGUOS=1 ~/LetsSing/reconvertir_videos.sh     # lanzar o continuar: sigue donde se quedó
```

- Hay que relanzarla después de apagar, reiniciar o cerrar la sesión. No pasa nada por lanzarla dos veces (avisa de
  que ya está en marcha).
- Cuando acabe, la última línea del registro dice `Finished this run: N encoded, M failed`. Los que fallen conservan
  su vídeo antiguo; al volver a lanzarla los intenta otra vez.
- Solo rehace vídeos con su vídeo original en la carpeta; nunca cambia un vídeo por una carátula fija.
- Al terminar: `~/LetsSing/pasar_a_switch.sh` para llevar los vídeos nuevos a la consola.
- En 28 canciones el vídeo nuevo va recortado igual que el audio (antes iba retrasado). Su lista está al principio
  del registro (línea `made from the whole clip`); conviene mirar una o dos en el juego.

## 5. Canciones nuevas

- Con versión en USDB: [12_CANCIONES_NUEVAS.md](12_CANCIONES_NUEVAS.md).
- Sin versión en USDB (fabricarla con SongMaker): [14_CANCIONES_SIN_USDB.md](14_CANCIONES_SIN_USDB.md), y luego
  los pasos 1–3 de esta guía.

## Si algo sale mal

| Qué pasa | Qué hacer |
|---|---|
| `cancion_lista.sh` dice que el nombre coincide con varias | escribe más del nombre, o la carpeta entera entre comillas |
| El validador da `problem(s)` | lee la línea: dice la canción y el archivo que falta; vuelve a lanzar `cancion_lista.sh` con esa canción |
| `pasar_a_switch.sh` dice «Can't open …» | la Switch no está en DBI → MTP responder (cable) o ftpd no está abierto / otra IP (Wi-Fi) |
| «The Switch does not have the expected patch» | la SD no tiene lo que la foto dice; no copia nada. Copia la carpeta del parche entera una vez |
| Un tono quedó mal después del paso 2 | en el editor selecciona la nota, súbela o bájala con Mayús+↑ / Mayús+↓, guarda, y convierte desde el programa (no repitas `cancion_lista.sh`, que volvería a medirla) |
| El programa pone otra vez 80 en «Tamaño máximo de vídeo» | ponlo en 250 en la sección de ajustes; con 80 los vídeos nuevos de canciones largas salen con menos calidad |
