import json
import os


def unpack_dlc(songs_dir: str, input_dir: str) -> tuple[int, str]:
    """Rebuilds UltraStar song folders from a Let's Sing 'Songs' folder (romfs/Songs) using the
    LetSing_ExtractorPro logic (the old converter in this file wrote wrong timings)."""
    from tools import LetSing_ExtractorPro as extractor

    if not songs_dir or os.path.basename(os.path.normpath(songs_dir)) != "Songs":
        return 0, "You must select a folder named 'Songs' (from romfs/Songs)."
    if not input_dir or not os.path.exists(input_dir):
        return 0, "Your main Input folder must be set and exist."

    vxla_dir = os.path.join(songs_dir, "vxla")
    if not os.path.exists(vxla_dir):
        return 0, "No 'vxla' subfolder found. Cannot extract lyrics."

    # Song metadata from a songs_xx.json next to the Songs folder
    parent_dir = os.path.dirname(os.path.normpath(songs_dir))
    meta_db = {}
    for f in sorted(os.listdir(parent_dir)):
        if f.endswith('.json'):
            try:
                with open(os.path.join(parent_dir, f), 'r', encoding='utf-8-sig') as j:
                    for s in json.load(j).get('songs', []):
                        meta_db[s.get('id')] = s
            except (OSError, ValueError):
                pass

    extracted = 0
    skipped = 0
    for f in sorted(os.listdir(vxla_dir)):
        if not f.endswith(".vxla"):
            continue
        song_id = f[:-len(".vxla")]
        vxla_file = os.path.join(vxla_dir, f)
        meta = meta_db.get(song_id) or extractor.extract_vxla_metadata(vxla_file) or {}
        meta.setdefault('artist', 'Unknown Artist')
        meta.setdefault('title', song_id)

        safe_artist = "".join(c for c in meta['artist'] if c.isalnum() or c in " -_&'").strip()
        safe_title = "".join(c for c in meta['title'] if c.isalnum() or c in " -_&'").strip()
        out_folder = os.path.join(input_dir, f"{safe_artist} - {safe_title}")
        if os.path.exists(out_folder):
            skipped += 1  # never overwrite an existing song folder
            continue
        if extractor.convert_vxla_to_txt(vxla_file, song_id, meta, out_folder, parent_dir):
            extracted += 1

    return extracted, (f"Successfully reversed {extracted} songs into {input_dir}"
                       + (f" ({skipped} already existed and were left untouched)" if skipped else ""))
