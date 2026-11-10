"""Gives the real release year to songs rebuilt from DLCs whose #YEAR is a placeholder (the old extractor wrote the
year of the DLC, mostly 2020).

Usage:
    python tools/fix_years.py <songs folder> --extracted <extracted games>            # only lists
    python tools/fix_years.py <songs folder> --extracted <extracted games> --apply    # writes #YEAR (.bak kept)

Sources, in this order:
  1. the official data of the extracted games (Songs.tsv / SongsDLC.tsv, *_meta.xml, songs_xx.json), found
     through the song's own official vxla (letssing_original.vxla);
  2. MusicBrainz: first release year of the recording, only when title and artist match;
  3. the iTunes store: earliest release year of the same title and artist.
Only songs with an official vxla are checked; --year limits it to the songs with that #YEAR (default 2020).
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import UltrastarToSingit  # noqa: E402
import naming  # noqa: E402


def simple(text):
    text = unicodedata.normalize('NFKD', text.lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'\(.*?\)|\[.*?\]', ' ', text)
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', text.replace('&', ' and ')).split())


def official_years(extracted):
    """{official song ID: year} from every official file of the extracted games."""
    years = {}
    for tsv in glob.glob(os.path.join(extracted, '**', 'Songs*.tsv'), recursive=True):
        try:
            with open(tsv, encoding='utf-8-sig', errors='replace') as f:
                for row in csv.DictReader(f, delimiter='\t'):
                    if row.get('ID') and str(row.get('YEAR', '')).isdigit():
                        years.setdefault(row['ID'], int(row['YEAR']))
        except (OSError, csv.Error):
            pass
    for meta in glob.glob(os.path.join(extracted, '**', '*_meta.xml'), recursive=True):
        try:
            root = ET.parse(meta).getroot()
            sid, year = root.findtext('Id'), root.findtext('Year')
            if sid and year and year.strip().isdigit():
                years.setdefault(sid.strip(), int(year))
        except (OSError, ET.ParseError):
            pass
    for js in glob.glob(os.path.join(extracted, '**', 'songs_*.json'), recursive=True):
        try:
            for song in json.load(open(js, encoding='utf-8-sig')).get('songs', []):
                if song.get('id') and str(song.get('year', '')).isdigit():
                    years.setdefault(str(song['id']), int(song['year']))
        except (OSError, ValueError):
            pass
    return years


def musicbrainz_year(artist, title):
    """Earliest release year of the recording, when MusicBrainz has one with the same title and artist."""
    first_artist = simple(re.split(r' feat\.? | ft\.? |,| & | x | \+ ', artist)[0])
    query = f'recording:"{title}" AND artist:"{first_artist}"'
    url = 'https://musicbrainz.org/ws/2/recording/?' + urllib.parse.urlencode({'query': query, 'fmt': 'json',
                                                                               'limit': 25})
    request = urllib.request.Request(url, headers={'User-Agent': 'LetsSingUltraStarConverter/1.0 (song years)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode('utf-8'))
    years = []
    for rec in data.get('recordings', []):
        artists = simple(' '.join(c.get('name', '') for c in rec.get('artist-credit', []) if isinstance(c, dict)))
        if simple(rec.get('title', '')) == simple(title) and first_artist in artists:
            date = rec.get('first-release-date', '')
            if re.match(r'\d{4}', date):
                years.append(int(date[:4]))
    return min(years) if years else None


def itunes_year(artist, title):
    """Earliest release year in the iTunes store among entries with the same title and artist (a fallback:
    the store often lists remasters and compilations, the earliest one is the closest to the original)."""
    first_artist = simple(re.split(r' feat\.? | ft\.? |,| & | x | \+ ', artist)[0])
    url = 'https://itunes.apple.com/search?' + urllib.parse.urlencode({'term': f"{artist} {title}", 'entity': 'song',
                                                                       'limit': 50})
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        results = json.loads(response.read().decode('utf-8')).get('results', [])
    years = [int(r['releaseDate'][:4]) for r in results
             if simple(r.get('trackName', '')) == simple(title) and first_artist in simple(r.get('artistName', ''))
             and re.match(r'\d{4}', r.get('releaseDate', ''))]
    return min(years) if years else None


def with_retries(function, *args):
    """MusicBrainz answers 503 when asked too often: wait and try again."""
    for attempt in range(4):
        try:
            return function(*args)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def set_year(txt_path, year):
    raw = txt_path.read_bytes()
    encoding = UltrastarToSingit._detect_encoding_bytes(raw)
    if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8'
    text = raw.decode(encoding)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.upper().startswith('#YEAR:'):
            lines[i] = f"#YEAR:{year}"
            break
    else:
        lines.insert(next((i for i, l in enumerate(lines) if not l.startswith('#')), 0), f"#YEAR:{year}")
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
    parser.add_argument('--extracted', required=True)
    parser.add_argument('--year', default='2020', help="only songs whose #YEAR is this placeholder (\"\": no year)")
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    years = official_years(args.extracted)
    vxla_ids = {}
    for f in Path(args.extracted).rglob('*.vxla'):
        vxla_ids.setdefault(hashlib.sha1(f.read_bytes()).hexdigest(), re.sub(r'(_duet|_feat)$', '', f.stem))
    print(f"official years known: {len(years)}")

    placeholder = int(args.year) if args.year.strip() else None  # --year "": songs with no #YEAR at all
    found = {'official': 0, 'musicbrainz': 0, 'itunes': 0}
    missing = []
    for d in sorted(p for p in Path(args.songs).iterdir() if p.is_dir()):
        official = d / naming.OFFICIAL_VXLA_NAME
        if not official.exists():
            continue
        txt = ConvertFiles.choose_txt_file([p for p in d.iterdir() if p.suffix.lower() == '.txt'])
        data = UltrastarToSingit.parse_file(txt)
        if data.get('YEAR', '').strip() != args.year:
            continue
        song_id = vxla_ids.get(hashlib.sha1(official.read_bytes()).hexdigest())
        year, source = years.get(song_id), 'official'
        if year is None or year == placeholder:
            source = 'musicbrainz'
            try:
                year = with_retries(musicbrainz_year, data.get('ARTIST', ''), data.get('TITLE', ''))
            except Exception as e:
                year = None
                print(f"   MusicBrainz error for {d.name}: {e}")
            time.sleep(1.1)  # MusicBrainz asks for one request per second
        if year is None or year == placeholder:
            source = 'itunes'
            try:
                year = with_retries(itunes_year, data.get('ARTIST', ''), data.get('TITLE', ''))
            except Exception as e:
                year = None
                print(f"   iTunes error for {d.name}: {e}")
        if not year or year == placeholder:
            missing.append(d.name)
            continue
        found[source] += 1
        print(f"   {year}  {d.name}  ({source}{' ' + song_id if source == 'official' else ''})")
        if args.apply:
            set_year(txt, year)
    print(f"\n{sum(found.values())} year(s) found {found}; {'written' if args.apply else 'run again with --apply'}")
    if missing:
        print(f"{len(missing)} without a reliable year (kept): {missing}")


if __name__ == '__main__':
    main()
