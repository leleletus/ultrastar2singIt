import os
import sys

sys.path.append('/home/djvemo/ultrastar_official')
from UltrastarToSingit import parse_file, map_data

custom_dir = "/run/media/djvemo/EADE-F56A/songs_custom"
txt_files = []
for d in os.listdir(custom_dir):
    d_path = os.path.join(custom_dir, d)
    if os.path.isdir(d_path):
        for f in os.listdir(d_path):
            if f.endswith(".txt"):
                txt_files.append(os.path.join(d_path, f))
                
test_files = txt_files[:100]

success = 0
golden_count_total = 0
rap_count_total = 0

for txt in test_files:
    try:
        us_data = parse_file(txt)
        orig_pitch_notes = sum(1 for n in us_data["notes"] if n[0] in [':', '*', 'F', 'R', 'G'])
        sing_it = map_data(us_data, 200.0, 36, txt)
        new_notes = len(sing_it["notes"])
        
        if orig_pitch_notes == new_notes:
            success += 1
            
        long_passages = sum(1 for p in sing_it.get("passages", []) if p["value"] == "long")
        speed_passages = sum(1 for p in sing_it.get("passages", []) if p["value"] == "speed")
        
        golden_count_total += long_passages
        rap_count_total += speed_passages
    except: pass

print(f"Total Successful 100% Matches: {success} / 100")
print(f"Golden Notes generated: {golden_count_total}")
print(f"Rap/Freestyle sections generated: {rap_count_total}")
