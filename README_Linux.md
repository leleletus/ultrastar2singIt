# UltraStar to Let's Sing Converter - Linux Support

This branch/patch introduces native Linux compatibility via Wine and Python natively!

## Changes Made
1. **Bink Video Conversion (radvideo64.exe) via Wine:**
   - Modified `ConvertFiles.py` to seamlessly wrap RADVideo calls using `wine` when running on Linux (`sys.platform != "win32"`).
   - Automatically translates Unix file paths (e.g., `/home/...`) into Wine-friendly `Z:\home\...` format so `binkc` does not fail with "Syntax Errors".
2. **Dynamic Paths in GUI:**
   - `Gui.py` now intelligently looks for `ffmpeg` at `/usr/bin/ffmpeg` on Linux.
   - It also automatically searches for `radvideo64.exe` inside `~/.wine/drive_c/Program Files (x86)/RADVideo/`.
3. **Replaced pytablericons with Pillow (PIL):**
   - Removed the `pytablericons` dependency in `GuiElement.py` and replaced it with native `ImageDraw` shapes. `pytablericons` often crashed on Linux environments due to missing font or cairo rendering dependencies. Pillow makes the GUI completely cross-platform and more stable.
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

# 3. Setup Python venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 LetsSingUltraStarConverter.py
```
