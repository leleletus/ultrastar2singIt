"""Checks a converted patch (JSON editions, Let's Sing 2024+) before copying it to the console. Only reads.

Usage: python tools/validate_patch.py <patch DLC folder, e.g. output/0100EE4020D19003>

Every song of songs_xx.json must have its audio, preview, cover (256x256 PNG), video (.bk2, not empty) and vxla
(with notes that end inside the audio); IDs must be unique and plain ASCII; no file may be left without a song; the
values of the song must be the ones the game knows (Let's Sing 2026 enums, read from the game code). In Let's Sing 2026
every song also needs its Feat mode lyrics (vxla_feat/<id>_feat.vxla: the game closes without them) and should have
beats/<id>.json. Exit code 1 when something is wrong.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import OfficialVxla  # noqa: E402
import data.repository.DlcRepository as repository  # noqa: E402

LANGUAGES = {'English', 'French', 'Spanish', 'German', 'Korean', 'Other'}
GENRES = {'Pop', 'HipHop', 'Ballad', 'Rock', 'RnB', 'Electro', 'Country', 'Latin', 'Summer'}
THEMES = {'Love', 'Deep', 'Party'}
DIFFICULTIES = {'VeryEasy', 'Easy', 'Medium', 'Hard', 'VeryHard'}
GENDERS = {'Women', 'Men', 'Both'}
MIN_BK2 = 16 * 1024


def ogg_duration(path):
    import subprocess
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    dlc = sys.argv[1]
    romfs = os.path.join(dlc, 'romfs')
    jsons = [f for f in os.listdir(romfs) if f.startswith('songs_') and f.endswith('.json')]
    if len(jsons) != 1:
        sys.exit(f"expected one songs_xx.json in {romfs}, found {jsons}")
    data = json.load(open(os.path.join(romfs, jsons[0]), encoding='utf-8-sig'))
    songs = data.get('songs', [])
    songs_dir = os.path.join(romfs, 'Songs')
    entity = repository.get_by_dlc_id(os.path.basename(os.path.normpath(dlc)).upper())
    feat_mode = bool(entity and str(entity.core_edition) == '2026')
    problems, warnings = [], []
    ids = [str(s.get('id')) for s in songs]
    for i in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"{i}: ID repeated")
    for s in songs:
        sid = str(s.get('id'))
        if not re.fullmatch(r'[A-Za-z0-9]+', sid):
            problems.append(f"{sid}: ID with characters other than ASCII letters and digits")
        for field, allowed in (('genre', GENRES), ('difficulty', DIFFICULTIES), ('gender', GENDERS)):
            if s.get(field) not in allowed:
                problems.append(f"{sid}: {field} '{s.get(field)}' unknown to the game")
        for field, allowed in (('language', LANGUAGES), ('theme', THEMES)):
            values = [v.strip() for v in str(s.get(field, '')).split(',') if v.strip()]
            if not values or any(v not in allowed for v in values):
                problems.append(f"{sid}: {field} '{s.get(field)}' unknown to the game")
        if not isinstance(s.get('year'), int) or not 1900 <= s['year'] <= 2100:
            problems.append(f"{sid}: year '{s.get('year')}'")
        files = {'audio': f'{sid}.ogg', 'audio_preview': f'{sid}_preview.ogg', 'covers': f'{sid}.png',
                 'videos': f'{sid}.bk2', 'vxla': f'{sid}.vxla'}
        paths = {k: os.path.join(songs_dir, k, v) for k, v in files.items()}
        missing = [k for k, p in paths.items() if not os.path.isfile(p)]
        if missing:
            # official songs of the DLC itself are not in the patch: their files come from the DLC
            if len(missing) < len(paths):
                problems.append(f"{sid}: missing {', '.join(missing)}")
            continue
        if os.path.getsize(paths['videos']) < MIN_BK2:
            problems.append(f"{sid}: video of {os.path.getsize(paths['videos'])} bytes (failed encode)")
        try:
            from PIL import Image
            with Image.open(paths['covers']) as img:
                if img.size != (256, 256) or img.format != 'PNG':
                    problems.append(f"{sid}: cover {img.format} {img.size[0]}x{img.size[1]} (the game uses 256x256 PNG)")
        except Exception as e:
            problems.append(f"{sid}: cover unreadable ({e})")
        try:
            layers, _ = OfficialVxla.read_layers(paths['vxla'])
            notes = layers.get('notes_full') or []
            if not notes:
                problems.append(f"{sid}: vxla without notes")
            else:
                duration = ogg_duration(paths['audio'])
                end = max(t2 for _, t2, _ in notes)
                if duration and end > duration + 0.5:
                    warnings.append(f"{sid}: lyrics end {end - duration:.1f} s after the audio")
                text = ''.join(v for _, _, v in layers.get('lyrics', []))
                if re.search(r'Ã.|Â|â€|�', text):
                    problems.append(f"{sid}: broken characters in the lyrics")
        except Exception as e:
            problems.append(f"{sid}: vxla unreadable ({e})")
        if feat_mode:
            feat = os.path.join(songs_dir, 'vxla_feat', f'{sid}_feat.vxla')
            if not os.path.isfile(feat):
                problems.append(f"{sid}: no vxla_feat (the game closes when it is sung in Feat mode)")
            else:
                try:
                    layers, _ = OfficialVxla.read_layers(feat)
                    segments = layers.get('segments') or []
                    if not layers.get('notes_full') or not segments or segments[0][0] > 1e-3 \
                            or any(abs(a[1] - b[0]) > 1e-3 for a, b in zip(segments, segments[1:])):
                        problems.append(f"{sid}: vxla_feat without notes or with segments that leave gaps")
                    if any(name not in layers for name in ('notes2_full', 'lyrics2', 'pages2')):
                        problems.append(f"{sid}: vxla_feat without the second voice layers")
                except Exception as e:
                    problems.append(f"{sid}: vxla_feat unreadable ({e})")
            if not os.path.isfile(os.path.join(songs_dir, 'beats', f'{sid}.json')):
                warnings.append(f"{sid}: no beats (only the effects that follow the music)")
    known = set(ids)
    for sub in ('audio', 'audio_preview', 'covers', 'videos', 'vxla', 'vxla_feat', 'beats'):
        folder = os.path.join(songs_dir, sub)
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            stem = re.sub(r'(_preview|_feat)?\.[A-Za-z0-9]+$', '', name)
            if stem not in known:
                warnings.append(f"{sub}/{name}: no song uses it")
    print(f"{len(songs)} songs checked: {len(problems)} problem(s), {len(warnings)} warning(s)")
    for p in problems:
        print('  PROBLEM ', p)
    for w in warnings:
        print('  warning ', w)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
