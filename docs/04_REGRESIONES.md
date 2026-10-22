# 04 — Regresiones

Método: `git blame` de las líneas defectuosas + comparación con `upstream/main` (`69f8814`, v1.0.2).
Base de comparación del fork: `fd9fe37` (rama `main` local) → `linux-wine-support`.

| ID | Commit (fecha) | Qué cambió | Qué rompió | Bugs |
|---|---|---|---|---|
| R-01 | `5f0d14e` (2026-09-29) "Massive Overhaul" | Sync Editor, multihilo, herramientas, Linux | `return` mal indentado en la validación; `config.yml` al CWD; `log_message` inexistente; `SingleSelection` al reactivar; TSV/name.txt sin lock con multihilo; GUI no carga multihilo; filtro `_cover.mp4` nace aquí | B-01, B-18, B-21, B-23, B-05, B-19 |
| R-02 | `4e1cb35` (2026-10-05) "Fix Wine GStreamer segfault…" | intermedio y fallback pasan de `.mp4` a `.avi`; limpieza PIL de portadas | temporal compartido → portadas cruzadas con multihilo; filtros siguen en `_cover.mp4`; XML recibe un AVI llamado `.mp4`; los `<id>.mp4` intermedios viejos de carpetas JSON quedan huérfanos y además cuentan como video fuente | B-02, B-09, B-10 |
| R-03 | `3f60d56` (2026-10-02) "SyncEditor play the converted .ogg" | el editor prefiere `.ogg` | elige el primer `*.ogg` (puede ser la preview); el `.ogg` convertido lleva VIDEOGAP aplicado y el editor no lo suma a las letras | B-26 |
| R-04 | `0844bc6` (2026-10-05) "sanitize name_id strictly to ASCII" | filtro ASCII en ConvertFiles y Gui | (a) cambia el ID de canciones con `& ø œ æ ß` u otros no ASCII → su caché queda huérfana y se reconvierten; (b) si se fusiona con un `songs_xx.json` base de una conversión anterior, la canción aparece **dos veces** (ID viejo + nuevo); (c) `cache_recovery`, `unpacker`, `reverse_vxla`, `ExtractorPro` no se actualizaron | B-30, B-31 |
| R-05 | `362d058` (2026-10-03) "Fix cache wipe vulnerability" + `80ad4b9` (upstream) | escudo `_Patch` | `isfile` relativo al CWD; al aplicarse en GUI y en ConvertFiles puede anidar `_Patch/_Patch`; la ruta mostrada no es la usada | B-17 |
| R-06 | `fa8c111` (2026-10-03) i18n + `1194ff6` | menú de idioma | el idioma no se restaura al iniciar; en inglés el checkbox de medios aparece en español; textos nuevos fuera de `tr()` | B-20 |
| R-07 | `4cb04ff` (2026-10-02) columna Play | nueva columna desplaza índices | el "orden original" quedó en la columna 7 (ahora Lyrics) en vez de 8 | B-22 |
| R-08 | `5f0d14e` / `4cb04ff` + spec de `78a5b28` | `QtMultimedia` importado en Gui | el spec heredado excluye `QtMultimedia` → build probablemente roto (a verificar) | B-41 |
| R-09 | `1e04eba` (2026-10-03) "natively name media files" (unpacker) | renombrado de medios al desempaquetar | introdujo `safe_artist`/`safe_title` sin definir → Tools → Unpack falla siempre | B-32 |
| R-10 | `2c2beb9` / `8f2a560` (2026-10-02) | loudnorm → dynaudnorm | no es regresión de sincronía, pero `dynaudnorm` cambia la dinámica de forma variable a lo largo del tema; el comentario "match −16 LUFS" no se cumple (no mide sonoridad). Vigilar quejas de volumen desigual | M-12 |

## Herencias de upstream (no son regresiones del fork, pero siguen abiertas)

| Origen | Problema | Bug |
|---|---|---|
| `80ad4b9` (upstream) | JSON leído con `utf-8` (sin BOM) | B-03 |
| `5f0d14e` sobre heurística de `da53b6c` (upstream) | corrección de tono "fast" (+48 / no octava) | B-06 |
| upstream | `normalize_text` elimina tildes en letras | B-40 |
| upstream | caché del vxla por mtime | B-13 |
| upstream `18-add-support-for-duets` (sin fusionar) | duetos sin soporte | B-29 / M-04 |

## Cómo evitar nuevas regresiones

1. Antes de renombrar un archivo generado, buscar el nombre en todo el repo (ver "Mapa de impacto" en `01_INFORME_TECNICO.md`).
2. Un único módulo para nombres/IDs y para la resolución de fuentes (B-08, B-30).
3. Pruebas mínimas (M-01): parser, name_id, tono, `get_required_files`, escritura JSON/TSV con hilos, `required_fields_missing`.
4. Conjunto de canciones de prueba fijo (`test_input/`) con casos difíciles: BOM, CRLF, sin video, sin portada, dueto, VIDEOGAP,
   año no numérico, nombre con `&`/`ø`, nombre no latino.
