import os
import shutil
import json
import xml.etree.ElementTree as ET
from pathlib import Path

BPM = 300
MULTIPLIER = (BPM * 4) / 60.0

def construct_name_id_from_directory_name(dir_long_name) -> str:
    import unicodedata
    def strip_accents(s):
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    split_dir_name = dir_long_name.split(' - ')
    if len(split_dir_name) < 2: return dir_long_name
    artist_dir_name = strip_accents(split_dir_name[0])
    title_dir_name = strip_accents(split_dir_name[1])
    artist_caps = [word[0].upper() for word in artist_dir_name.split()]
    artist_cap = ''.join(artist_caps)
    title_lower = ''.join(e.lower() for e in title_dir_name if e.isalnum())
    return artist_cap + title_lower

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
                if val == " " or val.endswith(" ") or val.startswith(" "):
                    spaces.append({
                        't1': float(interval.get('t1')),
                        't2': float(interval.get('t2')),
                        'val': val
                    })
            break
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

def convert_vxla_to_txt(vxla_file, song_id, meta, output_folder, songs_dir):
    try:
        with open(vxla_file, 'rb') as f:
            raw = f.read()
        try: raw = raw.decode('utf-8')
        except: raw = raw.decode('latin-1')
        raw = raw.replace('encoding="utf-16"', 'encoding="utf-8"').replace('encoding="UTF-16"', 'encoding="utf-8"')
        root = ET.fromstring(raw)
    except Exception as e:
        return False
    
    notes_layer = None
    passages_layer = None
    pages_layer = None
    for layer in root.findall('IntervalLayer'):
        if layer.get('name') == 'notes_full':
            notes_layer = layer
        elif layer.get('name') == 'notes' and notes_layer is None:
            notes_layer = layer
        elif layer.get('name') == 'passages':
            passages_layer = layer
        elif layer.get('name') == 'pages':
            pages_layer = layer
            
    if notes_layer is None:
        return False
        
    lyrics_data = get_lyrics_spaces(root)
        
    title = meta.get('title', song_id)
    artist = meta.get('artist', 'Unknown Artist')
    real_bpm = meta.get('bpm', BPM)
    
    os.makedirs(output_folder, exist_ok=True)
    
    txt_path = os.path.join(output_folder, f"{song_id}.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"#TITLE:{title}\n")
        f.write(f"#ARTIST:{artist}\n")
        f.write(f"#YEAR:{meta.get('year', '')}\n")
        f.write(f"#BPM:{real_bpm}\n")
        f.write(f"#GAP:0\n")
        
        folder_name = f"{safe_artist} - {safe_title}"
        name_id = construct_name_id_from_directory_name(folder_name)
        
        ogg_src = os.path.join(songs_dir, "audio", f"{song_id}.ogg")
        if os.path.exists(ogg_src):
            f.write(f"#MP3:{name_id}.ogg\n")
            try: shutil.copy2(ogg_src, os.path.join(output_folder, f"{name_id}.ogg"))
            except: pass
            
        video_found = False
        for ext in ['.mp4', '.webm', '.bik']:
            vid_src = os.path.join(songs_dir, "videos", f"{song_id}{ext}")
            if os.path.exists(vid_src):
                f.write(f"#VIDEO:{name_id}{ext}\n")
                try: shutil.copy2(vid_src, os.path.join(output_folder, f"{name_id}{ext}"))
                except: pass
                video_found = True
                break
                
        for ext in ['.jpg', '.png']:
            cov_src = os.path.join(songs_dir, "covers", f"{song_id}{ext}")
            if os.path.exists(cov_src):
                f.write(f"#COVER:{name_id}{ext}\n")
                try: shutil.copy2(cov_src, os.path.join(output_folder, f"{name_id}{ext}"))
                except: pass
                break
            
        last_t2 = 0
        for interval in notes_layer.findall('Interval'):
            t1 = float(interval.get('t1'))
            t2 = float(interval.get('t2'))
            val = interval.get('value')
            
            parts = val.split(',')
            if len(parts) >= 2:
                us_pitch = parts[1]
                lyric = clean_lyric(parts[0])
                if lyric == "" or lyric == "-":
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

def unpack_dlc(songs_dir: str, input_dir: str) -> tuple[int, str]:
    if not songs_dir or not songs_dir.endswith("Songs"):
        return 0, "You must select a folder named 'Songs' (from romfs/Songs)."
    if not input_dir or not os.path.exists(input_dir):
        return 0, "Your main Input folder must be set and exist."

    vxla_dir = os.path.join(songs_dir, "vxla")
    if not os.path.exists(vxla_dir):
        return 0, "No 'vxla' subfolder found. Cannot extract lyrics."

    # Try to find a JSON file alongside Songs dir
    parent_dir = os.path.dirname(songs_dir)
    json_path = None
    for f in os.listdir(parent_dir):
        if f.endswith('.json'):
            json_path = os.path.join(parent_dir, f)
            break
            
    meta_db = {}
    if json_path:
        try:
            with open(json_path, 'r', encoding='utf-8') as j:
                data = json.load(j)
            for s in data.get('songs', []):
                meta_db[s.get('id')] = s
        except: pass

    extracted = 0
    for f in os.listdir(vxla_dir):
        if f.endswith(".vxla"):
            song_id = f.split(".")[0]
            meta = meta_db.get(song_id, {'artist': 'Unknown', 'title': song_id, 'year': '', 'bpm': 300})
            
            safe_artist = "".join(c for c in meta['artist'] if c.isalnum() or c in " -_")
            safe_title = "".join(c for c in meta['title'] if c.isalnum() or c in " -_")
            out_folder = os.path.join(input_dir, f"{safe_artist} - {safe_title}")
            
            if convert_vxla_to_txt(os.path.join(vxla_dir, f), song_id, meta, out_folder, songs_dir):
                extracted += 1
                
    return extracted, f"Successfully reversed {extracted} songs into {input_dir} using VXLA deep extraction!"
