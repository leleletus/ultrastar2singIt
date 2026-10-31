# Documentación técnica — Let's Sing UltraStar Converter

Documentación interna del fork (rama `linux-wine-support`). Estado auditado: commit `4e1cb35` (2026-10-05). Arreglos posteriores: ver `05_BITACORA.md`.
Fecha de la auditoría: 2026-10-21.

| Documento | Contenido |
|---|---|
| [01_INFORME_TECNICO.md](01_INFORME_TECNICO.md) | Arquitectura, flujo de conversión, formatos de salida, caché, mapa de dependencias ("si tocas X revisa Y") |
| [02_REFERENCIA_SCRIPTS.md](02_REFERENCIA_SCRIPTS.md) | Script por script y función por función, con línea exacta y notas |
| [03_BUGS.md](03_BUGS.md) | Registro de bugs (ID, severidad, ubicación, causa, impacto, arreglo propuesto, relacionados) |
| [04_REGRESIONES.md](04_REGRESIONES.md) | Regresiones atribuidas a commits concretos (vía `git blame` / comparación con `upstream/main`) |
| [05_BITACORA.md](05_BITACORA.md) | Bitácora: historia del proyecto por fases según git y entradas de trabajo |
| [06_BACKLOG_Y_MEJORAS.md](06_BACKLOG_Y_MEJORAS.md) | Backlog priorizado, mejoras de la interfaz gráfica, plan de trabajo por fases |
| [07_CANCIONES_PROBLEMA.md](07_CANCIONES_PROBLEMA.md) | Canciones reportadas con problemas: causa probable, arreglo que la cubre y qué verificar |
| [08_USO_EN_LINUX.md](08_USO_EN_LINUX.md) | Abrir el programa, acceso en el menú (KDE), revisar la sincronía de la biblioteca en segundo plano, ventana colgada |

## Convenciones

- **IDs**: `B-xx` bug, `R-xx` regresión, `M-xx` mejora/backlog, `G-xx` mejora de interfaz gráfica.
- **Severidad**: `CRÍTICO` (rompe la conversión o puede colgar la consola), `ALTO` (resultado incorrecto o función rota),
  `MEDIO` (falla en casos concretos o degrada mucho la experiencia), `BAJO` (cosmético o raro).
- **Estado**: `ABIERTO`, `EN CURSO`, `CERRADO (commit)`, `A VERIFICAR` (sospecha fundada, falta prueba real).
- Las referencias `archivo.py:NNN` apuntan a líneas del commit `4e1cb35`. Al cerrar un bug, anotar el commit en `03_BUGS.md`
  y añadir una entrada en `05_BITACORA.md`.
- Evidencia de campo: `error.log` (9 771 líneas, 2026-09-17 → 2026-10-05) se usó para confirmar los fallos reales más frecuentes.
