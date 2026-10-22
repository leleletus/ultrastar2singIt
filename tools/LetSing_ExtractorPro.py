import os
import shutil
import json
import argparse
import xml.etree.ElementTree as ET
from PIL import Image
import unicodedata

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def construct_name_id(artist, title) -> str:
    artist_dir_name = strip_accents(artist).replace("?", "").replace("!", "").replace(":", "").replace('"', "").replace("/", " ")
    title_dir_name = strip_accents(title).replace("?", "").replace("!", "").replace(":", "").replace('"', "").replace("/", " ")
    artist_caps = [word[0].upper() for word in artist_dir_name.split()]
    artist_cap = ''.join(artist_caps)
    title_lower = ''.join(e.lower() for e in title_dir_name if e.isalnum())
    return artist_cap + title_lower

def crop_to_square(img_path):
    try:
        with Image.open(img_path) as img:
            width, height = img.size
            if width == height: return
            new_size = min(width, height)
            left = (width - new_size) / 2
            top = (height - new_size) / 2
            right = (width + new_size) / 2
            bottom = (height + new_size) / 2
            img_cropped = img.crop((left, top, right, bottom))
            if img_cropped.mode in ("RGBA", "P"):
                if img_path.lower().endswith(('.jpg', '.jpeg')):
                    img_cropped = img_cropped.convert("RGB")
            img_cropped.save(img_path)
    except Exception as e:
        pass

