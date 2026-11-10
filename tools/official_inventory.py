"""Inventory of the songs of extracted Let's Sing games (tools/extract_switch_songs.py) against what the library
already has: for every song, which game and pack it comes from, and whether the library has it already as an
official song (letssing_original.vxla, with the game it came from), as a song made by us (USDB / SongMaker) or not
at all. Decides with the user's rules: the official song beats one made by us; between two official versions the
one from the newest game wins (an identical vxla changes nothing). Only reads; writes a report and a JSON plan.

Usage:
    python tools/official_inventory.py <extracted folder> --songs <library> --megapack <megapack folder>
        [--md report.md] [--plan plan.json]
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

# release year of every game (its songs' "version"); the numbered editions are the same years as the yearly ones
GAME_YEAR = {"Let's Sing 2014": 2013, "Let's Sing 2015": 2014, "Let's Sing 2016": 2015, "Let's Sing 2017": 2016,
             "Let's Sing 10": 2017, "Let's Sing 2018": 2017, "Let's Sing 11": 2018, "Let's Sing 2019": 2018,
             "Let's Sing 12": 2019, "Let's Sing 2020": 2019, "Let's Sing Country": 2019, "Let's Sing 13": 2020,
             "Let's Sing 2021": 2020, "Let's Sing Queen": 2020, "Let's Sing 2022": 2021, "Let's Sing ABBA": 2022,
             "Let's Sing 2023": 2022, "Let's Sing 2024": 2023, "Let's Sing 2025": 2024, "Let's Sing 2026": 2025}


def game_of(text):
    for name in sorted(GAME_YEAR, key=len, reverse=True):
        if name in text:
            return name
    return None


def norm(text):
    text = unicodedata.normalize('NFKD', (text or '').lower().replace('&', ' and '))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'\((feat|ft)[^)]*\)|\b(feat|ft)\.?\s.*$', '', text)
    return re.sub(r'[^a-z0-9]', '', text)


def first_word(artist):
    """Normalized first word of an artist ("Calvin Harris ft. Ellie Goulding" -> "calvin")."""
    words = re.split(r'\s+', unicodedata.normalize('NFKD', (artist or '').lower()).strip())
    return norm(words[0]) if words and words[0] else ''


def vxla_meta(path):
    meta = {}
    try:
        for layer in ET.parse(path).getroot().findall('IntervalLayer'):
            if layer.get('name') == 'meta':
                for interval in layer.findall('Interval'):
                    value = interval.get('value', '')
                    for key in ('TITLE', 'ARTIST', 'YEAR'):
                        if value.startswith(key + ': '):
                            meta[key.lower()] = value[len(key) + 2:].strip()
    except (ET.ParseError, OSError):
        pass
    return meta


def digest(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def tsv_rows(romfs):
    """{song id: (artist, title, year)} from Songs.tsv / SongsDLC.tsv when the game has them."""
    out = {}
    for tsv in list(romfs.rglob('Songs.tsv')) + list(romfs.rglob('SongsDLC.tsv')) + list(romfs.rglob('*SongsExport.tsv')):
        with open(tsv, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                if row.get('ID'):
                    out[row['ID']] = (row.get('ARTIST', '').replace('_', ' '), row.get('TITLE', ''), row.get('YEAR', ''))
    return out


def unity_strings(raw):
    """The strings of a Unity object in order (int32 length, UTF-8 bytes, padded to 4)."""
    import struct
    out, i = [], 0
    while i + 4 <= len(raw):
        n = struct.unpack_from('<i', raw, i)[0]
        if 1 <= n <= 300 and i + 4 + n <= len(raw):
            chunk = raw[i + 4:i + 4 + n]
            try:
                text = chunk.decode('utf-8')
            except UnicodeDecodeError:
                text = None
            if text and text.isprintable():
                out.append(text)
                i += 4 + n + (-n % 4)
                continue
        i += 4
    return out


def unity_song_names(romfs, ids):
    """{song id: (artist, title, '')} from the game's GameSongDatabase (Unity MonoBehaviour), for the games that
    keep their song list there instead of a .tsv (Let's Sing 11 and 12). Needs UnityPy; {} without it."""
    data_dir = next((p.parent for p in romfs.rglob('resources.assets')), None)
    if data_dir is None:
        return {}
    try:
        import UnityPy
    except ImportError:
        return {}
    out = {}
    env = UnityPy.load(str(data_dir))
    for obj in env.objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        raw = obj.get_raw_data()
        if b'GameSongDatabase' not in raw[:200]:
            continue
        strings = unity_strings(raw)
        for k, text in enumerate(strings):
            if text in ids and k + 2 < len(strings) and text not in out:
                out[text] = (strings[k + 1].strip(), strings[k + 2].strip(), '')
    return out


def dlc_meta(romfs):
    """{song id: (artist, title, year)} from the DLC packs' <id>_meta.xml."""
    out = {}
    for meta in romfs.rglob('*_meta.xml'):
        try:
            root = ET.parse(meta).getroot()
        except ET.ParseError:
            continue
        sid = (root.findtext('Id') or meta.name[:-len('_meta.xml')]).strip()
        artist = (root.findtext('Artist') or '').strip()
        feat = (root.findtext('Feat') or '').strip()
        if feat:
            artist = f"{artist} feat. {feat.replace('Feat.', '').strip()}"
        out[sid] = (artist, (root.findtext('Title') or '').strip(), (root.findtext('Year') or '').strip())
    return out


def wii_songs(root):
    """Songs of Wii discs extracted with wit (files/common/vxla, files/common/audio, files/common/textures/covers,
    files/wii/videos/*.mo, and the game's song list files/common/level/SingTheHits.db)."""
    import sqlite3
    songs = []
    for db in sorted(Path(root).glob('*/files/common/level/SingTheHits.db')):
        base = db.parents[2]
        disc = base.parent.name
        con = sqlite3.connect(str(db))
        con.text_factory = lambda b: b.decode('utf-8', 'replace')
        names = {a: (artist, title, str(year or ''), genre) for a, artist, title, year, genre in
                 con.execute('select AssetName, Artist, Title, Year, Genre from Songs')}
        for vxla in sorted((base / 'common' / 'vxla').glob('*.vxla')):
            if vxla.stem.upper().endswith('_DUET') or vxla.stem not in names:
                continue
            artist, title, year, genre = names[vxla.stem]
            songs.append({'id': vxla.stem, 'artist': artist, 'title': title, 'year': year, 'game': game_of(disc),
                          'pack': disc, 'vxla': str(vxla), 'songs_dir': str(base), 'platform': 'wii'})
    return songs


def extracted_songs(root):
    """[{id, artist, title, year, game, pack, vxla, songs_dir}] of every song of every extracted NSP."""
    songs = []
    for done in sorted(Path(root).glob('*/.extraction_done')):
        romfs = done.parent / 'romfs'
        pack = done.parent.name
        game = game_of(pack)
        vxlas = [v for v in sorted(romfs.rglob('*.vxla')) if v.parent.name == 'vxla'
                 and not v.stem.startswith('Fake') and not v.stem.upper().endswith('_DUET')]
        names = tsv_rows(romfs)
        names.update(dlc_meta(romfs))
        missing = {v.stem for v in vxlas} - set(names)
        if missing:
            names.update(unity_song_names(romfs, missing))
        for vxla in vxlas:
            sid = vxla.stem
            meta = vxla_meta(vxla)
            artist, title, year = names.get(sid, (meta.get('artist', ''), meta.get('title', sid), meta.get('year', '')))
            songs.append({'id': sid, 'artist': artist or meta.get('artist', ''), 'title': title or sid,
                          'year': year, 'game': game, 'pack': pack, 'vxla': str(vxla),
                          'songs_dir': str(vxla.parent.parent)})
    return songs


def library(songs_dir, megapack):
    """{key: {...}} of the library's songs: by song ID (official ones) and by artist+title."""
    mega = {}
    db = Path(megapack).parent / 'songs_database.json'
    if db.exists():
        for x in json.load(open(db, encoding='utf-8')):
            mega[x['id'].lower()] = re.sub(r' \(.*\)$', '', x['source'])
    mega_digest = {}
    vx = Path(megapack) / 'Songs' / 'vxla'
    if vx.exists():
        for f in vx.glob('*.vxla'):
            mega_digest[digest(f)] = f.stem
    by_title, by_id = {}, {}
    for folder in sorted(Path(songs_dir).iterdir()):
        if not folder.is_dir() or folder.name.startswith(('_', '.')):
            continue
        artist, _, title = folder.name.partition(' - ')
        official = folder / 'letssing_original.vxla'
        entry = {'folder': folder.name, 'kind': 'songmaker' if (folder / 'songmaker.json').exists() else 'usdb'}
        if official.exists():
            d = digest(official)
            sid = mega_digest.get(d)
            entry.update(kind='oficial', id=sid, game=mega.get((sid or '').lower()), digest=d)
            if sid:
                by_id[sid.lower()] = entry
        entry['artist_norm'] = norm(artist)
        by_title[norm(artist) + '|' + norm(title)] = entry
        by_title.setdefault('|' + norm(title), []).append(entry)
    return by_id, by_title, mega


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('extracted', nargs='+', help='folders of extracted Switch games and/or Wii discs')
    parser.add_argument('--songs', required=True)
    parser.add_argument('--megapack', required=True)
    parser.add_argument('--md')
    parser.add_argument('--plan')
    args = parser.parse_args()
    found = [s for root in args.extracted for s in extracted_songs(root) + wii_songs(root)]
    # the same song in several packs of these games: the newest game's copy
    best = {}
    for s in found:  # same song: same title and same first word of the artist (IDs can differ between games)
        key = norm(s['title']) + '|' + first_word(s['artist'])
        if key not in best or GAME_YEAR.get(s['game'], 0) > GAME_YEAR.get(best[key]['game'], 0):
            best[key] = s
    by_id, by_title, mega = library(args.songs, args.megapack)
    plan = {'nuevas': [], 'reemplazar_hecha_por_nosotros': [], 'reemplazar_oficial_mas_vieja': [],
            'ya_esta_igual_o_mas_nueva': []}
    for key, s in sorted(best.items(), key=lambda kv: (kv[1]['artist'].lower(), kv[1]['title'].lower())):
        have = by_id.get(s['id'].lower()) or by_title.get(norm(s['artist']) + '|' + norm(s['title']))
        if not have:  # same title written another way: only with the same artist ("Magic" of Coldplay is not Selena's)
            word = first_word(s['artist'])
            have = next((e for e in by_title.get('|' + norm(s['title']), [])
                         if word and (word in e['artist_norm'] or e['artist_norm'].startswith(word[:4]))), None)
        in_mega = mega.get(s['id'].lower())
        s = dict(s, folder=have['folder'] if have else None)
        if have and have['kind'] == 'oficial':
            old_year = GAME_YEAR.get(have.get('game') or '', 0)
            same = have.get('digest') == digest(s['vxla'])
            if not same and GAME_YEAR.get(s['game'], 0) > old_year:
                plan['reemplazar_oficial_mas_vieja'].append(dict(s, old_game=have.get('game')))
            else:
                plan['ya_esta_igual_o_mas_nueva'].append(dict(s, old_game=have.get('game'), identical=same))
        elif have:
            plan['reemplazar_hecha_por_nosotros'].append(dict(s, old_kind=have['kind']))
        elif in_mega:
            plan['ya_esta_igual_o_mas_nueva'].append(dict(s, old_game=in_mega, identical=False, only_megapack=True))
        else:
            plan['nuevas'].append(s)
    if args.plan:
        Path(args.plan).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = ["# Canciones de los juegos extraídos frente a tu biblioteca", "",
             f"{len(found)} canciones en los paquetes extraídos, {len(best)} distintas.", ""]
    titles = {'nuevas': "Nuevas (no las tienes)",
              'reemplazar_hecha_por_nosotros': "Las tienes hechas por nosotros (USDB / SongMaker): se cambian por la oficial",
              'reemplazar_oficial_mas_vieja': "Las tienes oficiales de un juego más viejo: se cambian por esta",
              'ya_esta_igual_o_mas_nueva': "Ya las tienes oficiales, iguales o de un juego más nuevo: no se tocan"}
    for k, title in titles.items():
        rows = plan[k]
        lines += [f"## {title} ({len(rows)})", ""]
        for s in rows:
            extra = ''
            if s.get('folder'):
                extra = f" — tu carpeta: «{s['folder']}»"
            if s.get('old_game') or s.get('old_kind'):
                extra += f" (la tuya: {s.get('old_game') or s.get('old_kind')}{', idéntica' if s.get('identical') else ''})"
            lines.append(f"- {s['artist']} — {s['title']} ({s['year']}) · {s['game']} · {s['pack']}{extra}")
        lines.append("")
    if args.md:
        Path(args.md).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for k in titles:
        print(f"{k}: {len(plan[k])}")


if __name__ == '__main__':
    sys.exit(main())
