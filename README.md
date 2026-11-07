# Let's Sing UltraStar Converter
This converter helps you add custom songs to your Let's Sing game by mimicking the structure of the official song pack DLCs.
It converts UltraStar karaoke files (found on a well known Spanish UltraStar site) to the selected DLC format.

The goal of this converter is full automation, it converts the provided song covers, audio, video and lyrics files
to the correct format and generates the required structure with minimal fiddling.

## Credits
 - Major props go to [dh4rry](https://github.com/dh4rry), the original creator of the ultrastar2singit script used for converting the UltraStar text
   files into Let's Sing's vxla format. [Here](https://gbatemp.net/threads/add-your-own-songs-to-lets-sing-2019.538379/) is the link to the original
   post focusing on Let's Sing 2019 with discussions on how to replace the original DLC files with custom songs.
 - Many props go to [MRJPGames](https://github.com/MrJPGames) for writing a
   [comprehensive tutorial](https://gbatemp.net/threads/add-custom-songs-to-lets-sing-2022-from-ultrastar.607817/) on how to prepare all the needed
   files for adding new songs instead of replacing them for Let's Sing 2022.
 - Overwhelming props go to [kosei](https://gbatemp.net/members/kosei.626603/), for writing a script to automate this whole conversion process
   [in the same thread](https://gbatemp.net/threads/add-custom-songs-to-lets-sing-2022-from-ultrastar.607817/post-10037766).
   Kosei's converter script was the jumping off point for my contributions.
 - Special thanks to [omnialord](https://github.com/omnialord) also from gbatemp for contributing to the project with bug fixes and fresh ideas,
   as well as for helping keep this game's modding scene alive.

UltraStar karaoke files lack proper standardization, so a simple desire to quickly add a couple of songs to the game quickly evolved into a fully fledged project. 
Inspired by kosei’s automation script, and compelled by poor standardization, I extensively modified his
scripts to streamline the conversion process as much as possible (while taking some [Creative Liberties](#creative-liberties)).

After successfully adding over 400 songs to Let’s Sing 2022 and realizing the shortcomings of this game version,
I expanded support for other versions of the game as well. Newer versions of Let's Sing (2024+) feature a superior
song selection menu designed for hundreds of tracks rather than just a few dozen and aren't so prone to crashing.
To make the whole process even more user-friendly, I've implemented a GUI and packaged the converter as a standalone executable,
so you don't need to worry about installing Python or any dependencies.

## What this fork adds (`linux-wine-support` branch)
**Mod for Let's Sing 2026: skip long intros.** Press ZR/ZL during a song's intro and it jumps to 3 s before the
first note (normal mode only). **Only for game update v131072** (build ID `1C344DD17322D4FA3E8F50063340C7D0`).
Its own repository, with the download, compatibility and build instructions:
[leleletus/letssing2026-skip-intro](https://github.com/leleletus/letssing2026-skip-intro).

Detailed technical notes, bug list, regressions and work log (in Spanish) are in [`docs/`](docs/README.md).

**Your converted videos are safe.** Encoding a `.bk2` can take hours, so the converter never deletes or re-encodes one:
"Clear cache" keeps them (double confirmation), a failed encode never replaces a good file, and before the output
folder is cleared any video without a copy in its song folder is rescued.

**Sync editor** (right click on a song → *Fix sync…*), a small video editor for the lyrics: move all the lyrics
or only a part of the song, see where the singer really is, fix the pitch of a note, delete lyrics where nothing is
sung and fix misspelt words, and sing over it with a microphone. Every button and shortcut is described in
[Sync editor: buttons and shortcuts](#sync-editor-buttons-and-shortcuts).

**Lyrics and notes**
- Songs rebuilt from older Let's Sing DLCs use the official vxla (`letssing_original.vxla`, see
  `tools/attach_official_vxla.py`): exact timing, pitch and syllables; v2.0 files are converted to the 2024+ format.
- Encoding detection on the whole txt (accents and apostrophes were silently deleted before), `#START`/`#END`,
  pitch moved only by whole octaves, words no longer glued together, passages (`long`/`speed`) like the official files.
- Each song keeps a signature of how its lyrics and audio were made, so only what changed is converted again.

**Library tools** (`tools/`, all of them only report unless `--apply` is given)
| Tool | What it does |
|---|---|
| `diagnose_library.py` | finds rebuilt songs, missing lyrics, glued lyrics, odd pitch, `#START` songs |
| `attach_official_vxla.py` | pairs rebuilt songs with their official vxla by their lyrics |
| `rename_songs.py` | fixes wrong artist/title and renames the folder and its cache (videos included) |
| `usdb_sources.py` | songs whose audio was downloaded from another video than the one the lyrics were timed to |
| `sync_check.py` / `sync_scan.py` | compares the lyrics with the isolated voice, one song or the whole library (CSV report) |
| `fix_covers.py` | gives every song its own cover: USDB link, official cover, single/album of the store (never compilations) |
| `fix_years.py` | real release year (MusicBrainz, iTunes) for songs rebuilt from DLCs that had the DLC year |
| `artist_genders.py` | men / women / both for each artist (MusicBrainz), used for the "gender" of Let's Sing 2026 |
| `align_voices.py` / `songmaker_report.py` | speech-model alignment of SongMaker lyrics (resumable batch) / report of the made songs with what to fix by hand |
| `validate_patch.py` | checks the patch before copying it: files, values the game accepts, covers, lyrics |
| `switch_update.py` | copies to the Switch over MTP (DBI) only the files that changed; `--prune` removes renamed ones |

**Let's Sing 2026** (only this edition; older ones are generated as before): the "Title" list of the game is sorted
by the song ID, so the patch uses title-first IDs; real language (English/French/Spanish/German/Korean/Other), genre
(HipHop, RnB, Latin...), difficulty (estimated from the notes) and singer. **Feat mode** works with converted songs: each one gets
the Feat lyrics the game needs (choruses sung together, the second singer's lines from UltraStar duets or from the
sections of Genius) and its beats ([`docs/13_MODO_FEAT.md`](docs/13_MODO_FEAT.md)). What the game's code says and how the
skip-intro mod works: [`docs/10_MOD_SALTAR_INTRO.md`](docs/10_MOD_SALTAR_INTRO.md).

**GUI**: fast song table with per-song status, convert only the checked songs or a single one, coloured log,
settings remembered, full Spanish translation. Tests: `python -m unittest discover -s tests -t .`

## Sync editor: buttons and shortcuts
Open it with a right click on a song → *Fix sync…* (*Arreglar sincronización...*). Tick **Only SongMaker** (*Solo
hechas con SongMaker*) above the song list to see only the songs SongMaker made (the ones to check by ear; what to
look at in each one: `tools/songmaker_report.py`). Button names are shown in English
and, in brackets, as they appear with the Spanish translation. Hovering over any button shows what it does and its
shortcut. Shortcuts work while the editor window is active (not while typing in a text box).

**Songs that use an official Let's Sing lyrics file** (`letssing_original.vxla`) open **read-only**: the game uses
their timing as it is, so only playback, voice analysis and sing mode work; the editing buttons are greyed out.

### Window, from top to bottom
| Part | What it shows / does |
|---|---|
| Info line | audio and video files used, and warnings (still-image video, lyrics longer than the audio, official file...) |
| Video | the song's video, in sync with the audio |
| Note lane | the notes as bars like the game, **with their syllable written under them**: **blue** = normal note, **yellow** = golden note, **grey bar at the bottom** = rap note (only the timing counts, not the pitch). The white vertical line is "now"; the name of the note being sung is shown next to it. Horizontal guides = one per semitone (labelled on every C). After *Analyze voice*, **light-blue dots** = the singer's real voice. In sing mode, **green / red dots** = your voice on / off the note. A **white outline** = the selected note. The **orange tint** = the part the arrows move; **orange lines** = cuts |
| Karaoke lyrics | the line being sung, coloured as it goes, and the next one |
| Timeline | click anywhere to jump there |
| Moving through the song | **mouse wheel** over the note lane or the line map: half a second a step (2 s with `Ctrl`); **drag an empty place of the note lane** sideways to scroll like a map |
| Line map | one block per lyrics line: **green** = on the voice, **orange** = a bit off, **red** = out of time, **grey** = voice not analysed yet (or the line is barely sung). Orange triangles = cuts, white box = selected part, red line = end of the audio. Click to jump there (and select that part) |

### Mouse on the note lane
| Action | What it does |
|---|---|
| Click a note | selects it (white outline); rap notes can be selected too |
| Drag the middle of a note up / down | changes its pitch by semitones (sung notes only) |
| Drag the middle of a note sideways | moves it in time (the first move decides: sideways = time, up/down = pitch) |
| Drag the **right edge** of a note (the cursor becomes ↔) | makes it longer or shorter |
| Drag the left edge of a note | moves its start, its end stays |
| Double click a note | fixes the text of that syllable (see [Lyrics](#lyrics-fix-misspelt-words-delete-what-is-not-sung)) |
| `Ctrl` + click a note | adds it to the selection, or takes it out: **several notes selected** |
| `Shift` + click a note | selects every note from the selected one to this one |
| `Shift` + drag an empty place | selects the notes that start in that stretch (shaded while dragging; with `Ctrl` too, they are added to the ones already selected) |
| `Ctrl+A` | selects the whole line of the selected note (or the line being played) |
| Drag one of the selected notes | **they all move together**: sideways in time (they stop at the first note that is not selected) or up/down in pitch |
| Click one of the selected notes | only that one stays selected |
| `Esc` | nothing selected. With nothing selected, `Esc` closes the editor and asks first if there are unsaved changes |

Moving and resizing go in whole beats of the song (37.5 ms in SongMaker songs) and a note never goes over the notes
before and after it (shorten or move the neighbour first).

### Playback
| Button | Name | Shortcut | What it does |
|---|---|---|---|
| ⏮ skip back | Go to the start (*Ir al inicio*) | `Home` | jumps to 0:00 |
| ⏮ previous track | Previous line (*Línea anterior*) | `Up` | goes back to the start of the line being sung; pressed again (in the first second of the line), to the line before |
| ⏪ 5 | Back 5 seconds (*Retroceder 5 segundos*) | `J` | |
| ‹ | Back 0.1 seconds (*Retroceder 0,1 segundos*) | `,` | fine positioning |
| ▶ / ⏸ (big) | Play / pause (*Reproducir / pausar*) | `Space` | |
| › | Forward 0.1 seconds (*Avanzar 0,1 segundos*) | `.` | |
| ⏩ 5 | Forward 5 seconds (*Avanzar 5 segundos*) | `L` | |
| ⏭ next track | Next line (*Línea siguiente*) | `Down` | half a second before the next line |
| text icon | Go to just before the first lyrics (*Ir justo antes de la primera letra*) | `F` | 2 s before the first line, to skip the intro |
| speedometer + list | Speed (*Velocidad*) | | 0.5×, 0.75×, 1×, 1.25× (slow it down to place a fast part) |
| speaker + slider | Volume (*Volumen*) | | |
| time | | | position / length of the song |

### Timing: move the lyrics
| Button | Name | Shortcut | What it does |
|---|---|---|---|
| « -250 | Lyrics earlier (*Letra antes*) | `Ctrl+Left` | moves the selected part (or all the lyrics) 250 ms earlier |
| ‹ -50 | Lyrics earlier | `Left` | 50 ms earlier |
| ‹ -10 | Lyrics earlier | `Shift+Left` | 10 ms earlier |
| +10 › | Lyrics later (*Letra después*) | `Shift+Right` | 10 ms later |
| +50 › | Lyrics later | `Right` | 50 ms later |
| +250 » | Lyrics later | `Ctrl+Right` | 250 ms later |
| ✂ Start | Cut start (*Inicio*) | `C` | a new part starts at the line being sung and gets selected: from now on the arrows move only that part (from there to the next cut or to the end) |
| ⏐ End | Cut end (*Fin*) | `V` | the selected part ends just before the line being sung: what comes after does not move |
| ⤙ Join | Join (*Unir*) | | removes the selected cut: the part joins the one before it and takes its shift |
| ↔ All the lyrics | All the lyrics (*Toda la letra*) | `G` | selects the whole song (`#GAP`): the arrows move every part together |
| | previous / next part | `[` / `]` | selects the part before / after (or click it on the line map) |
| ✨ Fit to voice | Fit to voice (*Ajustar a la voz*) | `A` | moves the line being sung, and its part up to the next cut, to where the voice analysis found the singer. Needs *Analyze voice* first |
| 〜 Analyze voice | Analyze voice (*Analizar voz*) | | isolates the voice with Demucs (about 2–3 minutes, once per song; then it is kept next to the song): draws the singer over the notes and colours the line map. SongMaker songs are already analysed (from their original audio; the editor moves it to the converted audio) |
| ↶ Undo | Undo (*Deshacer*) | `Ctrl+Z` | undoes the last change, one step at a time (a whole drag of a note is one step; up to 500 steps) |
| ↷ | Redo (*Rehacer*) | `Ctrl+Y` / `Ctrl+Shift+Z` | does again the change just undone (a new change forgets what was undone) |
| ⤺⤺ | Undo all the changes (*Deshacer todos los cambios*) | | asks first, then goes back to how the song was when the editor opened: timing, cuts, pitches, moved/resized notes, added, deleted and fixed lyrics. `Ctrl+Z` brings everything back |
| 💾 Save | Save (*Guardar*) | `Ctrl+S` | writes the txt (a `.bak` copy of the original txt is kept the first time). Convert the song afterwards so the game gets it |

The label under the buttons shows what the arrows move (all the lyrics, or lines *a–b* and their shift), how many
parts there are, how far the voice of the current line is, and a warning when a moved part would overlap the line
before it (fix it before saving). Parts are saved in steps of one beat of the song (shown there).

### Pitch and length of a note
| Action | Shortcut | What it does |
|---|---|---|
| Drag the selected note | | up / down by semitones, sideways in time, by its edge longer/shorter |
| Note up / down | `Shift+Up` / `Shift+Down` | one semitone up / down (every selected note) |
| Note earlier / later | `Alt+Left` / `Alt+Right` | moves the selected note one beat (several selected: all of them together) |
| Note shorter / longer | `Ctrl+Shift+Left` / `Ctrl+Shift+Right` | one beat shorter / longer (its end moves) |

### Lyrics: fix misspelt words, delete what is not sung
UltraStar songs only. Nothing is written until you save; the grey label of this row shows the selected syllable and
how many notes were deleted / texts fixed.

| Button | Name | Shortcut | What it does |
|---|---|---|---|
| 🗑 Delete syllable | Delete syllable (*Borrar sílaba*) | `Delete` | deletes the selected note's syllable with its notes (also the `~` notes that hold it). Click the note first; with several selected, all of them go |
| row minus | Delete line (*Borrar línea*) | `Ctrl+Delete` | deletes the line being sung (or the selected note's line) with all its notes, after asking |
| I-beam Fix text | Fix text (*Corregir texto*) | `T` | fixes the text of the line being sung (or of the selected note's line); you can also **add** missing syllables (see below) |
| ⑂ Split note | Split note (*Dividir nota*) | `S` | splits the selected note in two (same pitch) and asks for the text of the new half: a syllable that was missing. The note needs 2 beats or more |
| | Fix syllable | double click a note | fixes the text of only that note |

How to write the text:
- *Fix text* shows the line **one piece per note, separated by `|`**, for example `Ca|mi|nan|do `. What you write is
  compared with what was there: a changed piece changes its note; **an added piece splits the note before it** (in
  `Neo|do |kiss` → `Neo|do |ya|kiss` the note of "do" is split in two); a removed piece leaves its note as `~` (or
  delete the note). If the note is too short to split, make it longer first (drag its right edge).
- A **space at the end** of a piece ends the word: `Ca|mi|nan|do ` is one word, `Ca |mi ` are two.
- `~` holds the syllable before (a long note sung over several pitches). An empty piece becomes `~`.

### Sing mode
| Control | Name | What it does |
|---|---|---|
| 🎤 Sing (toggle) | Sing (*Cantar*) | listens to the microphone and draws your voice over the notes like the game: green = on the note, red = off. It counts the notes you hit (any octave counts, like the game) and the % on pitch. Use headphones so the microphone does not hear the song |
| microphone list | | which microphone to use |
| ms box | Mic delay (*Retardo del micro*) | how late the microphone hears you (default 100 ms); raise it if your voice is drawn after the notes |

### Closing
If there are unsaved changes, closing asks: **Yes** saves, **No** discards them, **Cancel** goes back to the editor.

## Requirements
- Windows 7+, or Linux with Wine (see [README_Linux.md](README_Linux.md))
- [ffmpeg](https://ffmpeg.org/download.html) - I used version [7.1.1-full_build from gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
- [RAD Video Tools](https://www.radgametools.com/bnkdown.htm) (**needed only for Let's Sing 2024+**)

## How to use
**Linux:** install it as in [README_Linux.md](README_Linux.md), then open the program with `./start_linux.sh` from the
project folder (or run `bash install_linux_launcher.sh` once to get it in the applications menu). Daily use on Linux, the menu launcher and long background tasks:
[`docs/08_USO_EN_LINUX.md`](docs/08_USO_EN_LINUX.md).

See the [Guide document](Guide.md) for a detailed step-by-step guide on how to use this converter and patch your DLC with custom songs.

This converter can also be run from the command line by using the `--cli` flag, use the `--help` flag for a quick rundown of available options.

## Creative Liberties
_Not mandatory reading:_
1. Some songs contain too many "F" (freestyle) notes, these notes seem mostly intended for rapping sections of songs and
   aren't scored. This is probably because rapping at a consistent pitch isn't possible so UltraStar apps just ignore them.
   This makes singing songs like Linkin Park's In The End a real snooze fest.
   <br> Let's Sing does support rapping though, every note with a pitch of 1 is considered a rap note. The pitch is ignored
   for these notes and only the timing matters. This is why the converter considers all "F" notes to be "R" (rap) notes.
2. Song previews (~30s soundbites) are automatically cut from the songs starting at 60 seconds into the song (where most medleys start)
   unless there are medley tags in the text file. 
3. Some songs don't have videos, either because the uploader didn't put them, or the songs never had videos to begin with.
   The converter makes a static video from the provided cover art in these cases. 
4. Silence is added at the start of a song if it has a positive #VIDEOGAP tag in the text file (cropped if the gap is
   negative) in order to sync the audio with the video and lyrics. 
5. Some songs are way quiter/louder than others, the converter will use ffmpeg to normalize loudness.

## Recent Updates
- **Multi-language Support:** The GUI now features full i18n support. Simply place translation files in the `locales/` directory (e.g. `es.json`) and switch the language instantly in the top menu.
- **Linux & Wine Support:** Cross-platform improvements mean you can now run this flawlessly on Linux using Python and Wine to execute Windows dependencies (like RAD Video Tools).
- **Automated Media Copying:** When extending DLCs, you can now seamlessly copy all media files (Videos, Audio, Covers) from your base JSON's `Songs/` folder directly to the `Output/` patch with visual progress logs. 
- **New songs:** download with usdb_syncer, tick *Only pending* → *Check all visible* → *Convert checked*, then section 5 → *Update the patch on the Switch*. Step by step: `docs/12_CANCIONES_NUEVAS.md`.
- **Library tools:** section 5 of the window ("Advanced options: library tools") runs the maintenance tools of `tools/` in the background: patch check, Switch update over MTP, voice sync scan, covers, years, genres and singers' gender. See `docs/11_GUIA_DE_PRUEBAS.md`.
