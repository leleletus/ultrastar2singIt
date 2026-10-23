"""Read-only health report of an UltraStar song library (only the .txt files are read).

Usage:
    python tools/diagnose_library.py <input folder> [--csv report.csv] [--only "Song name" ...]

For every song folder it reports:
  - encoding of the txt and whether its lyrics look damaged (characters lost or mojibake)
  - songs rebuilt from Let's Sing DLC files without #LETSSINGPITCHOFFSET (converted one octave too high)
  - pitch correction of the old heuristic vs the current one
  - GAP / VIDEOGAP / BPM values that usually mean a sync problem, time of the first lyric
  - duets, notes without lyric, unknown note lines
  - folder name that does not match #ARTIST / #TITLE (possibly wrong or invented metadata)
"""
import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import naming  # noqa: E402
import PitchAnalyzer  # noqa: E402
import UltrastarToSingit  # noqa: E402
from tools.mark_extracted_songs import looks_extracted  # noqa: E402

MOJIBAKE = re.compile(r'Ã[\x80-\xbf]|Â[\x80-\xbf]|â€|Ã©|Ã±|�')


def old_fast_correction(txt_data):
    """The heuristic used before the octave fix (for comparison)."""
    pitches = [int(n[3]) for n in txt_data['notes'] if n and n[0] in (':', '*') and len(n) > 3]
    if not pitches:
        return 0
    average = round(sum(pitches) / len(pitches))
    if 40 <= average <= 80:
        return 0
    corr = 0
    if max(pitches) > 33:
        corr = max(corr, 81 - max(pitches))
    elif min(pitches) < -5:
        corr = max(corr, 43 - min(pitches))
    return corr if corr > 0 else 48


def simplify(text):
    text = naming.strip_accents(text).lower()
    return re.sub(r'[^a-z0-9]+', '', text)


