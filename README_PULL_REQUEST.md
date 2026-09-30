# Pull Request & README Updates para Ultrastar2SingIt (FORK VERSION)

Este documento contiene la versión final, detallada y exhaustiva del Pull Request y del README. Como el autor original no suele contestar, esta documentación está preparada para que sea la **página principal de tu propio Fork** (tu versión oficial de Ultrastar2SingIt).

---

## 1. Plantilla para el Pull Request (GitHub)

**Title:** `feat: Massive Overhaul - Sync Editor, UI Tools, Linux Wine Support, Multithreading & Stability`

**Description:**
This PR transforms the repository into a fully stable, cross-platform powerhouse. It introduces a visual Sync Editor, UI enhancements (real-time search, 3-state sorting, cache recovery), comprehensive Linux/Wine support, and fixes massive critical bugs in the core conversion logic.

### 🌟 UI & Quality of Life Features
* **Built-in Visual Sync Editor (`SyncEditor.py`)**: Added a "Fix Sync" button that opens a PySide6 media player. It simultaneously plays the `#VIDEO` and `#MP3` tracks while rendering the lyrics in real-time. Features a slider and +/- 50ms buttons to dynamically adjust the `#GAP`.
* **Real-time Search Filter**: Added a search bar to instantly filter hundreds of songs. Using `setRowHidden`, it maintains selection states even when clearing the search.
* **3-State Sorting**: Added custom column sorting (A->Z, Z->A, Original Order) without losing the initial filesystem chronological loading order.
* **Tools Menu (Recovery & Unpack)**:
  * **Recover Cache**: If output files were accidentally deleted from the input directory via the UI, this script automatically recovers the `.bk2`, `.ogg`, `.png`, and `.vxla` files directly from the output directory.
  * **Unpack Output**: Reverse-engineers a Let's Sing DLC output folder back into a standard UltraStar directory so it can be re-converted or edited.

### 🐛 Core Bug Fixes & Stability Improvements
* **Wine Binkc Unicode Fix**: Running `binkc.exe` via Wine crashes on special characters (like apostrophes in "Hips Don't Lie" or `[DUET]`). The pipeline now temporarily copies problematic files to `/tmp/`, processes them with ASCII names, and copies them back, ensuring a 100% success rate.
* **FFmpeg Multithreading Collision**: Fixed FFmpeg threads overwriting each other's passlog files by implementing UUIDs (`passlogfile_{uuid}`).
* **`#VIDEO` Tag Prioritization**: Strictly parses the `#VIDEO:` tag instead of picking the first alphabetical `.mp4`.
* **AI Pitch Correction (`crepe`) Fixes**: Bypassed `viterbi=True` decoding to prevent crashes on modern Python (3.14/numpy 2.0).
* **Aggressive Cancellation**: Added `pkill` handling for Linux users. Pressing "Stop" now forcefully terminates running background processes.

---

## 2. Nuevo contenido para tu archivo `README.md` (Para tu Fork)

```markdown
# Ultrastar to Let's Sing Converter (Enhanced Fork)

A powerful, robust Python tool designed to convert UltraStar karaoke formats (`.txt` + media) into Nintendo Switch *Let's Sing* formats (JSON/XML + `.bk2` videos).

This fork brings massive stability improvements, a visual Sync Editor, Linux native compatibility, and essential UI tools for power users with libraries of 300+ songs.

## ✨ Features & Capabilities

### 🎛️ The Visual Sync Editor (Fix Sync)
Tired of converting a song, loading it in-game, and realizing the lyrics are out of sync?
- **Real-Time Preview**: Click "Fix Sync" to open a dual-player (Video + Audio) that renders lyrics exactly as they will appear in-game.
- **Dynamic #GAP Adjustment**: Use the visual slider or the "+50ms / -50ms" buttons to shift the lyrics. The changes are saved instantly to your `.txt` file.
- **Progressive Highlighting**: Lyrics light up word-by-word just like the actual game.

### 🧠 AI Pitch Correction & Analysis
- **Pitch Fixing**: Automatically analyzes the original song's vocals using TensorFlow (CREPE algorithm). It calculates the exact pitch offset needed so you hit the right notes in-game without false positives.
- **Genius API Integration**: The tool intelligently scrapes Genius.com to detect chorus sections and medley tags for perfect song structure.

### 🚀 Multithreaded Processing
- Convert multiple songs simultaneously. 
- *Note on expected behavior*: You might see multiple console windows open briefly. Usually, it balances to `N-1` active encoding windows because one thread is typically handling invisible background tasks (like downloading Genius lyrics or running AI Pitch analysis).

### 🧰 Power-User UI Tools
- **Real-Time Search Bar**: Filter through hundreds of songs instantly without losing your current selections.
- **Smart Sorting**: Click column headers to sort (A-Z, Z-A, and a third click to return to original filesystem order).
- **Cache Recovery**: Accidentally cleared your generated files? Use `Tools > Recover Cache` to restore them from the output directory instantly.
- **Unpack Let's Sing Files**: Have a Let's Sing DLC folder but lost the original UltraStar files? Use `Tools > Unpack/Reverse` to extract the video, audio, and cover art back into an UltraStar format.

---

## 🐧 Linux Installation & Compatibility

Running this converter on Linux requires Python 3.x and **Wine** (to run the Windows-only RAD Video Tools `binkc` encoder).

### 1. System Requirements & Dependencies
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv wine ffmpeg
```

### 2. Setup the Python Environment
```bash
git clone https://github.com/YOUR_USERNAME/ultrastar2singIt.git
cd ultrastar2singIt
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
*(If AI Pitch correction fails on modern Linux, install `pip install tf-nightly tf-nightly-cpu`)*

### 3. Installing RAD Video Tools
1. Download **RAD Video Tools** (Windows `.exe`).
2. Run via Wine: `wine radtools.exe`
3. In the GUI, point the RAD path to: `~/.wine/drive_c/Program Files (x86)/RADVideo/radvideo64.exe`

### 4. Running the Application
```bash
python Gui.py
```
*(Wayland Users: If you get a white screen, run: `QT_QPA_PLATFORM=xcb python Gui.py`)*

## 📚 General Workflow
1. Add your UltraStar song folders (they must follow the `Artist - Title` naming convention) to your `Input` folder.
2. Select your `Output` folder.
3. Configure your core/DLC info (USDB compatibility allows generating valid structures for custom games).
4. **Fix Sync**: Check any song with a yellow warning (⚠️) using the Sync Editor.
5. Hit **Start Conversion** and let the multithreading engine do the heavy lifting!

## 🔮 Future Implementations (Roadmap)
- Fully automated AI Desync Detector (Offline tool using Demucs/Crepe to flag the 1% of songs with bad timing without human intervention).
- Expanded USDB fetching capabilities.
```
