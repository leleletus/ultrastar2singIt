import os
import json
import shutil
import xml.etree.ElementTree as ET

WORKSPACE_DIR = "/run/media/djvemo/EADE-F56A/lets_sing_workspace"
MEGAPACK_DIR = os.path.join(WORKSPACE_DIR, "megapack_completo")
OUTPUT_DIR = "/run/media/djvemo/EADE-F56A/songs_custom"
EXTRACTED_DIR = os.path.join(WORKSPACE_DIR, "extracted")

BPM = 300
MULTIPLIER = (BPM * 4) / 60.0

def seconds_to_beats(sec):
    return int(round(sec * MULTIPLIER))

def clean_lyric(lyric):
    lyric = lyric.replace("#h", "")
    lyric = lyric.replace("#g5", "")
    return lyric

def get_lyrics_spaces(vxla_root):
    spaces = []
    for layer in vxla_root.findall('IntervalLayer'):
        if layer.get('name') == 'lyrics':
            for interval in layer.findall('Interval'):
                val = interval.get('value', '')
                t1 = float(interval.get('t1'))
                t2 = float(interval.get('t2'))
                spaces.append({'t1': t1, 't2': t2, 'val': val})
    return spaces

def check_space_after(t2, lyrics_data):
    for l in lyrics_data:
        if abs(l['t2'] - t2) < 0.1:
            if l['val'].endswith(' '): return True
            if l['val'].endswith('-') and not l['val'].endswith(' '): return False
    return False

def check_space_before(t1, lyrics_data):
    for l in lyrics_data:
        if abs(l['t1'] - t1) < 0.1:
            if l['val'].startswith(' '): return True
    return False

def build_metadata_db():
    db = {}
    for root, dirs, files in os.walk(EXTRACTED_DIR):
        for f in files:
            if f.endswith('.json') and f.startswith('songs_'):
                try:
                    with open(os.path.join(root, f), 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                        for song in data.get('songs', []):
                            sid = str(song.get('id'))
                            db[sid] = {
                                'artist': song.get('artist', 'Unknown Artist'),
                                'title': song.get('title', 'Unknown Title'),
                                'year': str(song.get('year', ''))
                            }
                except: pass
            elif f.endswith('_meta.xml'):
                try:
                    # Fix encoding issues for parsing
                    with open(os.path.join(root, f), 'rb') as xf:
                        raw = xf.read()
                    try: raw = raw.decode('utf-8-sig')
                    except: raw = raw.decode('latin-1')
                    raw = raw.replace('encoding="utf-16"', 'encoding="utf-8"').replace('encoding="UTF-16"', 'encoding="utf-8"')
                    tree = ET.ElementTree(ET.fromstring(raw))
                    rt = tree.getroot()
                    sid_el = rt.find('Id')
                    artist_el = rt.find('Artist')
                    title_el = rt.find('Title')
                    year_el = rt.find('Year')
                    if sid_el is not None:
                        sid = sid_el.text.strip() if sid_el.text else ''
                        artist = artist_el.text.strip() if (artist_el is not None and artist_el.text) else 'Unknown Artist'
                        title = title_el.text.strip() if (title_el is not None and title_el.text) else 'Unknown Title'
                        year = year_el.text.strip() if (year_el is not None and year_el.text) else ''
                        db[sid] = {'artist': artist, 'title': title, 'year': year}
                except: pass
    return db

def convert_vxla_to_txt(vxla_file, song_id, meta, output_folder):
    try:
        with open(vxla_file, 'rb') as xf:
            raw = xf.read()
        try: raw = raw.decode('utf-8-sig')
        except: raw = raw.decode('latin-1')
        raw = raw.replace('encoding="utf-16"', 'encoding="utf-8"').replace('encoding="UTF-16"', 'encoding="utf-8"')
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"Error parsing {vxla_file}: {e}")
        return False
    
    notes_layer = None
    passages_layer = None
    pages_layer = None
    for layer in root.findall('IntervalLayer'):
        if layer.get('name') == 'pages':
            pages_layer = layer
        if layer.get('name') == 'notes_full':
            notes_layer = layer
        elif layer.get('name') == 'notes' and notes_layer is None:
            notes_layer = layer
        elif layer.get('name') == 'passages':
            passages_layer = layer
            
    if notes_layer is None:
        return False
        
    lyrics_data = get_lyrics_spaces(root)
        
    title = meta.get('title', song_id)
    artist = meta.get('artist', 'Unknown Artist')
    year = meta.get('year', '')
    
    os.makedirs(output_folder, exist_ok=True)
    safe_artist = "".join(c for c in artist if c.isalnum() or c in " -_")
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")
    
    txt_path = os.path.join(output_folder, f"{safe_artist} - {safe_title}.txt")
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"#TITLE:{title}\n")
        f.write(f"#ARTIST:{artist}\n")
        f.write(f"#YEAR:{year}\n")
        f.write(f"#BPM:{BPM}\n")
        
        ogg_src = os.path.join(MEGAPACK_DIR, "Songs", "audio", f"{song_id}.ogg")
        if os.path.exists(ogg_src):
            f.write(f"#MP3:{song_id}.ogg\n")
            shutil.copy2(ogg_src, os.path.join(output_folder, f"{song_id}.ogg"))
            
        # Check for multiple video extensions
        video_found = False
        for ext in ['.mp4', '.webm', '.bik']:
            vid_src = os.path.join(MEGAPACK_DIR, "Songs", "videos", f"{song_id}{ext}")
            if os.path.exists(vid_src):
                f.write(f"#VIDEO:{song_id}{ext}\n")
                shutil.copy2(vid_src, os.path.join(output_folder, f"{song_id}{ext}"))
                video_found = True
                break
        
        # Check covers too
        for ext in ['.jpg', '.png']:
            cov_src = os.path.join(MEGAPACK_DIR, "Songs", "covers", f"{song_id}{ext}")
            if os.path.exists(cov_src):
                f.write(f"#COVER:{song_id}{ext}\n")
                shutil.copy2(cov_src, os.path.join(output_folder, f"{song_id}{ext}"))
                break
            
        last_t2 = 0
        for interval in notes_layer.findall('Interval'):
            t1 = float(interval.get('t1'))
            t2 = float(interval.get('t2'))
            val = interval.get('value')
            
            if val.startswith("#p") and "#." in val:
                pitch_str, lyric = val.split("#.", 1)
                pitch = int(pitch_str[2:])
                us_pitch = pitch - 36
                
                lyric = clean_lyric(lyric)
                
                if lyric == "-":
                    lyric = "~"
                else:
                    if check_space_after(t2, lyrics_data): lyric += " "
                    if check_space_before(t1, lyrics_data): lyric = " " + lyric
                        
                start_beat = seconds_to_beats(t1)
                duration = seconds_to_beats(t2) - start_beat
                if duration <= 0: duration = 1
                    
                if pages_layer is not None:
                    # check if this note's t1 is after the end of the page that last_t2 belonged to
                    for p in pages_layer.findall('Interval'):
                        pt2 = float(p.get('t2'))
                        if last_t2 <= pt2 and t1 >= pt2:
                            # We crossed a page boundary!
                            f.write(f"- {seconds_to_beats(pt2)}\n")
                            break
                elif start_beat > seconds_to_beats(last_t2) + 20:
                    # Fallback if no pages layer
                    f.write(f"- {seconds_to_beats(last_t2)}\n")
                    
                is_freestyle = False
                if passages_layer is not None:
                    for p in passages_layer.findall('Interval'):
                        pt1 = float(p.get('t1'))
                        pt2 = float(p.get('t2'))
                        pval = p.get('value')
                        if pval == "speed" and pt1 <= t1 and pt2 >= t2:
                            is_freestyle = True
                            
                note_char = "F" if is_freestyle else ":"
                f.write(f"{note_char} {start_beat} {duration} {us_pitch} {lyric}\n")
                last_t2 = t2
                
        f.write("E\n")
    return True

