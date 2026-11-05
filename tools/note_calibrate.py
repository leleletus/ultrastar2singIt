"""Measures SongMaker's note maker against official Let's Sing songs: it gets only the lines of the official lyrics
(start time and text) and the analysed voice (<id>.voice.npz), and its notes are compared with the official ones.

Usage:
    python tools/note_calibrate.py <songs folder> [--each]

Official songs need their voice analysed first (open them once in the sync editor, or SyncModel.analyze_voice).
"""
import argparse
import os
import re
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import SongMaker  # noqa: E402
from note_style import stats, KEYS  # noqa: E402

FRAME = SongMaker.FRAME


def read_official(path):
    """(lines [(t, text)], syllables [(t1, t2, text)], notes [(t1, t2, midi or None)])."""
    text = Path(path).read_text(encoding='iso-8859-1', errors='replace')
    layers = {name: re.findall(r't1="([\d.]+)" t2="([\d.]+)" value="([^"]*)"', body) for name, body in
              re.findall(r'<IntervalLayer[^>]*name="([a-z_0-9]+)"[^>]*>(.*?)</IntervalLayer>', text, re.S)}
    syllables = [(float(a), float(b), v) for a, b, v in layers['lyrics']]
    if 'notes' in layers:
        notes = [(float(a), float(b), int(v)) for a, b, v in layers['notes']]
    else:
        notes = []
        for a, b, v in layers.get('notes_full', []):
            m = re.match(r'#p(\d+)', v)
            if m:
                p = int(m.group(1))
                notes.append((float(a), float(b), None if p == 1 else p))
    lines = []
    for a, b, _ in layers['pages']:
        a, b = float(a), float(b)
        inside = [s for s in syllables if a <= s[0] < b]
        if inside:
            lines.append((inside[0][0], ''.join(s[2] for s in inside).replace('-', '').strip(), inside))
    return lines, syllables, notes


def language_of(folder):
    for txt in Path(folder).glob('*.txt'):
        m = re.search(r'^#LANGUAGE:(.+)$', txt.read_text(encoding='utf-8', errors='replace'), re.M)
        if m:
            return m.group(1).strip()
    return 'English'


def compare(official_notes, official_lines, made_lines):
    made = [n for line in made_lines for n in line]
    end = max(n[1] for n in official_notes) + 2
    frames = int(end / FRAME) + 1
    off = np.full(frames, np.nan)
    off_rap = np.zeros(frames, bool)
    gen = np.full(frames, np.nan)
    for a, b, p in official_notes:
        if p is None:
            off_rap[int(a / FRAME):int(b / FRAME)] = True
        else:
            off[int(a / FRAME):int(b / FRAME)] = p
    for a, b, p, _ in made:
        if int(a / FRAME) < frames:
            gen[int(a / FRAME):int(b / FRAME)] = p if p is not None else -1
    both = ~np.isnan(off) & ~np.isnan(gen) & (gen > 0)
    diff = np.abs(((gen[both] - off[both]) + 6) % 12 - 6)
    official_time = (~np.isnan(off)).sum()
    made_time = (~np.isnan(gen)).sum()
    # syllable starts, line by line when the syllable counts agree
    errors, same = [], 0
    for (t, text, syl), notes in zip(official_lines, made_lines):
        starts = [n[0] for n in notes if n[3] not in ('~',)]
        if len(starts) == len(syl):
            same += 1
            errors += [abs(x - s[0]) for x, s in zip(starts, syl)]
    return {
        'pitch±1': float((diff <= 1).mean()) if len(diff) else 0.0,
        'pitch_exact': float((diff < 0.5).mean()) if len(diff) else 0.0,
        'covered': float(both.sum() / max(1, official_time)),
        'extra': float(((~np.isnan(gen)) & np.isnan(off) & ~off_rap).sum() / max(1, made_time)),
        'onset_err': statistics.median(errors) if errors else float('nan'),
        'same_syl': same / max(1, len(official_lines)),
        'rap_found': float(((gen == -1) & off_rap).sum() / max(1, off_rap.sum())) if off_rap.any() else float('nan'),
        'false_rap': float(((gen == -1) & ~np.isnan(off)).sum() / max(1, official_time)),
    }


MKEYS = ['pitch±1', 'pitch_exact', 'covered', 'extra', 'onset_err', 'same_syl', 'rap_found', 'false_rap']


def run(songs, maker, each=False):
    rows = []
    for d in sorted(os.listdir(songs)):
        folder = Path(songs) / d
        vx = folder / 'letssing_original.vxla'
        npz = list(folder.glob('*.voice.npz'))
        if not vx.exists() or not npz:
            continue
        data = np.load(npz[0])
        energy, pitch = data['energy'].astype(np.float32), data['pitch'].astype(np.float32)
        lines, syllables, notes = read_official(vx)
        made = maker([(t, text) for t, text, _ in lines], 0.0, energy, pitch, language_of(folder))
        m = compare(notes, lines, made)
        s = stats([(a, b, p, t != '~') for line in made for a, b, p, t in line])
        o = stats([(a, b, p, True) for a, b, p in notes])
        rows.append((d, m, s, o))
        if each:
            print(f"{d[:34]:<34}" + ''.join(f" {k}={m[k]:.2f}" for k in MKEYS)
                  + f" | len {s['len_med']:.2f}/{o['len_med']:.2f} short {s['short<0.12']:.2f}"
                  + f" jump>=5 {s['jump>=5']:.2f}/{o['jump>=5']:.2f} n {s['notes']:.0f}/{o['notes']:.0f}")

    def med(values):
        values = [v for v in values if not np.isnan(v)]
        return statistics.median(values) if values else float('nan')
    print(f"{'MEDIAN':<34}" + ''.join(f" {k}={med([r[1][k] for r in rows]):.2f}" for k in MKEYS))
    print(f"{'made style':<34}" + ''.join(f" {k}={med([r[2][k] for r in rows]):.2f}" for k in KEYS))
    print(f"{'official style':<34}" + ''.join(f" {k}={med([r[3][k] for r in rows]):.2f}" for k in KEYS))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--each', action='store_true')
    args = parser.parse_args()
    run(args.songs, SongMaker.make_notes, args.each)


if __name__ == '__main__':
    main()
