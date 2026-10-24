"""Rebuilds UltraStar songs from the vxla files of a Let's Sing megapack.

Usage: python tools/reverse_vxla.py <lets_sing_workspace> <songs folder>
Songs whose folder already exists are never touched.
"""
import argparse
import os
import json
import shutil
import xml.etree.ElementTree as ET

# set from the command line in main()
WORKSPACE_DIR = MEGAPACK_DIR = OUTPUT_DIR = EXTRACTED_DIR = None

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
        f.write("#LETSSINGPITCHOFFSET:36\n")

        # sources get generic names: the official song ID is usually the converter's ID too, and files named
        # <id>.ogg/.mp4/.png would be taken for already converted ones
        ogg_src = os.path.join(MEGAPACK_DIR, "Songs", "audio", f"{song_id}.ogg")
        if os.path.exists(ogg_src):
            f.write("#MP3:audio.ogg\n")
            shutil.copy2(ogg_src, os.path.join(output_folder, "audio.ogg"))
            
        # Check for multiple video extensions
        video_found = False
        for ext in ['.mp4', '.webm', '.bk2', '.bik']:
            vid_src = os.path.join(MEGAPACK_DIR, "Songs", "videos", f"{song_id}{ext}")
            if os.path.exists(vid_src):
                f.write(f"#VIDEO:video{ext}\n")
                shutil.copy2(vid_src, os.path.join(output_folder, f"video{ext}"))
                video_found = True
                break
        
        # Check covers too
        for ext in ['.jpg', '.png']:
            cov_src = os.path.join(MEGAPACK_DIR, "Songs", "covers", f"{song_id}{ext}")
            if os.path.exists(cov_src):
                f.write(f"#COVER:cover{ext}\n")
                shutil.copy2(cov_src, os.path.join(output_folder, f"cover{ext}"))
                break
            
        # Extract all lyrics for old format
        lyrics_map = {}
        for layer in root.findall('IntervalLayer'):
            if layer.get('name') == 'lyrics':
                for interval in layer.findall('Interval'):
                    lyrics_map[float(interval.get('t1'))] = interval.get('value', '~')

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
            else:
                # Old format: val is just pitch like "59"
                try: pitch = int(val)
                except: continue
                us_pitch = pitch - 36
                lyric = clean_lyric(lyrics_map.get(t1, "~"))
                
            # Now process spaces for BOTH formats
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
    global WORKSPACE_DIR, MEGAPACK_DIR, OUTPUT_DIR, EXTRACTED_DIR
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('workspace', help="folder with megapack_completo/ and extracted/")
    parser.add_argument('songs', help="songs folder to write the rebuilt songs to")
    args = parser.parse_args()
    WORKSPACE_DIR = args.workspace
    MEGAPACK_DIR = os.path.join(WORKSPACE_DIR, "megapack_completo")
    EXTRACTED_DIR = os.path.join(WORKSPACE_DIR, "extracted")
    OUTPUT_DIR = args.songs

    print("Building metadata database from official extracted files...")
    meta_db = build_metadata_db()
    print(f"Loaded metadata for {len(meta_db)} songs.")
    
    combined_json_path = os.path.join(MEGAPACK_DIR, "songs_int_combined.json")
    if os.path.exists(combined_json_path):
        with open(combined_json_path, 'r', encoding='utf-8') as f:
            import json
            data = json.load(f)
            for s in data.get('songs', []):
                sid = str(s.get('id'))
                if sid not in meta_db or meta_db[sid].get('artist') == 'Unknown Artist':
                    meta_db[sid] = {
                        'artist': s.get('artist', 'Unknown Artist'),
                        'title': s.get('title', sid),
                        'year': str(s.get('year', ''))
                    }

    vxla_dir = os.path.join(MEGAPACK_DIR, "Songs", "vxla")
    if not os.path.exists(vxla_dir):
        print("No vxla directory found")
        return
        
    vxla_files = [f for f in os.listdir(vxla_dir) if f.endswith('.vxla')]
    print(f"Reconstructing {len(vxla_files)} songs from vxla directory...")
    success_count = 0
    
    for vf in vxla_files:
        song_id = vf.replace('.vxla', '')
        vxla_file = os.path.join(vxla_dir, vf)
        
        meta = meta_db.get(song_id)
        if not meta:
            meta = {'artist': 'Unknown Artist', 'title': song_id, 'year': ''}
            
        safe_artist = "".join(c for c in meta.get('artist', 'Unknown Artist') if c.isalnum() or c in " -_")
        safe_title = "".join(c for c in meta.get('title', song_id) if c.isalnum() or c in " -_")
        out_folder = os.path.join(OUTPUT_DIR, f"{safe_artist} - {safe_title}")
        if os.path.exists(out_folder):
            # never touch a song that is already there: its txt may have been corrected or re-synced
            continue
        
        if convert_vxla_to_txt(vxla_file, song_id, meta, out_folder):
            success_count += 1
            
    print(f"Done! Reconstructed {success_count} songs into {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
