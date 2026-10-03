import os
from pathlib import Path

custom_dir = Path("/run/media/djvemo/EADE-F56A/songs_custom")
output_audio_dir = Path("/run/media/djvemo/EADE-F56A/output/0100EE4020D19003/romfs/Songs/audio")

deleted_count = 0

for d in custom_dir.iterdir():
    if not d.is_dir():
        continue
        
    txt_files = [f for f in d.iterdir() if f.suffix.lower() in ['.txt'] and not f.name.endswith('.vxla')]
    if not txt_files:
        continue
        
    original_audio = ""
    with open(txt_files[-1], 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('#MP3:'):
                original_audio = line.strip().split(':', 1)[1]
                break
                
    for f in d.iterdir():
        if f.suffix.lower() == '.ogg':
            if f.name == original_audio:
                continue
            
            os.remove(f)
            deleted_count += 1
            
            out_file = output_audio_dir / f.name
            if out_file.exists():
                os.remove(out_file)

print(f"Deleted {deleted_count} generated .ogg files. Original audio files were kept safe.")
