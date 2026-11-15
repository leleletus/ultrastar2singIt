"""After fixing a SongMaker song by ear in the sync editor (words moved, cloned, split, lengths changed): measures the
pitch of every sung note again from the voice where the note is now (a note moved in time keeps the pitch of the
place it came from), keeps the notes really sung an octave up, lists the notes that overlap and, with --checked,
marks the song as reviewed. The txt before the change is copied to <songs>/../_respaldo_songmaker/<date>_<song>/.
Convert the song afterwards (only its notes are made again; the video is kept).

Usage:
    python tools/after_review.py "<song folder>"                 # only shows what would change
    python tools/after_review.py "<song folder>" --apply         # writes the pitches
    python tools/after_review.py "<song folder>" --apply --checked   # ... and marks it as reviewed by ear
The same measure is the P key of the sync editor (selected notes, or the whole song).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

import SongMaker  # noqa: E402
import SyncModel  # noqa: E402

NOTE = re.compile(r'^([:*FRG]) (-?\d+) (\d+) (-?\d+)( .*)?$')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--checked', action='store_true', help='mark the song as reviewed by ear (songmaker.json)')
    args = parser.parse_args()
    folder = Path(args.folder)
    txt = folder / f"{folder.name}.txt"
    if not txt.exists():
        txt = sorted(folder.glob('*.txt'))[0]
    voice_path = SyncModel.voice_cache_path(str(folder))
    if not os.path.exists(voice_path):
        sys.exit("No voice analysis next to the song: open it in the sync editor and press \"Analyze voice\".")
    voice = np.load(voice_path)
    raw = txt.read_bytes()
    text = raw.decode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8')
    rows = text.split('\n')
    bpm = gap = None
    for row in rows:
        if row.upper().startswith('#BPM:'):
            bpm = float(row[5:].strip().replace(',', '.'))
        elif row.upper().startswith('#GAP:'):
            gap = float(row[5:].strip().replace(',', '.')) / 1000
    beat = 60 / (bpm * 4)
    lines, where = [[]], [[]]  # per lyrics line: (start s, end s, rap) and the row of each note
    for index, row in enumerate(rows):
        found = NOTE.match(row.rstrip('\r'))
        if found:
            start, length = int(found.group(2)), int(found.group(3))
            lines[-1].append((gap + start * beat, gap + (start + length) * beat, found.group(1) not in ':*'))
            where[-1].append(index)
        elif row.startswith('- '):
            lines.append([])
            where.append([])
    measured = SongMaker.pitches_from_voice(lines, voice['pitch'].astype(np.float32), SongMaker.load_vocals(folder))
    changed = far = 0
    for line, places, pitches in zip(lines, where, measured):
        for (start, _, _), index, midi in zip(line, places, pitches):
            if midi is None:
                continue
            found = NOTE.match(rows[index].rstrip('\r'))
            old, new = int(found.group(4)), midi - 60
            if old != new:
                changed += 1
                far += abs(old - new) > 1
                if abs(old - new) > 1:
                    print(f"   {int(start // 60)}:{start % 60:05.2f} {(found.group(5) or '').strip():12} {old:+d} -> {new:+d}")
                rows[index] = (f"{found.group(1)} {found.group(2)} {found.group(3)} {new}{found.group(5) or ''}"
                               + ('\r' if rows[index].endswith('\r') else ''))
    notes = sorted((n for line in lines for n in line), key=lambda n: n[0])
    overlaps = [(a, b) for a, b in zip(notes, notes[1:]) if b[0] < a[1] - 1e-6]
    total = sum(len(line) for line in lines)
    print(f"{folder.name}: {changed} of {total} notes change pitch ({far} by more than a semitone); "
          f"{len(overlaps)} overlap(s)")
    for a, b in overlaps:
        print(f"   overlap at {int(b[0] // 60)}:{b[0] % 60:05.2f}: the note before ends {a[1] - b[0]:.2f} s later")
    if not args.apply:
        print("Nothing written (run again with --apply).")
        return
    keep = folder.parent.parent / '_respaldo_songmaker' / f"{datetime.date.today():%Y%m%d}_{folder.name}"
    keep.mkdir(parents=True, exist_ok=True)
    shutil.copy2(txt, keep / txt.name)
    tmp = txt.with_name(txt.name + '.tmp')
    tmp.write_bytes(raw[:3] + '\n'.join(rows).encode('utf-8') if raw.startswith(b'\xef\xbb\xbf')
                    else '\n'.join(rows).encode('utf-8'))
    os.replace(tmp, txt)
    print(f"Written; the txt before is in {keep}")
    meta_path = folder / 'songmaker.json'
    if args.checked and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        meta['user_checked'] = f"{datetime.date.today():%Y-%m-%d}"
        meta_path.write_text(json.dumps(meta, indent=1), encoding='utf-8')
        print("Marked as reviewed by ear.")


if __name__ == '__main__':
    main()
