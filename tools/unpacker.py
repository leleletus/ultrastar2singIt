import os
import shutil
from pathlib import Path

def unpack_dlc(songs_dir: str, input_dir: str) -> tuple[int, str]:
    """
    Unpacks a Let's Sing 'Songs' DLC output directory back into UltraStar format in the input_dir.
    Returns (extracted_count, message).
    """
    if not songs_dir or not songs_dir.endswith("Songs"):
        return 0, "You must select a folder named 'Songs' (from romfs/Songs)."
        
    if not input_dir or not os.path.exists(input_dir):
        return 0, "Your main Input folder must be set and exist."

    videos_dir = os.path.join(songs_dir, "videos")
    if not os.path.exists(videos_dir):
        return 0, "No 'videos' subfolder found in the selected DLC."

    extracted = 0
    for f in os.listdir(videos_dir):
        if f.endswith(".bk2") or f.endswith(".mp4"):
            base_name = f.split(".")[0]
            
            # Recreate an UltraStar-like folder structure
            new_folder = os.path.join(input_dir, f"Unknown Artist - {base_name}")
            os.makedirs(new_folder, exist_ok=True)
            
            # 1. Copy video
            ext = ".bk2" if f.endswith(".bk2") else ".mp4"
            try:
                shutil.copy2(os.path.join(videos_dir, f), os.path.join(new_folder, f"{base_name}{ext}"))
            except Exception:
                pass
            
            # 2. Copy audio
            audio_path = os.path.join(songs_dir, "audio", f"{base_name}.ogg")
            if os.path.exists(audio_path): 
                try: shutil.copy2(audio_path, os.path.join(new_folder, f"{base_name}.ogg"))
                except Exception: pass
            
            # 3. Copy cover
            cover_path = os.path.join(songs_dir, "covers", f"{base_name}.png")
            if os.path.exists(cover_path): 
                try: shutil.copy2(cover_path, os.path.join(new_folder, f"{base_name}.png"))
                except Exception: pass
            
            # 4. Generate basic UltraStar .txt
            txt_path = os.path.join(new_folder, f"{base_name}.txt")
            if not os.path.exists(txt_path):
                with open(txt_path, "w", encoding="utf-8") as txt:
                    txt.write(f"#TITLE:{base_name}\n#ARTIST:Unknown\n#BPM:120\n#GAP:0\n*\t0\t10\t0\tUnpacked\nE\n")
            
            extracted += 1
            
    return extracted, f"Successfully extracted {extracted} songs into {input_dir}. Please rename the folders manually to 'Artist - Title'."