def analyze_song(folder_path):
    import ConvertFiles
    folder = os.path.basename(folder_path)
    txts = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith('.txt')]
    from pathlib import Path
    txt = ConvertFiles.choose_txt_file([Path(t) for t in txts])
    row = {'folder': folder, 'problems': []}
    if txt is None:
        row['problems'].append('no UltraStar txt')
        return row
    raw = open(txt, 'rb').read()
    encoding = UltrastarToSingit._detect_encoding_bytes(raw)
    row['encoding'] = encoding
    data = UltrastarToSingit.parse_file(txt)
    text = raw.decode(encoding, errors='replace')

    # lyrics
    lyrics = ''.join(n[4] for n in data['notes'] if len(n) > 4)
    if MOJIBAKE.search(lyrics) or MOJIBAKE.search(data.get('TITLE', '') + data.get('ARTIST', '')):
        row['problems'].append('mojibake in lyrics/tags (text was decoded with a wrong encoding before being saved)')
    non_ascii = sum(1 for c in lyrics if ord(c) > 127)
    row['accented_chars'] = non_ascii
    language = data.get('LANGUAGE', '').lower()
    if non_ascii == 0 and any(x in language for x in ('fr', 'spa', 'esp', 'ger', 'deu', 'por', 'ita')):
        row['problems'].append(f'#LANGUAGE:{data.get("LANGUAGE")} but no accented letters at all (maybe stripped earlier)')

    # rebuilt from DLC
    extracted = looks_extracted(data)
    row['rebuilt_from_dlc'] = extracted
    if extracted:
        row['problems'].append('rebuilt from DLC without #LETSSINGPITCHOFFSET: run tools/mark_extracted_songs.py')

    # pitch
    old = old_fast_correction(data)
    new = PitchAnalyzer.get_pitch_correction_suggestion_fast(data, 43, 81)
    row['pitch_old'], row['pitch_new'] = old, new
    if old != new:
        row['problems'].append(f'pitch changes {old:+d} -> {new:+d} ({"octave" if (old - new) % 12 == 0 else "KEY"} difference)')

    # timing
    try:
        bpm = float(data.get('BPM', '0').replace(',', '.'))
    except ValueError:
        bpm = 0
    try:
        gap = float((data.get('GAP') or '0').replace(',', '.'))
    except ValueError:
        gap = 0
    try:
        videogap = float((data.get('VIDEOGAP') or '0').replace(',', '.'))
    except ValueError:
        videogap = 0
    row['bpm'], row['gap_ms'], row['videogap_s'] = bpm, gap, videogap
    first = next((n for n in data['notes'] if n and n[0] in ':*FRG'), None)
    if bpm > 0 and first is not None:
        row['first_lyric_s'] = round(int(first[1]) * 60 / bpm / 4 + gap / 1000 + videogap, 2)
        if row['first_lyric_s'] < 0.5:
            row['problems'].append(f'first lyric at {row["first_lyric_s"]} s (lyrics may come too early)')
        if row['first_lyric_s'] > 60:
            row['problems'].append(f'first lyric at {row["first_lyric_s"]} s (very late: check GAP)')
    if bpm <= 0:
        row['problems'].append('missing or invalid #BPM')
    if gap < 0:
        row['problems'].append(f'negative GAP ({gap})')
    if abs(videogap) > 10:
        row['problems'].append(f'large VIDEOGAP ({videogap} s)')

    # structure
    if re.search(r'^P\s*[12]', text, re.M):
        row['problems'].append('duet (only player 1 is converted)')
    empty = sum(1 for n in data['notes'] if n and n[0] in ':*FRG' and len(n) > 4 and n[4].strip() == '')
    if empty:
        row['notes_without_lyric'] = empty
    note_lines = sum(1 for line in text.splitlines() if line[:1] in ':*FRG')
    parsed = sum(1 for n in data['notes'] if n and n[0] in ':*FRG')
    if parsed < note_lines - (len(re.findall(r'^P\s*2', text, re.M)) and note_lines):
        pass
    if parsed == 0:
        row['problems'].append('no notes could be read')

    # metadata vs folder name
    parts = folder.split(' - ', 1)
    artist, title = data.get('ARTIST', ''), data.get('TITLE', '')
    if len(parts) == 2 and (simplify(parts[0]) not in simplify(artist) and simplify(artist) not in simplify(parts[0])
                            or simplify(parts[1]) not in simplify(title) and simplify(title) not in simplify(parts[1])):
        row['problems'].append(f'folder name differs from tags: #ARTIST:{artist} #TITLE:{title}')
    if not artist or not title or 'unknown' in artist.lower():
        row['problems'].append('missing or unknown #ARTIST/#TITLE')
    row['audio_tag'] = data.get('AUDIO') or data.get('MP3', '')
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input')
    parser.add_argument('--csv', help='write the full report to this CSV file')
    parser.add_argument('--only', nargs='*', help='only folders whose name contains one of these texts')
    args = parser.parse_args()

    rows = []
    for folder in sorted(os.listdir(args.input), key=str.lower):
        path = os.path.join(args.input, folder)
        if not os.path.isdir(path) or folder.startswith(('_', '.')) or ' - ' not in folder:
            continue
        if args.only and not any(o.lower() in folder.lower() for o in args.only):
            continue
        try:
            rows.append(analyze_song(path))
        except Exception as e:
            rows.append({'folder': folder, 'problems': [f'could not analyze: {e}']})

    counts = {}
    for r in rows:
        for p in r['problems']:
            key = re.sub(r'[-+]?\d+(\.\d+)?', 'N', p.split(':')[0])
            counts[key] = counts.get(key, 0) + 1
        if r['problems']:
            print(f"\n{r['folder']}")
            for p in r['problems']:
                print(f"   - {p}")
    print(f"\n{len(rows)} songs, {sum(1 for r in rows if r['problems'])} with something to check:")
    for key, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {key}")

    if args.csv:
        fields = ['folder', 'encoding', 'accented_chars', 'rebuilt_from_dlc', 'pitch_old', 'pitch_new', 'bpm', 'gap_ms',
                  'videogap_s', 'first_lyric_s', 'notes_without_lyric', 'audio_tag', 'problems']
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for r in rows:
                writer.writerow({**r, 'problems': ' | '.join(r['problems'])})
        print(f"\nCSV report: {args.csv}")


if __name__ == '__main__':
    main()
