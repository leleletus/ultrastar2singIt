"""Points of SongMaker songs to check by ear: lines the speech model does not recognise where they are, long gaps
where it hears words but there are no lyrics (missing lyrics, or people talking in the video), lines alone far from
the rest and ad-libs piled up. Writes <song>/revisar.json (the sync editor jumps through them with N) and a list.

Usage:
    python tools/review_points.py <songs folder> [--skip "LISA - Dream" ...] [--md REVISAR.md]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import SongMaker  # noqa: E402
import VoiceAlign  # noqa: E402
import songmaker_report as R  # noqa: E402

REVIEW_FILE = 'revisar.json'


def heard(ctc, a, b):
    """Letters the model reads between two seconds (no language model: a rough idea of what is said)."""
    logp, vocab = ctc
    inv = {v: k for k, v in vocab.items()}
    blank = vocab.get('<blank>', 0)
    out, prev = [], None
    for x in logp[int(a / SongMaker.FRAME):int(b / SongMaker.FRAME)].argmax(1):
        if x != prev and x != blank:
            out.append(inv.get(int(x), ''))
        prev = x
    return ''.join(out)


def points(folder):
    txt = R.current_txt(folder)
    ctc = SongMaker.speech_model(folder, None, make=False)
    if txt is None or ctc is None:
        return []
    logp, vocab = ctc
    song, shift = R.load(txt, folder)
    lines = []
    for i, idx in enumerate(song.lines):
        syl = [song.syllables[k][2] for k in idx if song.syllables[k][2].strip() not in ('~', '')]
        if syl:
            lines.append((song.line_starts[i] + shift, song.line_ends[i] + shift, syl))
    out = []
    duration = len(logp) * SongMaker.FRAME
    previous_end = 0.0
    for k, (a, b, syl) in enumerate(lines):
        text = ''.join(syl).strip()
        gap = a - previous_end
        words = heard(ctc, previous_end, a)
        if gap > 8 and len(words) >= 8:
            out.append({'t': round(previous_end, 1), 'why': f"{gap:.0f} s sin letra pero se oyen palabras: «{words[:60]}» "
                        "→ ¿falta letra, o es gente hablando en el video?"})
        found = VoiceAlign.align_line(logp, vocab, int((a - 0.3) / SongMaker.FRAME), int((b + 0.3) / SongMaker.FRAME), syl)
        if found is None or found[1] < SongMaker.ALIGN_MIN_LOGP:
            out.append({'t': round(a, 1), 'why': f"el modelo no reconoce «{text}» aquí (oye «{heard(ctc, a, b)[:40]}»)"})
        after = lines[k + 1][0] - b if k + 1 < len(lines) else 0
        if gap > 10 and after > 10:
            out.append({'t': round(a, 1), 'why': f"«{text}» está sola, lejos de las demás → ¿va aquí?"})
        previous_end = b
    tail = heard(ctc, previous_end, duration)
    if duration - previous_end > 8 and len(tail) >= 8:
        out.append({'t': round(previous_end, 1), 'why': f"después de la última línea se oyen palabras: «{tail[:60]}» "
                    "→ ¿falta letra al final?"})
    rows = sorted(out, key=lambda p: p['t'])
    merged = []
    for p in rows:  # one point every 2 s at most
        if merged and p['t'] - merged[-1]['t'] < 2:
            merged[-1]['why'] += ' · ' + p['why']
        else:
            merged.append(p)
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--skip', nargs='*', default=[])
    parser.add_argument('--md')
    args = parser.parse_args()
    md = ['# Puntos para revisar a oído', '',
          'Abre la canción en el editor y pulsa **N** para ir al siguiente punto (Shift+N: al anterior).', '']
    for folder in sorted(Path(args.songs).iterdir()):
        if not (folder / 'songmaker.json').exists() or folder.name in args.skip:
            continue
        found = points(folder)
        (folder / REVIEW_FILE).write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f"{folder.name}: {len(found)}", flush=True)
        if found:
            md += [f"## {folder.name} ({len(found)})", '']
            md += [f"- [ ] **{int(p['t'] // 60)}:{p['t'] % 60:04.1f}** {p['why']}" for p in found] + ['']
    if args.md:
        Path(args.md).write_text('\n'.join(md) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