def convert_to_png(src_path, dest_path):
    try:
        with Image.open(src_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(dest_path, "PNG")
        return True
    except:
        return False

def seconds_to_beats(seconds, bpm=300):
    beats = float(seconds) * float(bpm) / 15.0
    return int(round(beats))

def clean_lyric(lyric):
    return lyric.replace("~", "").replace("\n", "").replace("\r", "")

# The game's offset between its note numbers and UltraStar pitches used by this extractor. It is written
# to the txt as #LETSSINGPITCHOFFSET so the converter restores the original pitches exactly.
PITCH_OFFSET = 36

def _same_time(a, b):
    try:
        return abs(float(a) - float(b)) < 0.005
    except (TypeError, ValueError):
        return False

def _lyric_value(interval):
    return interval.get('value', '')

def check_space_after(t2, lyrics_data):
    for interval in lyrics_data:
        value = _lyric_value(interval)
        if _same_time(interval.get('t2'), t2) and value.endswith(' '):
            return True
        if _same_time(interval.get('t1'), t2) and value == '~':
            return True
    return False

def check_space_before(t1, lyrics_data):
    for interval in lyrics_data:
        value = _lyric_value(interval)
        if _same_time(interval.get('t1'), t1) and value.startswith(' '):
            return True
        if _same_time(interval.get('t2'), t1) and value == '~':
            return True
    return False

def build_metadata_from_json(json_path):
    meta_db = {}
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for s in data.get('songs', []):
                meta_db[s['id']] = s
    return meta_db

def extract_vxla_metadata(vxla_path):
    meta = {}
    try:
        tree = ET.parse(vxla_path)
        root = tree.getroot()
        for layer in root.findall('IntervalLayer'):
            name = layer.get('name')
            if name == 'meta':
                for interval in layer.findall('Interval'):
                    val = interval.get('value', '')
                    if val.startswith('TITLE: '): meta['title'] = val.replace('TITLE: ', '')
                    elif val.startswith('ARTIST: '): meta['artist'] = val.replace('ARTIST: ', '')
                    elif val.startswith('YEAR: '): meta['year'] = val.replace('YEAR: ', '')
    except: pass
    return meta

def fuzzy(s):
    return strip_accents(s.lower().replace('&', '').replace(',', '').replace("'", "").replace(' ', '').replace('-', '').replace('(', '').replace(')', ''))

def convert_vxla_to_txt(vxla_file, song_id, meta, output_folder, mega_dir):
    try:
        tree = ET.parse(vxla_file)
        root = tree.getroot()
    except:
        return False

    notes_layer = None
    lyrics_layer = None
    pages_layer = None
    passages_layer = None

    for layer in root.findall('IntervalLayer'):
        name = layer.get('name')
        if name == 'notes_full': notes_layer = layer
        elif name == 'notes' and notes_layer is None: notes_layer = layer
        elif name == 'lyrics': lyrics_layer = layer
        elif name == 'pages': pages_layer = layer
        elif name == 'passages': passages_layer = layer

    if notes_layer is None:
        return False
    if lyrics_layer is None:
        lyrics_layer = ET.Element('IntervalLayer')

    lyrics_data = lyrics_layer.findall('Interval')
    os.makedirs(output_folder, exist_ok=True)
    
    artist = meta.get('artist', 'Unknown')
    title = meta.get('title', song_id)
    year = meta.get('year', '')
    BPM = 300
    
    txt_filename = f"{os.path.basename(output_folder)}.txt"
    txt_path = os.path.join(output_folder, txt_filename)
    
    name_id = construct_name_id(artist, title)
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"#TITLE:{title}\n")
        f.write(f"#ARTIST:{artist}\n")
        f.write(f"#YEAR:{year}\n")
        f.write(f"#BPM:{BPM}\n")
        f.write("#GAP:0\n")
        f.write(f"#LETSSINGPITCHOFFSET:{PITCH_OFFSET}\n")
        
        # 1. Map Audio
        audio_found = False
        for ext in ['.ogg', '.mp3']:
            ogg_src = os.path.join(mega_dir, "Songs", "audio", f"{song_id}{ext}")
            alt_ogg_src = os.path.join(mega_dir, "Songs", "audio", f"{name_id}{ext}")
            target_src = ogg_src if os.path.exists(ogg_src) else (alt_ogg_src if os.path.exists(alt_ogg_src) else None)
            
            if target_src:
                input_audio = f"audio{ext}"
                f.write(f"#MP3:{input_audio}\n")
                shutil.copy2(target_src, os.path.join(output_folder, input_audio))
                # Create Cache Duplicate
                shutil.copy2(target_src, os.path.join(output_folder, f"{name_id}.ogg"))
                audio_found = True
                break
                
        # 2. Map Video (.bk2 prioritized)
        video_found = False
        for search_dir in ["videos", "vxla_mp4", "videos_mp4"]:
            for ext in ['.mp4', '.webm', '.bk2', '.bik']:
                vid_src = os.path.join(mega_dir, "Songs", search_dir, f"{song_id}{ext}")
                alt_vid_src = os.path.join(mega_dir, "Songs", search_dir, f"{name_id}{ext}")
                target_src = vid_src if os.path.exists(vid_src) else (alt_vid_src if os.path.exists(alt_vid_src) else None)
                
                if target_src:
                    input_video = f"video{ext}"
                    f.write(f"#VIDEO:{input_video}\n")
                    shutil.copy2(target_src, os.path.join(output_folder, input_video))
                    # Create Cache Duplicate (only if it matches what the GUI would generate natively, but creating a copy is safe)
                    shutil.copy2(target_src, os.path.join(output_folder, f"{name_id}{ext}"))
                    video_found = True
                    break
            if video_found: break
            
        # 3. Map Cover
        cover_found = False
        mega_covers = os.path.join(mega_dir, "Songs", "covers")
        if os.path.exists(mega_covers):
            target_fuzzy = fuzzy(name_id)
            target_src = None
            
            # Fuzzy match to find the cover in megapack
            for mf in os.listdir(mega_covers):
                if fuzzy(os.path.splitext(mf)[0]) == target_fuzzy:
                    target_src = os.path.join(mega_covers, mf)
                    break
            
            if target_src:
                ext = os.path.splitext(target_src)[1].lower()
                if ext not in ['.png', '.jpg', '.jpeg']: ext = '.jpg'
                
                input_cover = f"cover{ext}"
                f.write(f"#COVER:{input_cover}\n")
                dest_input = os.path.join(output_folder, input_cover)
                shutil.copy2(target_src, dest_input)
                crop_to_square(dest_input)
                
                # Cache Duplicate as PNG for double check
                cache_dest = os.path.join(output_folder, f"{name_id}.png")
                if ext == '.png':
                    shutil.copy2(dest_input, cache_dest)
                else:
                    convert_to_png(dest_input, cache_dest)
                    
                cover_found = True
                
        # 4. Process Lyrics
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
                try: pitch = int(pitch_str[2:])
                except ValueError: continue
                us_pitch = pitch - PITCH_OFFSET
                lyric = clean_lyric(lyric)
            else:
                try: pitch = int(val)
                except: continue
                us_pitch = pitch - PITCH_OFFSET
                lyric = clean_lyric(next((v for k, v in lyrics_map.items() if abs(k - t1) < 0.005), "~"))
                
            if lyric in ("-", ""): lyric = "~"
            else:
                if check_space_after(t2, lyrics_data): lyric += " "
                if check_space_before(t1, lyrics_data): lyric = " " + lyric
                        
            start_beat = seconds_to_beats(t1)
            duration = seconds_to_beats(t2) - start_beat
            if duration <= 0: duration = 1
                
            if pages_layer is not None:
                for p in pages_layer.findall('Interval'):
                    pt2 = float(p.get('t2'))
                    if last_t2 <= pt2 and t1 >= pt2:
                        f.write(f"- {seconds_to_beats(pt2)}\n")
                        break
            elif start_beat > seconds_to_beats(last_t2) + 20:
                f.write(f"- {seconds_to_beats(last_t2)}\n")
                
            is_freestyle = False
            if passages_layer is not None:
                for p in passages_layer.findall('Interval'):
                    pt1 = float(p.get('t1'))
                    pt2 = float(p.get('t2'))
                    if p.get('value') == "speed" and pt1 <= t1 and pt2 >= t2:
                        is_freestyle = True
                        
            note_char = "F" if is_freestyle else ":"
            f.write(f"{note_char} {start_beat} {duration} {us_pitch} {lyric}\n")
            last_t2 = t2
                
        f.write("E\n")
        
    return True

