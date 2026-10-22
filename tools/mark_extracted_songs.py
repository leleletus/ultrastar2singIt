"""Marks songs rebuilt from Let's Sing DLC files (LetSing_ExtractorPro / reverse_vxla / Tools → Unpack)
with #LETSSINGPITCHOFFSET:36, so the converter restores their original pitches exactly.

Songs extracted before that tag existed were converted one octave too high (-36 when extracting,
+48 when converting back).

Usage:
    python tools/mark_extracted_songs.py <input folder>            # only lists what would change
    python tools/mark_extracted_songs.py <input folder> --apply    # adds the tag (keeps a .bak copy)

Only the .txt files are modified; converted videos and the rest of the cache are not touched
(the lyrics/notes .vxla is regenerated automatically on the next conversion).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import UltrastarToSingit  # noqa: E402
from PitchAnalyzer import PITCH_OFFSET_TAG  # noqa: E402

EXTRACTOR_TAGS = {'TITLE', 'ARTIST', 'YEAR', 'BPM', 'GAP', 'MP3', 'VIDEO', 'COVER'}
EXTRACTOR_OFFSET = 36


def looks_extracted(txt_data) -> bool:
    """Footprint of the extractors: BPM 300, only their own tags, GAP 0/10 or none, only ':'/'F' notes."""
    tags = {k for k in txt_data if k.isupper()}
    if PITCH_OFFSET_TAG in tags or not tags <= EXTRACTOR_TAGS:
        return False
    if txt_data.get('BPM', '').replace(',', '.') not in ('300', '300.0', '300.00'):
        return False
    if txt_data.get('GAP', '0') not in ('0', '10'):
        return False
    note_types = {n[0] for n in txt_data['notes'] if n and n[0] not in ('-', 'E')}
    return bool(note_types) and note_types <= {':', 'F'}


def add_tag(txt_path) -> None:
    with open(txt_path, 'rb') as f:
        raw = f.read()
    encoding = UltrastarToSingit._detect_encoding_bytes(raw)
    if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8'
    text = raw.decode(encoding)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith('#'):
            insert_at = i + 1
        elif line.strip():
            break
    lines.insert(insert_at, f"#{PITCH_OFFSET_TAG}:{EXTRACTOR_OFFSET}")

    backup = txt_path + '.bak'
    if not os.path.exists(backup):
        with open(backup, 'wb') as f:
            f.write(raw)
    tmp = txt_path + '.tmp'
    with open(tmp, 'w', encoding=encoding, newline='') as f:
        f.write(newline.join(lines) + newline)
    os.replace(tmp, txt_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', help='Input folder with "Artist - Title" song folders')
    parser.add_argument('--apply', action='store_true', help='Add the tag (default: only list)')
    args = parser.parse_args()

    found = []
    for folder in sorted(os.listdir(args.input)):
        song_dir = os.path.join(args.input, folder)
        if not os.path.isdir(song_dir) or folder.startswith(('_', '.')):
            continue
        for name in sorted(os.listdir(song_dir)):
            if not name.lower().endswith('.txt'):
                continue
            txt_path = os.path.join(song_dir, name)
            try:
                if looks_extracted(UltrastarToSingit.parse_file(txt_path)):
                    found.append(txt_path)
            except Exception as e:
                print(f"  ! could not read {txt_path}: {e}")

    for txt_path in found:
        print(("marked: " if args.apply else "would mark: ") + os.path.relpath(txt_path, args.input))
        if args.apply:
            add_tag(txt_path)
    print(f"\n{len(found)} extracted song(s) {'marked' if args.apply else 'found (run again with --apply to mark them)'}.")


if __name__ == '__main__':
    main()
