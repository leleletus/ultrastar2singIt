"""Renames song folders safely (wrong artist/title), keeping every converted file.

Usage:
    python tools/rename_songs.py <songs folder> <corrections.csv>            # only shows what would change
    python tools/rename_songs.py <songs folder> <corrections.csv> --apply    # renames

corrections.csv columns:  folder;artist;title   (semicolon separated, UTF-8)
  folder  current folder name
  artist  correct artist
  title   correct title

For each row: #ARTIST/#TITLE are corrected in the txt (a .bak copy is kept), the folder becomes
"Artist - Title", and every cached file of the converter is renamed to the new song ID. Converted .bk2
videos are moved, never deleted or re-encoded. Nothing happens if the target folder already exists.
"""
import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import naming  # noqa: E402
import UltrastarToSingit  # noqa: E402

FORBIDDEN = r'[<>:"/\\|?*]'


def safe_folder_name(artist, title):
    name = f"{artist} - {title}"
    return re.sub(FORBIDDEN, '', name).rstrip(' .')


def retag_txt(path, artist, title, apply):
    with open(path, 'rb') as f:
        raw = f.read()
    encoding = UltrastarToSingit._detect_encoding_bytes(raw)
    if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8'
    text = raw.decode(encoding)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    found = set()
    for i, line in enumerate(lines):
        key = line.split(':', 1)[0].upper()
        if key == '#ARTIST':
            lines[i] = f"#ARTIST:{artist}"
            found.add(key)
        elif key == '#TITLE':
            lines[i] = f"#TITLE:{title}"
            found.add(key)
    for key, value in (('#TITLE', title), ('#ARTIST', artist)):
        if key not in found:
            lines.insert(0, f"{key}:{value}")
    if apply:
        if not os.path.exists(path + '.bak'):
            with open(path + '.bak', 'wb') as f:
                f.write(raw)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding=encoding, newline='') as f:
            f.write(newline.join(lines) + newline)
        os.replace(tmp, path)


def rename_song(songs_dir, folder, artist, title, apply):
    old_dir = os.path.join(songs_dir, folder)
    if not os.path.isdir(old_dir):
        return f"SKIP {folder}: folder not found"
    new_folder = safe_folder_name(artist, title)
    new_dir = os.path.join(songs_dir, new_folder)
    if new_folder != folder and os.path.exists(new_dir):
        return f"SKIP {folder}: '{new_folder}' already exists (duplicate song?)"

    old_ids = naming.all_name_ids(folder.rstrip('.'))
    new_id = naming.construct_name_id_from_directory_name(new_folder)
    renames = []
    for name in sorted(os.listdir(old_dir)):
        for old_id in old_ids:
            if naming.is_generated_file(name, [old_id]) and name.startswith(old_id):
                target = new_id + name[len(old_id):]
                if target != name and not os.path.exists(os.path.join(old_dir, target)):
                    renames.append((name, target))
                break
    txt_files = [os.path.join(old_dir, f) for f in os.listdir(old_dir) if f.lower().endswith('.txt')]

    report = [f"{folder}  ->  {new_folder}   (ID {old_ids[0]} -> {new_id})"]
    report += [f"      {a} -> {b}" for a, b in renames]
    if apply:
        for txt in txt_files:
            retag_txt(txt, artist, title, True)
        for a, b in renames:
            os.rename(os.path.join(old_dir, a), os.path.join(old_dir, b))
        if new_folder != folder:
            os.rename(old_dir, new_dir)
    return '\n'.join(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('corrections')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with open(args.corrections, encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f, delimiter=';') if r.get('folder') and not r['folder'].startswith('#')]
    for row in rows:
        print(rename_song(args.songs, row['folder'].strip(), row['artist'].strip(), row['title'].strip(), args.apply))
    print(f"\n{len(rows)} correction(s) {'applied' if args.apply else 'checked (run again with --apply)'}.")


if __name__ == '__main__':
    main()
