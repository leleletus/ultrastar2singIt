"""Status report (Markdown) of a list of songs: in the library or not, USDB, converted, in the patch, on the Switch.

Usage:
    python tools/song_status.py <songs folder> <patch DLC folder> <list.json> [--out report.md]

<list.json>: [{"artist": "...", "title": "...", "note": "optional text"}, ...]. Only reads.
"""
import argparse
import difflib
import json
import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import UltrastarToSingit  # noqa: E402
import naming  # noqa: E402

USDB_DB = Path.home() / '.local/share/usdb_syncer/usdb_syncer.db'


def simple(text):
    text = unicodedata.normalize('NFKD', str(text).lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'\[(duet|multi)\]', ' ', text)
    text = re.sub(r'\((feat|ft|with)[^)]*\)|\b(feat|ft)\b.*', ' ', text)
    return ' '.join(re.sub(r'[^a-z0-9 ]+', ' ', text).split())


def similar(a, b):
    a, b = simple(a), simple(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if (a in b or b in a) and min(len(a), len(b)) >= 4:
        return 0.92
    return difflib.SequenceMatcher(None, a, b).ratio()


def library(songs):
    out = []
    for d in sorted(os.listdir(songs)):
        path = Path(songs) / d
        if not path.is_dir() or d.startswith(('_', '.')):
            continue
        txt = ConvertFiles.choose_txt_file([p for p in path.iterdir() if p.suffix.lower() == '.txt'])
        artist, title = (d.split(' - ', 1) + [''])[:2]
        if txt:
            data = UltrastarToSingit.parse_file(txt)
            artist, title = data.get('ARTIST', artist), data.get('TITLE', title)
        out.append((path, artist, title))
    return out


def origin(path):
    files = os.listdir(path)
    if 'songmaker.json' in files:
        return 'fabricada (SongMaker)'
    if any(f.endswith('.usdb') for f in files):
        return 'USDB'
    if naming.OFFICIAL_VXLA_NAME in files:
        return 'DLC oficial'
    return 'otra'


def song_state(path, patch, switch_photo, json_songs):
    folder = path.name
    nid = naming.construct_name_id_from_directory_name(folder)
    has = lambda suffix: (path / (nid + suffix)).exists()
    problems = []
    video = 'sí' if has('.bk2') else 'no'
    if has('.bk2') and has('.ogg'):
        try:
            if ConvertFiles.is_still_bk2(path / (nid + '.bk2'), ConvertFiles.get_duration(path / (nid + '.ogg'))):
                video = 'portada fija'
                problems.append('video = portada fija (Añadir un video)')
        except Exception:
            pass
    sync = ''
    try:
        sync = json.loads((path / (nid + naming.SYNC_REPORT_SUFFIX)).read_text(encoding='utf-8')).get('verdict', '')
    except (OSError, ValueError):
        pass
    entry = None
    data = None
    txt = ConvertFiles.choose_txt_file([p for p in path.iterdir() if p.suffix.lower() == '.txt'])
    if txt:
        data = UltrastarToSingit.parse_file(txt)
        entry = max(json_songs, key=lambda s: similar(s['title'], data.get('TITLE', '')) * 0.7 +
                    similar(s['artist'], data.get('ARTIST', '')) * 0.3, default=None)
        if entry and (similar(entry['title'], data.get('TITLE', '')) < 0.9
                      or similar(entry['artist'], data.get('ARTIST', '')) < 0.6):
            entry = None  # another song with the same title (badmómzjay - Signal is not TWICE - SIGNAL)
    in_patch = bool(entry) and (Path(patch) / 'romfs/Songs/vxla' / (entry['id'] + '.vxla')).exists()
    on_switch = bool(entry) and f"romfs/Songs/vxla/{entry['id']}.vxla" in switch_photo
    if not has('.vxla'):
        problems.append('sin convertir')
    elif not has(naming.VXLA_FEAT_SUFFIX):
        problems.append('sin letra Feat')
    if sync and sync not in ('ok',):
        problems.append(f'sincronía: {sync}')
    if has('.vxla') and not in_patch:
        problems.append('no está en el parche')
    if in_patch and not on_switch:
        problems.append('falta copiarla a la Switch')
    return {'folder': folder, 'origin': origin(path), 'video': video, 'classic': 'sí' if has('.vxla') else 'no',
            'feat': 'sí' if has(naming.VXLA_FEAT_SUFFIX) else 'no', 'patch': 'sí' if in_patch else 'no',
            'switch': 'sí' if on_switch else 'no', 'sync': sync or '—', 'problems': problems,
            'duet': bool(txt and UltrastarToSingit.is_duet(txt))}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('patch')
    parser.add_argument('list')
    parser.add_argument('--out')
    args = parser.parse_args()
    wanted = json.load(open(args.list, encoding='utf-8'))
    lib = library(args.songs)
    patch = Path(args.patch)
    json_songs = []
    for f in (patch / 'romfs').glob('songs_*.json'):
        json_songs = json.load(open(f, encoding='utf-8-sig')).get('songs', [])
    photo_path = patch.parent.parent / (patch.name + '.switch.json')
    switch_photo = json.load(open(photo_path, encoding='utf-8')) if photo_path.exists() else {}
    usdb = []
    if USDB_DB.exists():
        db = sqlite3.connect(f'file:{USDB_DB}?mode=ro', uri=True)
        usdb = db.execute('select song_id, artist, title, edition from usdb_song').fetchall()

    rows = ['| # | Canción | Estado | Origen | Video | Clásico | Feat | Parche | Switch | Sinc. | Qué falta / notas |',
            '|---|---|---|---|---|---|---|---|---|---|---|']
    counts = {}
    for i, w in enumerate(wanted, 1):
        best = max(lib, key=lambda x: similar(w['title'], x[2]) * 0.7 + similar(w['artist'], x[1]) * 0.3)
        score = similar(w['title'], best[2]) * 0.7 + similar(w['artist'], best[1]) * 0.3
        name = f"{w['artist']} – {w['title']}"
        note = w.get('note', '')
        if score >= 0.85:
            st = song_state(best[0], patch, switch_photo, json_songs)
            status = 'lista' if not st['problems'] else 'en biblioteca'
            extra = '; '.join(st['problems'] + ([note] if note else []) + (['dueto (2 voces)'] if st['duet'] else []))
            rows.append(f"| {i} | {name} | **{status}** | {st['origin']} | {st['video']} | {st['classic']} | "
                        f"{st['feat']} | {st['patch']} | {st['switch']} | {st['sync']} | {extra or '—'} |")
        else:
            hits = [h for h in usdb if similar(w['title'], h[2]) >= 0.9 and similar(w['artist'], h[1]) >= 0.6]
            if hits:
                status = 'en USDB, sin descargar'
                extra = 'descargar en usdb_syncer: ' + ', '.join(f"#{h[0]} {h[1]} – {h[2]}" for h in hits[:3])
            else:
                status = 'no existe: hay que fabricarla'
                extra = 'SongMaker'
            rows.append(f"| {i} | {name} | **{status}** | — | — | — | — | — | — | — | "
                        f"{'; '.join(x for x in (extra, note) if x)} |")
        counts[status] = counts.get(status, 0) + 1
    summary = ', '.join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
    text = '\n'.join([f"# Estado de las canciones pedidas", '', f"{len(wanted)} canciones: {summary}.", ''] + rows) + '\n'
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
