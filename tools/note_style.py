"""Compares how notes are written in the official Let's Sing songs (letssing_original.vxla) and in UltraStar .txt
files (e.g. the ones SongMaker makes): note length, pitch jumps between neighbouring notes, notes per syllable,
rap notes... The official songs are the model of what a person can sing.

Usage:
    python tools/note_style.py <songs folder>                 # official vs SongMaker songs
    python tools/note_style.py <songs folder> --txt a.txt b.txt
"""
import argparse
import os
import re
import statistics
import sys
from pathlib import Path

PHRASE_GAP = 0.35  # seconds of silence that end a phrase (between notes of the same phrase the jump counts)


def official_notes(path):
    """[(t1, t2, pitch or None for rap, starts a syllable)] from an official vxla."""
    text = Path(path).read_text(encoding='iso-8859-1', errors='replace')
    layers = {}
    for name, body in re.findall(r'<IntervalLayer[^>]*name="([a-z_0-9]+)"[^>]*>(.*?)</IntervalLayer>', text, re.S):
        layers[name] = re.findall(r't1="([\d.]+)" t2="([\d.]+)" value="([^"]*)"', body)
    out = []
    if 'notes' in layers:
        import bisect
        lyr = sorted(float(a) for a, b, v in layers.get('lyrics', []))
        for a, b, v in layers['notes']:
            a, b = float(a), float(b)
            i = bisect.bisect_left(lyr, a - 0.06)
            out.append((a, b, int(v), i < len(lyr) and lyr[i] <= a + 0.02))
        return out
    for a, b, v in layers.get('notes_full', []):
        m = re.match(r'#p(\d+)', v)
        if not m:
            continue
        p = int(m.group(1))
        syl = v.split('#.', 1)[1] if '#.' in v else ''
        syl = re.sub(r'#\w\d*', '', syl)
        out.append((float(a), float(b), None if p == 1 else p, syl.strip() not in ('', '~', '-')))
    return out


def txt_notes(path):
    """Same from an UltraStar txt (rap/freestyle notes have pitch None)."""
    bpm, gap, out = None, 0.0, []
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith('#BPM:'):
            bpm = float(line[5:].replace(',', '.'))
        elif line.startswith('#GAP:'):
            gap = float(line[5:].replace(',', '.')) / 1000
        elif line[:1] in ':*FRG' and bpm:
            parts = line.split(' ', 4)
            if len(parts) < 4:
                continue
            beat, length, pitch = int(parts[1]), int(parts[2]), int(parts[3])
            text = parts[4] if len(parts) > 4 else ''
            spb = 60 / bpm / 4
            t1 = gap + beat * spb
            out.append((t1, t1 + length * spb, None if line[0] in 'FRG' else pitch + 60,
                        text.strip() not in ('~', '')))
    return out


def stats(notes):
    if len(notes) < 20:
        return None
    lengths = [b - a for a, b, p, s in notes]
    jumps, zigzag, pairs = [], 0, 0
    prev_dir = 0
    for (a1, b1, p1, _), (a2, b2, p2, _) in zip(notes, notes[1:]):
        if a2 - b1 > PHRASE_GAP or p1 is None or p2 is None:
            prev_dir = 0
            continue
        d = p2 - p1
        jumps.append(abs(d))
        pairs += 1
        direction = (d > 0) - (d < 0)
        if direction and prev_dir and direction != prev_dir and abs(d) <= 2:
            zigzag += 1
        prev_dir = direction or prev_dir
    pitched = [n for n in notes if n[2] is not None]
    syl = sum(1 for n in notes if n[3])
    return {
        'notes': len(notes),
        'len_med': statistics.median(lengths),
        'short<0.12': sum(x < 0.12 for x in lengths) / len(lengths),
        'long>0.6': sum(x > 0.6 for x in lengths) / len(lengths),
        'jump0': sum(j == 0 for j in jumps) / max(1, len(jumps)),
        'jump1-2': sum(1 <= j <= 2 for j in jumps) / max(1, len(jumps)),
        'jump>=5': sum(j >= 5 for j in jumps) / max(1, len(jumps)),
        'jump_mean': statistics.mean(jumps) if jumps else 0,
        'zigzag': zigzag / max(1, pairs),
        'notes/syl': len(notes) / max(1, syl),
        'rap': 1 - len(pitched) / len(notes),
        'range': (max(n[2] for n in pitched) - min(n[2] for n in pitched)) if pitched else 0,
    }


KEYS = ['notes', 'len_med', 'short<0.12', 'long>0.6', 'jump0', 'jump1-2', 'jump>=5', 'jump_mean', 'zigzag',
        'notes/syl', 'rap', 'range']


def summary(name, rows):
    rows = [r for r in rows if r]
    if not rows:
        return
    print(f"{name:<28} n={len(rows):<4}" + ''.join(
        f" {k}={statistics.median(r[k] for r in rows):.2f}" for k in KEYS))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--txt', nargs='*')
    parser.add_argument('--each', action='store_true', help='one row per song')
    args = parser.parse_args()
    songs = Path(args.songs)
    official, made = [], []
    for d in sorted(os.listdir(songs)):
        folder = songs / d
        vx = folder / 'letssing_original.vxla'
        if vx.exists():
            official.append((d, stats(official_notes(vx))))
        elif (folder / 'songmaker.json').exists():
            txt = folder / f'{d}.txt'
            if not txt.exists():
                txts = list(folder.glob('*.txt'))
                txt = txts[0] if txts else None
            if txt:
                made.append((d, stats(txt_notes(txt))))
    summary('official', [r for _, r in official])
    summary('songmaker', [r for _, r in made])
    for t in args.txt or []:
        summary(Path(t).stem[:28], [stats(txt_notes(t))])
    if args.each:
        for d, r in made:
            if r:
                print(f"{d[:40]:<40}" + ''.join(f" {k}={r[k]:.2f}" for k in KEYS))


if __name__ == '__main__':
    sys.exit(main())