def main():
    print("Building metadata database from official extracted files...")
    meta_db = build_metadata_db()
    print(f"Loaded metadata for {len(meta_db)} songs.")
    
    # Fallback to songs_database.json if not found in extracted
    db_json_path = os.path.join(WORKSPACE_DIR, "songs_database.json")
    if os.path.exists(db_json_path):
        with open(db_json_path, 'r', encoding='utf-8') as f:
            for s in json.load(f):
                sid = s.get('id')
                if sid not in meta_db:
                    # Attempt heuristic artist extraction
                    title_raw = s.get('title', sid)
                    parts = title_raw.split(' - ')
                    if len(parts) == 2:
                        meta_db[sid] = {'artist': parts[0].strip(), 'title': parts[1].strip(), 'year': ''}
                    else:
                        meta_db[sid] = {'artist': 'Unknown Artist', 'title': title_raw, 'year': ''}

    json_path = os.path.join(MEGAPACK_DIR, "songs_int_combined.json")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"Reconstructing {len(data.get('songs', []))} songs...")
    success_count = 0
    
    for s_obj in data.get("songs", []):
        song_id = s_obj.get('id')
        vxla_file = os.path.join(MEGAPACK_DIR, "Songs", "vxla", f"{song_id}.vxla")
        if os.path.exists(vxla_file):
            meta = {
                'artist': s_obj.get('artist', 'Unknown'),
                'title': s_obj.get('title', song_id),
                'year': s_obj.get('year', '')
            }
            
            safe_artist = "".join(c for c in meta['artist'] if c.isalnum() or c in " -_")
            safe_title = "".join(c for c in meta['title'] if c.isalnum() or c in " -_")
            out_folder = os.path.join(OUTPUT_DIR, f"{safe_artist} - {safe_title}")
            
            success = convert_vxla_to_txt(vxla_file, song_id, meta, out_folder)
            if success:
                success_count += 1
                
    print(f"Done! Reconstructed {success_count} songs into {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
