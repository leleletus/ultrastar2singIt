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
Detailed technical notes, bug list, regressions and work log (in Spanish) are in [`docs/`](docs/README.md).

**Your converted videos are safe.** Encoding a `.bk2` can take hours, so the converter never deletes or re-encodes one:
"Clear cache" keeps them (double confirmation), a failed encode never replaces a good file, and before the output
folder is cleared any video without a copy in its song folder is rescued.

**Sync editor** (right click on a song → *Fix sync…*), a small video editor for the lyrics:
- video, the notes as bars like the game and karaoke lyrics; play/pause, ±5 s, ±0.1 s, previous/next line,
  jump to the first lyrics, speed 0.5×–1.25×, a timeline you can click, keyboard shortcuts on every button;
- move all the lyrics (`#GAP`) or **cut** the song into parts (cut start / cut end) and move one part without
  touching the others (a gap in the middle of the song); the selected part stays selected while you move around
  the song; a `.bak` of the txt is kept the first time a song is saved;
- **Analyze voice**: the singer is isolated (Demucs) and drawn over the notes; a map colours every line by how well
  it matches the voice and *Fit to voice* moves a part to where the singer really is;
- **Sing mode**: listens to the microphone, draws your voice over the notes and counts the notes you hit (any
  octave, like the game) to check that the pitch of a song is right;
- songs that use an official Let's Sing lyrics file are shown read-only (the game uses their timing as is).

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

**GUI**: fast song table with per-song status, convert only the checked songs or a single one, coloured log,
settings remembered, full Spanish translation. Tests: `python -m unittest discover -s tests -t .`

## Requirements
- Windows 7+
- [ffmpeg](https://ffmpeg.org/download.html) - I used version [7.1.1-full_build from gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
- [RAD Video Tools](https://www.radgametools.com/bnkdown.htm) (**needed only for Let's Sing 2024+**)

## How to use
**Linux:** open the program with `~/ultrastar_official/start_linux.sh` (or run `bash install_linux_launcher.sh`
once to get it in the applications menu). Daily use on Linux, the menu launcher and long background tasks:
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
- **Experimental Tools:** Check out the `experimental_tools/` directory for extra scripts, including `fix_dlc_artists_metadata.py`, a robust tool that fixes "Unknown Artist" entries in your large Let's Sing Megapack JSONs using a combination of known hardcoded DLC fixes and iTunes API multi-threaded lookups.
