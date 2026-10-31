"""Finds whether the singers of every song are men, women or both (MusicBrainz) for the "gender" of songs_xx.json.

Usage: python tools/artist_genders.py <songs folder>

Writes <songs folder>/_artist_genders.json ({artist as written in #ARTIST: "Men" | "Women" | "Both"}); the converter
reads it (Let's Sing 2026 only). Already known artists are not asked again. Rules, chosen so a song is never left out
of a filter it belongs to:
  - a solo singer: their gender in MusicBrainz;
  - several singers ("A feat. B", "A & B"): one gender if all have it, else Both;
  - groups, bands and anything not found for sure: Both (as every song was before).
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import UltrastarToSingit  # noqa: E402

CACHE_NAME = '_artist_genders.json'
SPLIT = re.compile(r'\s+(?:feat\.?|ft\.?|featuring|with|x|X|vs\.?|y|and)\s+|\s*[,&+]\s*|\s+/\s+')


def simple(text):
    text = unicodedata.normalize('NFKD', text.lower())
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


def ask(name):
    """MusicBrainz artist with exactly this name: ('person', 'male'/'female'/None) or ('group', None) or None."""
    url = 'https://musicbrainz.org/ws/2/artist/?' + urllib.parse.urlencode({'query': f'artist:"{name}"',
                                                                            'fmt': 'json', 'limit': 5})
    request = urllib.request.Request(url, headers={'User-Agent': 'LetsSingUltraStarConverter/1.0 (song singers)'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    time.sleep(1.1)  # one request per second
    for artist in data.get('artists', []):
        names = [artist.get('name', '')] + [a.get('name', '') for a in artist.get('aliases', []) or []]
        if int(artist.get('score', 0)) >= 95 and simple(name) in {simple(n) for n in names}:
            kind = (artist.get('type') or '').lower()
            if kind == 'person':
                return 'person', (artist.get('gender') or '').lower() or None
            return 'group', None
    return None


def featured(title):
    """Singers named in a title: "Blame (feat. John Newman)" -> ["John Newman"]."""
    m = re.search(r'[(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+([^)\]]+)[)\]]', title, re.I)
    return [p.strip() for p in SPLIT.split(m.group(1)) if p.strip()] if m else []


def gender_of(artist, known):
    """Men / Women / Both for an #ARTIST value; known caches single names."""
    def one(name):
        if name not in known:
            try:
                known[name] = ask(name)
            except Exception as e:
                print(f"   MusicBrainz error for {name}: {e}")
                return None
        return known[name]

    whole = one(artist)
    parts = [artist] if whole else [p.strip() for p in SPLIT.split(artist) if p.strip()]
    genders = set()
    for part in parts:
        found = whole if part == artist else one(part)
        if not found or found[0] != 'person' or found[1] not in ('male', 'female'):
            return 'Both'
        genders.add(found[1])
    return {'male': 'Men', 'female': 'Women'}[genders.pop()] if len(genders) == 1 else 'Both'


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    songs = Path(sys.argv[1])
    cache = songs / CACHE_NAME
    result = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {}
    known = {}
    artists = set()
    for d in songs.iterdir():
        if d.is_dir():
            try:
                txt = ConvertFiles.choose_txt_file([p for p in d.iterdir() if p.suffix.lower() == '.txt'])
                data = UltrastarToSingit.parse_file(txt)
                artists.add(data.get('ARTIST', '').strip())
                artists.update(featured(data.get('TITLE', '')))  # "Titanium (feat. Sia)": Sia sings too
            except Exception:
                continue
    todo = sorted(a for a in artists if a and a not in result)
    print(f"{len(artists)} artists, {len(todo)} to look up")
    for n, artist in enumerate(todo, 1):
        result[artist] = gender_of(artist, known)
        print(f"[{n}/{len(todo)}] {result[artist]:5}  {artist}", flush=True)
        tmp = cache.with_suffix('.tmp')
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
        os.replace(tmp, cache)
    counts = {}
    for g in result.values():
        counts[g] = counts.get(g, 0) + 1
    print(f"=== done: {counts} -> {cache}")


if __name__ == '__main__':
    main()
