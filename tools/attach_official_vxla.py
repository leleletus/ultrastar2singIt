"""Copies the official Let's Sing lyrics/notes (.vxla) into the song folders that come from Let's Sing DLCs, so the
converter reuses them exactly (timing, pitch and syllables) instead of rebuilding them from the txt.

Usage:
    python tools/attach_official_vxla.py <songs folder> <megapack folder>            # only lists the matches
    python tools/attach_official_vxla.py <songs folder> <megapack folder> --apply    # copies them

<megapack folder> contains Songs/vxla/<ID>.vxla, Songs/audio/<ID>.ogg and songs_*.json files.

A song rebuilt from a DLC (the extractor's footprint in its txt) is matched against every official vxla by its
syllables (the txt was made from one of them). Songs whose lyrics were lost are matched by their note timing
(an old extractor compressed the timing 4 times, both scales are tried) together with the title. Other songs are matched by
artist + title and accepted only if their audio file has the same size as the DLC audio (same recording).
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
import OfficialVxla  # noqa: E402
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


def note_starts_from_txt(data, count=40):
    try:
        bpm = float(data['BPM'].replace(',', '.'))
        gap = float((data.get('GAP') or '0').replace(',', '.')) / 1000
    except (KeyError, ValueError):
        return []
    return [int(n[1]) * 60 / bpm / 4 + gap for n in data['notes'] if n and n[0] in ':*FRG'][:count]


def note_starts_from_vxla(path, count=40):
    layers, _ = OfficialVxla.read_layers(path)
    notes = layers.get('notes_full') or layers.get('notes') or []
    return sorted(t1 for t1, _, _ in notes)[:count]


def timing_score(txt_starts, vxla_starts, tolerance=0.07):
    """Share of the txt notes that start at the same time as the official notes (scale 1 or 4)."""
    if len(txt_starts) < 10 or not vxla_starts:
        return 0.0
    best = 0.0
    for scale in (1.0, 4.0):
        hits = sum(1 for t in txt_starts if any(abs(t * scale - v) <= tolerance * scale for v in vxla_starts))
        best = max(best, hits / len(txt_starts))
    return best


def _clean_syllable(text):
    text = re.sub(r'#[a-z]\d*', '', text or '').replace('~', '').strip().lower()
    # accents compared loosely: older extractions dropped them
    return '' if text in ('', '-') else re.sub(r'[^a-z0-9]', '', naming.strip_accents(text))


def syllables_from_txt(data, count=80):
    out = [_clean_syllable(n[4]) for n in data['notes'] if n and n[0] in ':*FRG' and len(n) > 4]
    return [s for s in out if s][:count]


def syllables_from_vxla(path, count=80):
    layers, _ = OfficialVxla.read_layers(path)
    if layers.get('notes_full'):
        values = [v.split('#.', 1)[1] if '#.' in v else '' for _, _, v in sorted(layers['notes_full'])]
    else:
        values = [v for _, _, v in sorted(layers.get('lyrics_cut') or layers.get('lyrics') or [])]
    out = [_clean_syllable(v) for v in values]
    return [s for s in out if s][:count]


def lyrics_score(a, b):
    from difflib import SequenceMatcher
    if len(a) < 8 or len(b) < 8:
        return 0.0
    return SequenceMatcher(None, ' '.join(a), ' '.join(b[:len(a) + 10])).ratio()


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

    official_starts, official_syllables = {}, {}
    for song_id in available:
        try:
            path = os.path.join(vxla_dir, song_id + '.vxla')
            official_starts[song_id] = note_starts_from_vxla(path)
            official_syllables[song_id] = syllables_from_vxla(path)
        except Exception:
            pass

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
        if data and looks_extracted(data):
            # rebuilt from a DLC: find the official file it came from
            syllables = syllables_from_txt(data)
            if len(syllables) >= 8:
                scored = sorted(((lyrics_score(syllables, v), sid) for sid, v in official_syllables.items()),
                                reverse=True)
                how, threshold = 'same lyrics', 0.85
                wanted = {simplify(data.get('TITLE') or title), simplify(title)}
                if scored and scored[0][0] < threshold:
                    # same title as the official file and clearly similar lyrics (old extractions split
                    # apostrophes and accents differently)
                    same_title = [(sc, sid) for sc, sid in scored if simplify(sid) in wanted and sc >= 0.5]
                    if same_title:
                        scored, how, threshold = same_title, 'same title, similar lyrics', 0.5
            else:
                # lyrics lost: note timing, and the title must agree with the file name
                starts = note_starts_from_txt(data)
                wanted = {simplify(data.get('TITLE') or title), simplify(title)}
                scored = sorted(((timing_score(starts, v), sid) for sid, v in official_starts.items()
                                 if simplify(sid) in wanted or simplify(catalog.get(sid, {}).get('title')) in wanted),
                                reverse=True)
                how, threshold = 'same title and note timing', 0.6
            if scored and scored[0][0] >= threshold:
                score, chosen = scored[0]
                print(f"{'attach' if args.apply else 'would attach'}: {folder}  <-  {chosen}.vxla ({how}, {score:.0%})")
                if args.apply:
                    shutil.copy2(os.path.join(vxla_dir, chosen + '.vxla'), os.path.join(song_dir, naming.OFFICIAL_VXLA_NAME))
                attached += 1
            else:
                best = f"{scored[0][1]} {scored[0][0]:.0%}" if scored else "none"
                print(f"  ?  {folder}: rebuilt song but no official file with the same timing (best: {best})")
                skipped += 1
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
