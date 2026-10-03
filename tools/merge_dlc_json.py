import os
import sys
import json
import xml.etree.ElementTree as ET
import glob

EXTRACTED_DIR = "/run/media/djvemo/EADE-F56A/lets_sing_workspace/extracted"
MEGAPACK_DIR = "/run/media/djvemo/EADE-F56A/lets_sing_workspace/megapack_completo"

def get_all_megapack_metadata():
    db = {}
    for root, dirs, files in os.walk(EXTRACTED_DIR):
        for f in files:
            if f.endswith('.json') and f.startswith('songs_'):
                try:
                    with open(os.path.join(root, f), 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                        for song in data.get('songs', []):
                            sid = str(song.get('id'))
                            db[sid] = song
                except: pass

    for root, dirs, files in os.walk(EXTRACTED_DIR):
        for f in files:
            if f.endswith('_meta.xml'):
                try:
                    with open(os.path.join(root, f), 'rb') as xf:
                        raw = xf.read()
                    try: raw = raw.decode('utf-8-sig')
                    except: raw = raw.decode('latin-1')
                    raw = raw.replace('encoding="utf-16"', 'encoding="utf-8"').replace('encoding="UTF-16"', 'encoding="utf-8"')
                    tree = ET.ElementTree(ET.fromstring(raw))
                    rt = tree.getroot()
                    sid_el = rt.find('Id')
                    if sid_el is not None and sid_el.text:
                        sid = sid_el.text.strip()
                        if sid not in db:
                            artist = rt.find('Artist')
                            title = rt.find('Title')
                            year = rt.find('Year')
                            db[sid] = {
                                'id': sid,
                                'artist': artist.text.strip() if artist is not None and artist.text else 'Unknown',
                                'title': title.text.strip() if title is not None and title.text else sid,
                                'year': int(year.text.strip()) if year is not None and year.text and year.text.isdigit() else 2020,
                                'gender': 'Women',
                                'language': 'English',
                                'difficulty': 'Normal'
                            }
                except: pass
    return db

with open(os.path.join(MEGAPACK_DIR, "todas_las_canciones.json"), 'r', encoding='utf-8') as f:
    megapack_ids = json.load(f).get("selected_songs", [])

meta_db = get_all_megapack_metadata()

# Find the DLC JSON dynamically
user_dlc_json = ""
for root, dirs, files in os.walk("/home/djvemo/Desktop"):
    if "songs_int.json" in files:
        user_dlc_json = os.path.join(root, "songs_int.json")
        break

if not user_dlc_json:
    print("Could not find songs_int.json on Desktop")
    sys.exit(1)

print(f"Found DLC json: {user_dlc_json}")
with open(user_dlc_json, 'r', encoding='utf-8') as f:
    dlc_data = json.load(f)

added = 0
for sid in megapack_ids:
    if any(s.get('id') == sid for s in dlc_data.get("songs", [])):
        continue
    
    song_obj = meta_db.get(sid)
    if not song_obj:
        song_obj = {
            "id": sid,
            "artist": "Unknown Artist",
            "title": sid,
            "year": 2020,
            "gender": "Women",
            "language": "English",
            "difficulty": "Normal"
        }
    
    dlc_data["songs"].append(song_obj)
    added += 1

out_path = "/home/djvemo/Desktop/songs_int_combined.json"
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(dlc_data, f, indent=4, ensure_ascii=False)

print(f"Added {added} Megapack songs to {out_path}!")
