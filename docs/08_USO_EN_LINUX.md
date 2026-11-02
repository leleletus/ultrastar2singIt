# 08 — Uso diario en Linux

Guía rápida para abrir el programa, tenerlo en el menú de aplicaciones y lanzar las tareas largas (revisar la
sincronía de toda la biblioteca) sin que molesten. Los comandos funcionan igual en bash, zsh y fish.

En los ejemplos:

| Marcador | Qué es |
|---|---|
| `<proyecto>` | la carpeta donde clonaste este repositorio (`git clone …`) |
| `<canciones>` | la carpeta de entrada del programa (si usas usdb_syncer, la misma que su carpeta de canciones) |
| `<salida>` | la carpeta de salida del programa; el parche queda en `<salida>/<TitleID del DLC>` |

Instalación en un PC nuevo (Wine, RAD Video Tools, venv): [`README_Linux.md`](../README_Linux.md).

## Abrir el programa

```
<proyecto>/start_linux.sh
```

`start_linux.sh` entra en la carpeta del proyecto, activa el entorno de Python (`venv`) si existe (si no, usa el
`python3` del sistema) y abre la interfaz. La primera vez hay que haber instalado las dependencias (ver
`README_Linux.md`).

## Acceso en el menú de aplicaciones (KDE y otros escritorios)

Una sola vez:

```
bash <proyecto>/install_linux_launcher.sh
```

Crea `~/.local/share/applications/letssing-ultrastar-converter.desktop` con el ícono del programa y refresca el
menú de KDE. Después aparece como **"Let's Sing UltraStar Converter"** en el lanzador; con clic derecho →
*Fijar en el gestor de tareas* queda en la barra.

- Si se mueve la carpeta del proyecto, volver a ejecutar el script (el acceso guarda la ruta).
- Para quitarlo: `rm ~/.local/share/applications/letssing-ultrastar-converter.desktop`

Contenido del acceso, por si se quiere crear a mano (con la ruta real del proyecto en lugar de `<proyecto>`):

```ini
[Desktop Entry]
Type=Application
Name=Let's Sing UltraStar Converter
Comment=Convierte canciones UltraStar para Let's Sing y sincroniza letras
Exec=<proyecto>/start_linux.sh
Path=<proyecto>
Icon=<proyecto>/assets/logo.ico
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
Lo más sencillo es lanzarlo desde la app (apartado 5 → *Revisar la sincronía de cada canción con la voz*). Desde la
terminal, como servicio de usuario con **prioridad mínima** (solo usa la CPU que nadie usa) y un tope de memoria, así
se puede seguir usando el PC; sigue aunque se cierre la terminal o la sesión. Necesita Demucs
(`pip install -r requirements-slow.txt`):

```
systemd-run --user --unit=revisa-sincronia -p CPUSchedulingPolicy=idle -p Nice=19 -p IOSchedulingClass=idle \
  -p MemoryMax=4G -p StandardOutput=truncate:$HOME/revision_sincronia.log \
  <proyecto>/venv/bin/python <proyecto>/tools/sync_scan.py <canciones> \
  --report <canciones>/../informe_sincronia.csv
```

| Para… | Comando |
|---|---|
| ver el avance | `tail -5 ~/revision_sincronia.log` |
| ver si sigue activo | `systemctl --user status revisa-sincronia` |
| pausar / detener | `systemctl --user stop revisa-sincronia` |
| seguir otro día | el mismo `systemd-run` (lo ya analizado se salta: la voz queda guardada en `<id>.voice.npz`) |
| rehacer solo el informe | `<proyecto>/venv/bin/python <proyecto>/tools/sync_scan.py <canciones> --only-analyzed --report <canciones>/../informe_sincronia.csv` |

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
   <proyecto>/venv/bin/python <proyecto>/tools/switch_update.py <salida>/<TitleID del DLC>
   ```
4. Copiar: el mismo comando con `--apply` al final.

La herramienta compara el parche con la "foto" de lo que tiene la Switch (`<salida>/../<TitleID>.switch.json`,
se actualiza tras cada copia) y copia solo los archivos distintos. Antes comprueba en la Switch una muestra de
archivos (si no coinciden, la Switch tiene otro parche y no copia nada), guarda en
`<salida>/../switch_backup_<fecha>/` cada archivo que reemplaza y verifica el tamaño de cada copia. Sin `--prune`
no borra nada en la Switch. Si la Switch tiene un parche copiado a mano, la primera vez hay que darle la foto de ese
parche con `--baseline <foto.json>`; lo más simple es vaciar la carpeta del DLC en la Switch y dejar que la
herramienta lo copie todo (a partir de ahí lleva la foto sola). Necesita KDE (`kioclient`) y DBI.

## Mantener la biblioteca (herramientas)

Todas solo muestran lo que harían; con `--apply` lo hacen (los txt que tocan quedan con copia `.txt.bak`).

| Herramienta | Para qué |
|---|---|
| `tools/fix_covers.py <canciones> --extracted <juegos extraídos> [--dlc] [--blank] [--song "<carpeta>"]` | portadas propias: enlace del .usdb, portada oficial, single/álbum de la tienda |
| `tools/fix_years.py <canciones> --extracted <juegos extraídos>` | año real de las canciones de DLC que tenían 2020 |
| `tools/artist_genders.py <canciones>` | voz (hombre/mujer/ambos) por artista para 2026; deja `<canciones>/_artist_genders.json` |
| `tools/validate_patch.py <salida>/<TitleID del DLC>` | revisar el parche antes de copiarlo a la Switch |

Después de cualquiera de ellas, convertir (los videos no se recodifican) y copiar con `switch_update.py`.
En la interfaz, la columna **Sinc.** muestra el resultado de la revisión de voz de cada canción (naranja: revisar) y
el motivo al pasar el ratón; si se resincroniza la canción, el aviso viejo desaparece.

## Si la ventana deja de responder

El programa guarda en `<proyecto>/hang_trace.log` dónde estaba cada hilo cuando la ventana lleva más
de 10 s sin responder. Ese archivo dice la causa exacta: guardarlo antes de cerrar el programa. Para cerrar un
programa colgado: `pkill -f LetsSingUltraStarConverter`.
