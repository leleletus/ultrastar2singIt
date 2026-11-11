"""Adds #GENRE to the songs that have none, from the iTunes store (only when artist and title match exactly).

Usage:
    python tools/fix_genres.py <songs folder>            # only lists
    python tools/fix_genres.py <songs folder> --apply    # writes #GENRE (a .bak of the txt is kept)

Without #GENRE every song was "Pop" in the game. The store genre ("Hip-Hop/Rap", "R&B/Soul", "Latin", "Country",
"Dance", "Alternative"...) is written as it is; the converter turns it into a genre of the game (Let's Sing 2026:
HipHop, RnB, Latin, Country, Electro, Rock...). Songs that already have #GENRE are never changed.
"""
import argparse
import collections
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ConvertFiles  # noqa: E402
import UltrastarToSingit  # noqa: E402
from fix_covers import _simple, COMPILATION  # noqa: E402

# store genres that say nothing about the style of the song
NEUTRAL = {'soundtrack', 'singer/songwriter', 'music', 'vocal', 'children\'s music', 'holiday', 'christmas',
           'christmas: pop', 'easy listening', 'comedy', 'world'}


def store_genre(artist, title):
    """Most common primary genre of the song in the store (albums of the artist, no compilations), or None."""
    query = urllib.parse.urlencode({'term': f"{artist} {title}", 'entity': 'song', 'limit': 50})
    request = urllib.request.Request(f"https://itunes.apple.com/search?{query}",
                                     headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        results = json.loads(response.read().decode('utf-8')).get('results', [])
    want_title, first_artist = _simple(title), _simple(re.split(r' feat\.? | ft\.? |,| & | x | \+ ', artist)[0])
    genres = collections.Counter()
    for r in results:
        if _simple(r.get('trackName', '')) != want_title or first_artist not in _simple(r.get('artistName', '')):
            continue
        if (r.get('collectionArtistName') or '').lower() == 'various artists' or \
                COMPILATION.search(r.get('collectionName', '')):
            continue
        genre = (r.get('primaryGenreName') or '').strip()
        if genre and genre.lower() not in NEUTRAL:
            genres[genre] += 1
    return genres.most_common(1)[0][0] if genres else None


def set_genre(txt_path, genre):
    raw = txt_path.read_bytes()
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
    lines.insert(insert_at, f"#GENRE:{genre}")
    backup = txt_path.with_name(txt_path.name + '.bak')
    if not backup.exists():
        backup.write_bytes(raw)
    tmp = txt_path.with_name(txt_path.name + '.tmp')
    tmp.write_text(newline.join(lines) + (newline if text.endswith(('\n', '\r')) else ''), encoding=encoding,
                   newline='')
    os.replace(tmp, txt_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    found, missing = collections.Counter(), []
    for d in sorted(p for p in Path(args.songs).iterdir() if p.is_dir()):
        txts = [p for p in d.iterdir() if p.suffix.lower() == '.txt']
        if not txts:  # not a song (e.g. _songmaker_downloads)
            continue
        txt = ConvertFiles.choose_txt_file(txts)
        data = UltrastarToSingit.parse_file(txt)
        if data.get('GENRE', '').strip():
            continue
        try:
            genre = store_genre(data.get('ARTIST', ''), data.get('TITLE', ''))
        except Exception as e:
            genre = None
            print(f"   store error for {d.name}: {e}")
        time.sleep(3)  # the store limits the requests per minute
        if not genre:
            missing.append(d.name)
            continue
        found[genre] += 1
        print(f"   {genre:20} -> {ConvertFiles.match_genre({'GENRE': genre}, '2026'):8} {d.name}", flush=True)
        if args.apply:
            set_genre(txt, genre)
    print(f"\n{sum(found.values())} genre(s) found {dict(found)}; {'written' if args.apply else 'run again with --apply'}")
    print(f"{len(missing)} without a genre in the store (they stay Pop): {missing[:30]}")


if __name__ == '__main__':
    main()