def main():
    parser = argparse.ArgumentParser(description="Professional Let's Sing Ultrastar Extractor & Linker")
    parser.add_argument('--megapack', type=str, required=True, help="Path to the extracted megapack directory")
    parser.add_argument('--output', type=str, required=True, help="Path to the custom songs output directory")
    parser.add_argument('--json', type=str, help="Path to songs_int_combined.json")
    args = parser.parse_args()

    mega_dir = args.megapack
    out_dir = args.output
    json_path = args.json if args.json else os.path.join(mega_dir, "songs_int_combined.json")
    
    meta_db = build_metadata_from_json(json_path)
    vxla_dir = os.path.join(mega_dir, "Songs", "vxla")
    vxla_files = [f for f in os.listdir(vxla_dir) if f.endswith('.vxla')]
    
    success_count = 0
    for vf in vxla_files:
        song_id = vf.replace('.vxla', '')
        vxla_file = os.path.join(vxla_dir, vf)
        meta = meta_db.get(song_id)
        if not meta or meta.get('artist') == 'Unknown Artist':
            meta = extract_vxla_metadata(vxla_file)
            
        safe_artist = meta.get('artist', 'Unknown Artist').replace("?", "").replace("!", "").replace(":", "").replace('"', "").replace("/", " ").strip()
        safe_title = meta.get('title', song_id).replace("?", "").replace("!", "").replace(":", "").replace('"', "").replace("/", " ").strip()
        
        song_folder = os.path.join(out_dir, f"{safe_artist} - {safe_title}")
        
        if convert_vxla_to_txt(vxla_file, song_id, meta, song_folder, mega_dir):
            success_count += 1
            
    print(f"\n[SUCCESS] Reconstructed {success_count} songs into {out_dir}")
    print("[INFO] All files saved securely as 'inputs' AND populated with 'cache' copies for visual double-checks.")

if __name__ == '__main__':
    main()
