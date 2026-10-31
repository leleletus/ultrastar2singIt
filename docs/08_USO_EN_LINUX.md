# 08 — Uso diario en Linux

Guía rápida para abrir el programa, tenerlo en el menú de aplicaciones y lanzar las tareas largas (revisar la
sincronía de toda la biblioteca) sin que molesten. Los comandos funcionan igual en bash, zsh y fish.

## Abrir el programa

```
~/ultrastar_official/start_linux.sh
```

`start_linux.sh` entra en la carpeta del proyecto, activa el entorno de Python (`venv`) y abre la interfaz.
La primera vez hay que haber instalado las dependencias (ver `README_Linux.md`).

## Acceso en el menú de aplicaciones (KDE y otros escritorios)

Una sola vez:

```
bash ~/ultrastar_official/install_linux_launcher.sh
```

Crea `~/.local/share/applications/letssing-ultrastar-converter.desktop` con el ícono del programa y refresca el
menú de KDE. Después aparece como **"Let's Sing UltraStar Converter"** en el lanzador; con clic derecho →
*Fijar en el gestor de tareas* queda en la barra.

- Si se mueve la carpeta del proyecto, volver a ejecutar el script (el acceso guarda la ruta).
- Para quitarlo: `rm ~/.local/share/applications/letssing-ultrastar-converter.desktop`

Contenido del acceso, por si se quiere crear a mano (cambiar la ruta si el proyecto está en otro sitio):

```ini
[Desktop Entry]
Type=Application
Name=Let's Sing UltraStar Converter
Comment=Convierte canciones UltraStar para Let's Sing y sincroniza letras
Exec=/home/USUARIO/ultrastar_official/start_linux.sh
Path=/home/USUARIO/ultrastar_official
Icon=/home/USUARIO/ultrastar_official/assets/logo.ico
Terminal=false
Categories=AudioVideo;Audio;
```

## Arreglar la sincronía de una canción

En la tabla: clic derecho sobre la canción → **Arreglar sincronización...** (o el ícono de la columna *Sinc.*).
Atajos del editor: Espacio reproducir, J/L ±5 s, coma/punto ±0,1 s, ↑/↓ línea, F primera letra, ←/→ mover
(Shift ±10 ms, Ctrl ±250 ms), C cortar inicio, V cortar fin, `[` `]` cambiar de parte, G toda la letra,
A ajustar a la voz, Ctrl+S guardar. Al guardar por primera vez queda una copia `.txt.bak` del original.

## Revisar la sincronía de toda la biblioteca

Separa la voz de cada canción UltraStar (unos 6 minutos por canción en CPU) y la compara con la letra. Se lanza
como servicio de usuario con **prioridad mínima** (solo usa la CPU que nadie usa) y un tope de memoria, así se
puede seguir usando el PC; sigue aunque se cierre la terminal o la sesión:

```
systemd-run --user --unit=revisa-sincronia -p CPUSchedulingPolicy=idle -p Nice=19 -p IOSchedulingClass=idle \
  -p MemoryMax=4G -p StandardOutput=file:$HOME/revision_sincronia.log \
  ~/ultrastar_official/venv/bin/python ~/ultrastar_official/tools/sync_scan.py ~/LetsSing/songs \
  --report ~/LetsSing/informe_sincronia.csv
```

| Para… | Comando |
|---|---|
| ver el avance | `tail -5 ~/revision_sincronia.log` |
| ver si sigue activo | `systemctl --user status revisa-sincronia` |
| pausar / detener | `systemctl --user stop revisa-sincronia` |
| seguir otro día | el mismo `systemd-run` (lo ya analizado se salta: la voz queda guardada en `<id>.voice.npz`) |
| rehacer solo el informe | `~/ultrastar_official/venv/bin/python ~/ultrastar_official/tools/sync_scan.py ~/LetsSing/songs --only-analyzed --report ~/LetsSing/informe_sincronia.csv` |

El informe (`informe_sincronia.csv`, se abre con LibreOffice, separador `;`) se reescribe tras cada canción,
con las peores arriba: `otra_version`, `parcial` (una parte desfasada, dice desde qué minuto), `desfase` (toda la
letra), `dudosa` y `ok`. Las canciones se revisan en el orden más sospechoso primero (letra más larga que el
audio, audio de USDB bajado de otro video, GAP negativo...). Al abrir una de ellas en el editor, los puntos
celestes de la voz ya aparecen sin esperar.

Para que los servicios sigan funcionando después de cerrar la sesión de KDE hace falta, una vez:
`loginctl enable-linger $USER` (se deshace con `loginctl disable-linger $USER`).

## Actualizar la Switch sin copiar todo el parche

Después de arreglar unas pocas canciones no hace falta reconvertir ni copiar los ~30 GB:

1. En el programa: clic derecho sobre cada canción arreglada → **Convertir solo esta** (actualiza el parche sin
   vaciarlo; los videos no se tocan).
2. En la Switch abrir **DBI → Run MTP responder** y conectar el cable USB.
3. Ver qué se copiaría (no cambia nada):
   ```
   ~/ultrastar_official/venv/bin/python ~/ultrastar_official/tools/switch_update.py ~/LetsSing/output/0100EE4020D19003
   ```
4. Copiar: el mismo comando con `--apply` al final.

La herramienta compara el parche con la "foto" de lo que tiene la Switch (`~/LetsSing/0100EE4020D19003.switch.json`,
se actualiza tras cada copia) y copia solo los archivos distintos. Antes comprueba en la Switch una muestra de
archivos (si no coinciden, la Switch tiene otro parche y no copia nada), guarda en
`~/LetsSing/switch_backup_<fecha>/` cada archivo que reemplaza y verifica el tamaño de cada copia. No borra nada
en la Switch. La primera vez hay que indicarle qué parche se copió entero, con
`--baseline ~/LetsSing/archivo/foto_parche_2026-10-25.json` (foto del parche completo del 25 de octubre).
Si alguna vez se copia el parche entero a mano, crear la foto nueva con el mismo comando pasando como
`--baseline` un archivo hecho justo después de esa copia (o volver a copiar con la herramienta).

## Si la ventana deja de responder

El programa guarda en `~/ultrastar_official/hang_trace.log` dónde estaba cada hilo cuando la ventana lleva más
de 10 s sin responder. Ese archivo dice la causa exacta: guardarlo antes de cerrar el programa. Para cerrar un
programa colgado: `pkill -f LetsSingUltraStarConverter`.
