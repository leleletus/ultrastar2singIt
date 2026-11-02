# Documentación técnica — Let's Sing UltraStar Converter

Documentación interna del fork (rama `linux-wine-support`). Auditoría inicial: commit `4e1cb35` (2026-10-21);
01, 02 y 06 actualizados al código del 2026-11-01. El día a día está en `05_BITACORA.md`.

| Documento | Contenido |
|---|---|
| [01_INFORME_TECNICO.md](01_INFORME_TECNICO.md) | Arquitectura, flujo de conversión, formatos de salida, caché, configuración, dependencias, mapa "si tocas X revisa Y" |
| [02_REFERENCIA_SCRIPTS.md](02_REFERENCIA_SCRIPTS.md) | Script por script y función por función, con línea y bugs relacionados |
| [03_BUGS.md](03_BUGS.md) | Registro de bugs (ID, severidad, ubicación, causa, impacto, arreglo) |
| [04_REGRESIONES.md](04_REGRESIONES.md) | Regresiones atribuidas a commits concretos (vía `git blame` / comparación con `upstream/main`) e historia del ID interno |
| [05_BITACORA.md](05_BITACORA.md) | Bitácora: historia del proyecto por fases según git y entradas de trabajo |
| [06_BACKLOG_Y_MEJORAS.md](06_BACKLOG_Y_MEJORAS.md) | Estado del backlog, mejoras de la interfaz, plan de trabajo |
| [07_CANCIONES_PROBLEMA.md](07_CANCIONES_PROBLEMA.md) | Canciones reportadas con problemas: causa, arreglo y diagnóstico de la biblioteca |
| [08_USO_EN_LINUX.md](08_USO_EN_LINUX.md) | Uso diario en Linux: abrir el programa, acceso en el menú, tareas largas, Switch por MTP, ventana colgada |
| [09_HISTORIAL_BUGS.md](09_HISTORIAL_BUGS.md) | Resumen de todos los bugs: cerrados (con su commit), pendientes y mejoras por hacer |
| [10_MOD_SALTAR_INTRO.md](10_MOD_SALTAR_INTRO.md) | Mod de Let's Sing 2026 (saltar el intro): lo que dice el código del juego, compatibilidad, enlace a su repositorio |
| [11_GUIA_DE_PRUEBAS.md](11_GUIA_DE_PRUEBAS.md) | Qué cambió, cómo probarlo en la consola y en el PC, qué falta (2026-11-01) |
| [12_CANCIONES_NUEVAS.md](12_CANCIONES_NUEVAS.md) | Añadir canciones nuevas: usdb_syncer → programa → Switch |
| [13_MODO_FEAT.md](13_MODO_FEAT.md) | Modo Feat de 2026: archivos oficiales, reglas, cómo se generan la letra feat, la segunda voz y los beats, fiabilidad |
| [correcciones_metadatos.csv](correcciones_metadatos.csv) | Artista/título corregidos (entrada de `tools/rename_songs.py`) |

## Convenciones

- **IDs**: `B-xx` bug, `R-xx` regresión, `M-xx` mejora/backlog, `G-xx` mejora de interfaz gráfica.
- **Severidad**: `CRÍTICO` (rompe la conversión o puede colgar la consola), `ALTO` (resultado incorrecto o función rota),
  `MEDIO` (falla en casos concretos o degrada mucho la experiencia), `BAJO` (cosmético o raro).
- **Estado**: `ABIERTO`, `EN CURSO`, `CERRADO (commit)`, `A VERIFICAR` (sospecha fundada, falta prueba real).
- Las referencias `archivo.py:NNN` del detalle de B-01…B-45 (03_BUGS.md) apuntan a líneas del commit `4e1cb35`; las de
  02_REFERENCIA_SCRIPTS.md, al código actual. Al cerrar un bug, anotar el commit en `03_BUGS.md` y `09_HISTORIAL_BUGS.md`
  y añadir una entrada en `05_BITACORA.md`.
- **Rutas**: las guías de uso (08, 12) usan marcadores: `<proyecto>` = carpeta del repositorio, `<canciones>` = carpeta
  de entrada, `<salida>` = carpeta de salida. La bitácora, los registros de bugs y las guías 07 y 11 describen la
  biblioteca del autor (`~/LetsSing/songs`, `~/LetsSing/output`): son historia, no instrucciones para otro PC.
- Evidencia de campo: `error.log` (9 771 líneas, 2026-09-17 → 2026-10-05) se usó para confirmar los fallos reales más frecuentes.
