# 10 — Mod para Let's Sing 2026: saltar el intro y terminar al acabar la letra

Estado: **diseño listo, sin construir ni probar** (2026-10-31). Todo lo de abajo sale del código del juego, no de
suposiciones; las direcciones valen **solo** para la versión analizada.

| | |
|---|---|
| Juego | Let's Sing 2026, base `0100EE4020D18000` + actualización v131072 |
| Build ID del ejecutable (`main`) | `1C344DD17322D4FA3E8F50063340C7D0` |
| Motor | Unity IL2CPP, metadata v31 |
| Volcado | `~/LetsSing/juegos/Let's Sing 2026/extraido/il2cpp_dump/` (dump.cs, script.json, il2cpp.h) |

Cómo se obtuvo: `global-metadata.dat` sacado en la consola con nxdumptool (RomFS con la actualización);
`exefs/main` extraído del NSP de la actualización con hactool; Il2CppDumper v6.7.46 bajo Wine. Para desensamblar:
`hactool -t nso --uncompressed` y `llvm-objdump` sobre un ELF (`llvm-objcopy -I binary -O elf64-littleaarch64`);
**en el archivo descomprimido las direcciones del volcado van +0x100** (cabecera NSO).

## Lo que hace el juego

| Pieza | Dirección (RVA) | Qué hace |
|---|---|---|
| `KaraokeManager.Init(GameSong, float fStartTime, float fEndTime, bool)` | `0x45909A0` | Guarda inicio/fin en `startTime` (+0x38) y `endTime` (+0x3C) y crea la `KaraokeSong`. **El motor ya admite empezar y terminar en cualquier punto** |
| `LoadingInGame.PrepareKaraoke(float startTime)` (virtual, slot 34) | `0x4802320` | Partida normal: llama a `Init(song, startTime, 0)` con inicio 0 |
| `LoadingInGameFest.PrepareKaraoke` | `0x4806D80` | Conciertos online ("Fest"): calcula un inicio a mitad de canción para ir a la par de los demás. Prueba de que audio, video y letra arrancan juntos en un punto cualquiera |
| `InGameSimple.SetTime(float time)` (virtual, slot 43) | `0x47A9C20` | Mueve el audio (`Voxler.SoundFile.SetPositionMs`) |
| `KaraokeManager.KTime` (+0x30) | — | Reloj de la letra: sigue al audio |
| `InGameSimple.VideoDesyncTolerance` (+0x108), `timeofLastJump` (+0x10C) | — | El video Bink se reengancha solo cuando se separa del audio |
| `InGameClassic.StartSong` / `InGameSimple.StartSong` | `0x47A38A0` / `0x47A3590` | Inicio de la partida (llama a `InGame.StartSong`, `0x479F890`, que arranca `KaraokeManager.StartVx`) |
| `InGameSimple.UpdateVx` (slot 18) | `0x47A4700` | Se llama cada fotograma durante la canción |
| `InGameClassic.SwitchToResult()` | `0x47A3D50` | Termina la canción y muestra resultados, como al acabar normalmente |
| `Lyrics.firstNoteStartTime` (+0x94) | — | Inicio de la primera nota |
| `KaraokePage.TryGetFirstNote` / `TryGetLastNote` | dump.cs l. 495206 | Primera/última nota de una página |
| `SortTypeComparer.Compare` | `0x45A5140` | Orden de las listas: "Título" ordena por `Singable.Id` (por eso el parche usa IDs con el título primero) |


Enumeraciones del juego (útiles para el conversor, ya aplicadas): idiomas `English, French, Spanish, German,
Korean, Other`; temas `Love, Deep, Party`; géneros `Pop, HipHop, Ballad, Rock, RnB, Electro, Country, Latin, Summer`;
dificultad `VeryEasy…VeryHard`; voz `Women, Men, Both`.

## Diseño del mod

1. **Saltar el intro**: después de `InGameClassic.StartSong`, si la primera nota empieza a más de ~10 s, llamar a
   `this->SetTime(primeraNota - 3)`. El audio salta, la letra sigue al audio y el video se reengancha solo.
   - Variante con botón: en vez de automático, solo si se pulsa un botón durante el intro (requiere leer el mando:
     hook de la lectura de input del juego o de `hid`).
2. **Terminar al acabar la letra**: en `UpdateVx`, si `KTime` > última nota + 3 s, llamar a `SwitchToResult()` una
   vez. Así una canción como Bitch Better Have My Money no sigue con el video tras la última línea.
3. **Solo partida normal** (Classic): no tocar Fest/Career/Feat (online o con reglas propias).

### Cómo construirlo

- Forma recomendada: un módulo **exlaunch** (plantilla en C++ para hooks en juegos de Switch, se carga como
  `subsdk9` desde `atmosphere/contents/0100EE4020D18000/exefs/`). Hooks: post-`StartSong` y post-`UpdateVx`. El
  compilador ya está en el PC (`/opt/devkitpro/devkitA64`). Falta descargar la plantilla exlaunch (GitHub): pedir
  permiso antes, igual que con Il2CppDumper.
- Alternativa sin plantilla: parche IPS (`atmosphere/exefs_patches/letssing_skip/<build id>.ips`) con el código en
  una zona libre; más frágil (hay que recorrer listas IL2CPP en ensamblador).
- Se quita borrando la carpeta; no toca las canciones ni la partida guardada. No usar en modos online.
- Cada actualización del juego cambia el Build ID y las direcciones: hay que volver a localizarlas en el volcado
  nuevo (los nombres de las funciones no cambian).

### Pasos para seguir

1. Confirmar con un hook de prueba (solo registra) que `StartSong`/`UpdateVx` se llaman en partida normal.
2. Hook de `SetTime` con un tiempo fijo (p. ej. 30 s) para comprobar que audio, letra y video saltan juntos.
3. Calcular la primera/última nota desde `KaraokeManager.Instance.KaraokeSong` y activar las dos funciones.
4. Probar en la consola con canciones de intro largo (BBHMM 94 s, Stan 82 s, Something About Us 78 s).
