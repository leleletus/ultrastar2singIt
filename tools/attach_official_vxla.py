"""Copies the official Let's Sing lyrics/notes (.vxla) into the song folders that come from Let's Sing DLCs, so the
converter reuses them exactly (timing, pitch and syllables) instead of rebuilding them from the txt.

Usage:
    python tools/attach_official_vxla.py <songs folder> <megapack folder>            # only lists the matches
    python tools/attach_official_vxla.py <songs folder> <megapack folder> --apply    # copies them

<megapack folder> contains Songs/vxla/<ID>.vxla, Songs/audio/<ID>.ogg and songs_*.json files.

A song is matched by artist + title (from the DLC json) and accepted when either
  - it was rebuilt from the DLC (the extractor's footprint in the txt), or
  - its audio file is byte-for-byte the same size as the DLC audio (same recording, so the timing matches).
Nothing is overwritten; only letssing_original.vxla is added to the song folder.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import naming  # noqa: E402
import UltrastarToSingit  # noqa: E402
from tools.mark_extracted_songs import looks_extracted  # noqa: E402


def simplify(text):
    text = re.sub(r'\(.*?\)|\[.*?\]|feat\..*$|ft\..*$', '', text or '', flags=re.IGNORECASE)
    return re.sub(r'[^a-z0-9]+', '', naming.strip_accents(text).lower())


def load_catalog(megapack):
    catalog = {}
    for path in glob.glob(os.path.join(megapack, '*.json')):
        try:
            with open(path, encoding='utf-8-sig') as f:
                songs = json.load(f).get('songs', [])
        except (OSError, ValueError):
            continue
        for s in songs:
            if s.get('id'):
                catalog.setdefault(s['id'], s)
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('megapack')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    vxla_dir = os.path.join(args.megapack, 'Songs', 'vxla')
    audio_dir = os.path.join(args.megapack, 'Songs', 'audio')
    available = {f[:-5] for f in os.listdir(vxla_dir) if f.endswith('.vxla')}
    catalog = {k: v for k, v in load_catalog(args.megapack).items() if k in available}
    by_title = {}
    for song_id, s in catalog.items():
        by_title.setdefault(simplify(s.get('title')), []).append(song_id)
    # ids without json metadata can still match by their CamelCase id ("BeTheOne" -> "betheone")
    for song_id in available - set(catalog):
        by_title.setdefault(simplify(song_id), []).append(song_id)

    attached = skipped = 0
    for folder in sorted(os.listdir(args.songs), key=str.lower):
        song_dir = os.path.join(args.songs, folder)
        if not os.path.isdir(song_dir) or ' - ' not in folder or folder.startswith(('_', '.')):
            continue
        if os.path.exists(os.path.join(song_dir, naming.OFFICIAL_VXLA_NAME)):
            continue
        artist, title = folder.split(' - ', 1)
        txts = [os.path.join(song_dir, f) for f in os.listdir(song_dir) if f.lower().endswith('.txt')]
        data = {}
        for t in sorted(txts):
            try:
                data = UltrastarToSingit.parse_file(t)
                break
            except Exception:
                continue
        candidates = by_title.get(simplify(data.get('TITLE') or title), []) + by_title.get(simplify(title), [])
        candidates = list(dict.fromkeys(candidates))
        if not candidates:
            continue

        def artist_ok(song_id):
            known = catalog.get(song_id, {}).get('artist')
            if not known or known.lower().startswith('unknown'):
                return True
            a, b = simplify(known), simplify(data.get('ARTIST') or artist)
            return a in b or b in a or a[:5] == b[:5]
        candidates = [c for c in candidates if artist_ok(c)]
        if not candidates:
            continue

        audio_name = data.get('AUDIO') or data.get('MP3') or ''
        audio_path = os.path.join(song_dir, audio_name)
        audio_size = os.path.getsize(audio_path) if audio_name and os.path.isfile(audio_path) else None
        chosen, reason = None, None
        for song_id in candidates:
            dlc_audio = os.path.join(audio_dir, song_id + '.ogg')
            if audio_size is not None and os.path.isfile(dlc_audio) and os.path.getsize(dlc_audio) == audio_size:
                chosen, reason = song_id, 'same audio as the DLC'
                break
        if chosen is None and data and looks_extracted(data):
            chosen, reason = candidates[0], 'rebuilt from the DLC'
        if chosen is None:
            print(f"  ?  {folder}: possible DLC song {candidates} but its audio differs (timing may not match): skipped")
            skipped += 1
            continue

        print(f"{'attach' if args.apply else 'would attach'}: {folder}  <-  {chosen}.vxla ({reason})")
        if args.apply:
            shutil.copy2(os.path.join(vxla_dir, chosen + '.vxla'), os.path.join(song_dir, naming.OFFICIAL_VXLA_NAME))
        attached += 1

    print(f"\n{attached} song(s) {'attached' if args.apply else 'can be attached (run again with --apply)'}, "
          f"{skipped} possible matches skipped.")


if __name__ == '__main__':
    main()
