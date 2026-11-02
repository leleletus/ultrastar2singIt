# UltraStar to Let's Sing Converter - Linux Support

This branch/patch introduces native Linux compatibility via Wine and Python natively!

## Changes Made
1. **Bink Video Conversion (radvideo64.exe) via Wine:**
   - Modified `ConvertFiles.py` to seamlessly wrap RADVideo calls using `wine` when running on Linux (`sys.platform != "win32"`).
   - Automatically translates Unix file paths (e.g., `/home/...`) into Wine-friendly `Z:\home\...` format so `binkc` does not fail with "Syntax Errors".
2. **Dynamic Paths in GUI:**
   - `Gui.py` now intelligently looks for `ffmpeg` at `/usr/bin/ffmpeg` on Linux.
   - It also automatically searches for `radvideo64.exe` inside `$WINEPREFIX/drive_c/Program Files (x86)/RADVideo/`
     (`~/.wine` when `WINEPREFIX` is not set). Another Wine binary can be set with `tools.wine_path` in `config.yml`.
3. **Icons:**
   - The Tabler SVG icons of `pytablericons` are rendered with QtSvg (`GuiElement.py`); its own renderer needs
     pygame/cairo and failed on many Linux systems. Without the package the GUI still works (plain dots).
4. **JSON Fixes:**
   - Fixed a bug where `ConvertFiles.py` generated `songs_int.json` without the `"language": "English"` tag, which caused the Nintendo Switch game to crash internally on load.

## Requirements for Linux Users
To run the converter perfectly on Linux, users need the following dependencies installed:
```bash
# 1. Install system dependencies (Arch Linux example)
sudo pacman -S wine wine-gecko wine-mono gst-plugins-good ffmpeg

# Note: gst-plugins-good is CRITICAL! 
# Without it, Wine's internal winegstreamer cannot decode .mp4/.avi natively, 
# and radvideo64.exe will silently fail and produce empty 800-byte .bk2 files!

# 2. Install RAD Video Tools inside Wine
wget http://www.radgametools.com/down/Bink/RADTools.exe
wine RADTools.exe

# 3. Get the project and set up the Python venv (inside the project folder: start_linux.sh uses ./venv)
git clone -b linux-wine-support https://github.com/leleletus/ultrastar2singIt.git
cd ultrastar2singIt
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# optional, several GB: voice analysis of the sync editor / sync check (Demucs) and the "slow" pitch method
# pip install -r requirements-slow.txt
python3 LetsSingUltraStarConverter.py
```

Optional tools: `yt-dlp` (Add a video from a YouTube link; also found inside usdb_syncer's pipx install),
KDE's `kioclient` and DBI on the Switch (Update the patch on the Switch over MTP).

## Opening it every day
```
./start_linux.sh                 # open the program (from the project folder; any folder works with its full path)
bash install_linux_launcher.sh   # once: adds it to the applications menu (KDE, GNOME...)
```
More in [`docs/08_USO_EN_LINUX.md`](docs/08_USO_EN_LINUX.md).
