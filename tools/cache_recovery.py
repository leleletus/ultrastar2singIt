import os
import shutil
import unicodedata
from pathlib import Path

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def construct_name_id(dir_long: str) -> str:
    parts = dir_long.split(' - ')
    if len(parts) < 2: 
        return ""
    art_cap = ''.join(word[0].upper() for word in strip_accents(parts[0]).split())
    tit_low = ''.join(e.lower() for e in strip_accents(parts[1]) if e.isalnum())
    return art_cap + tit_low

def recover_cache(input_dir: str, output_dir: str) -> tuple[int, str]:
    """
    Recovers cached output files from the destination directory back to the input directories.
    Returns (count, message).
    """
    if not input_dir or not output_dir or not os.path.exists(input_dir) or not os.path.exists(output_dir):
        return 0, "Input and Output directories must be set and exist."
        
    dlc_dir = ""
    for root, dirs, files in os.walk(output_dir):
        if "romfs" in dirs:
            dlc_dir = os.path.join(root, "romfs", "Songs")
            break
            
    if not dlc_dir:
        return 0, "Could not find romfs/Songs in output directory. Nothing to recover."

    count = 0
    extensions_to_recover = [
        ("videos", ".bk2"), 
        ("videos", ".mp4"), 
        ("audio", ".ogg"), 
        ("audio_preview", "_preview.ogg"), 
        ("covers", ".png"), 
        ("vxla", ".vxla")
    ]
    
    for d in os.listdir(input_dir):
        d_path = os.path.join(input_dir, d)
        if os.path.isdir(d_path) and " - " in d:
            name_id = construct_name_id(d)
            if not name_id: 
                continue
                
            for sub_dir, ext in extensions_to_recover:
                src = os.path.join(dlc_dir, sub_dir, name_id + ext)
                dest = os.path.join(d_path, name_id + ext)
                if os.path.exists(src):
                    try:
                        shutil.copy2(src, dest)
                        count += 1
                    except Exception as e:
                        pass # Ignore individual file permission errors
                        
    return count, f"Recovered {count} files successfully!"
