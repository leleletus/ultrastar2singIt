# 10 — Mod para Let's Sing 2026: saltar el intro y terminar al acabar la letra

Estado: **funciona en la consola (2026-11-01)**. Botón (ZR/ZL, SL/SR) durante el intro, salto a 3 s antes de la
primera nota. Todo lo de abajo sale del código del juego, no de suposiciones; las direcciones valen **solo** para la
versión analizada.

**Repositorio del mod**: https://github.com/leleletus/letssing2026-skip-intro (código, `build.sh`, release con el
zip para la SD, compatibilidad e instrucciones para adaptarlo a otra versión). En este proyecto se clona en
`mods/skip_intro/`, que está en `.gitignore`: es un repositorio aparte.

| Compatibilidad | |
|---|---|
| Juego | Let's Sing 2026, base `0100EE4020D18000` |
| Actualización | **solo v131072** (`0100EE4020D18800`). Con otra, el juego se cierra o el mod no hace nada: quitarlo |
| DLC / canciones del conversor | no influyen: funciona con y sin ellas |
| Firmware | Atmosphère (`atmosphere/contents/0100EE4020D18000/exefs/`) |
| Emuladores | sin probar |

| | |
|---|---|
| Juego | Let's Sing 2026, base `0100EE4020D18000` + actualización v131072 |
| Build ID del ejecutable (`main`) | `1C344DD17322D4FA3E8F50063340C7D0` |
| Motor | Unity IL2CPP, metadata v31 |
| Volcado | `il2cpp_dump/` (dump.cs, script.json, il2cpp.h) de Il2CppDumper sobre `exefs/main` + `global-metadata.dat`; no se versiona (es código del juego) |

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

### Cómo está hecho

- Módulo **exlaunch** (commit `f9f4b0d`, GPL-2.0) cargado como `subsdk9` desde
  `atmosphere/contents/0100EE4020D18000/exefs/`. Un gancho en `InGameClassic.UpdateVx` (cada fotograma, solo partida
  normal) lee el mando con `nn::hid::GetNpadState` y, si se pulsa ZR/ZL con más de 6 s hasta la primera nota, llama a
  `InGameSimple.SetTime(primeraNota - 3)`.
- `main.npdm` = el del juego + llamadas al sistema `0x40`, `0x43`, `0x74`, `0x75` (sin ellas: "Undefined System
  Call 0x74", B-69).
- Compilar: `./build.sh` en el repositorio del mod (devkitA64 + `npdmtool`). La salida es idéntica en código al
  release publicado.
- Se quita borrando la carpeta; no toca las canciones ni la partida guardada. No usar en modos online.
- Cada actualización del juego cambia el Build ID y las direcciones: hay que volver a localizarlas en el volcado
  nuevo (los nombres de las funciones no cambian). Pasos en el README del mod.

### Pendiente

1. **Terminar al acabar la letra**: en `UpdateVx`, si `KTime` > última nota + 3 s, llamar a `SwitchToResult()` una
   vez (canciones como Bitch Better Have My Money, cuyo video sigue tras la última línea).
2. **Video sin acelerar**: tras el salto, el video Bink se pone al día acelerando un momento (`VideoDesyncTolerance`);
   lo ideal es moverlo directo al mismo tiempo que el audio.
