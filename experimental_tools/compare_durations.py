import os
import subprocess
import json

def get_duration(file_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0

custom_dir = "/run/media/djvemo/EADE-F56A/songs_custom"
differences = []
perfect_matches = 0
total_checked = 0

for root, dirs, files in os.walk(custom_dir):
    m4a_files = [f for f in files if f.lower().endswith('.m4a')]
    ogg_files = [f for f in files if f.lower().endswith('.ogg')]
    
    if m4a_files and ogg_files:
        m4a_path = os.path.join(root, m4a_files[0])
        ogg_path = os.path.join(root, ogg_files[0])
        
        # Only check OGG files that were already converted
        dur_m4a = get_duration(m4a_path)
        dur_ogg = get_duration(ogg_path)
        
        if dur_m4a > 0 and dur_ogg > 0:
            total_checked += 1
            diff = abs(dur_m4a - dur_ogg)
            if diff > 0.005:  # more than 5 milliseconds difference
                differences.append({
                    "song": os.path.basename(root),
                    "m4a": dur_m4a,
                    "ogg": dur_ogg,
                    "diff_ms": round(diff * 1000, 2)
                })
            else:
                perfect_matches += 1

# Sort by biggest difference
differences.sort(key=lambda x: x["diff_ms"], reverse=True)

print(f"Total compared: {total_checked}")
print(f"Perfect matches: {perfect_matches}")
print(f"Differences found: {len(differences)}")
if differences:
    print("\nTop 15 worst desyncs:")
    for d in differences[:15]:
        print(f" - {d['song']}: desync of {d['diff_ms']} ms")

