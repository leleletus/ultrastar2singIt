"""Gives back their own cover to songs that share the same image with other songs.

Usage:
    python tools/fix_covers.py <songs folder> [--extracted <extracted games>]            # only lists
    python tools/fix_covers.py <songs folder> [--extracted <extracted games>] --apply    # fixes

An older script replaced the cover of many USDB songs with one image per artist (all the Ariana Grande songs had
the same cover). For every song whose cover is shared:
  - USDB songs: the cover is downloaded again from the address kept in their .usdb file;
  - songs rebuilt from DLCs (letssing_original.vxla): the loose official cover of the extracted games (2024+);
  - else the single/album cover of the iTunes store, when artist and title match exactly;
  - otherwise a frame of the song's own video (the megapack covers have the same problem, they are not used).
The new image is saved as cover_song.<ext> (the old one is kept) and #COVER of the txt points to it (a .bak of the
txt is kept). The next conversion rebuilds the cover of those songs (the converter notices the newer source).
"""
import argparse
import collections
import glob
import hashlib
import io
import json
import os
import sys
import re
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import UltrastarToSingit  # noqa: E402
import naming  # noqa: E402

NEW_COVER = 'cover_song'


def sha1(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def current_cover(song_dir):
    data = UltrastarToSingit.parse_file(ConvertFiles.choose_txt_file(
        [p for p in song_dir.iterdir() if p.suffix.lower() == '.txt']))
    _, _, cover = ConvertFiles.resolve_song_sources(song_dir, data, naming.all_name_ids(song_dir.name.rstrip('.')))
    return cover


def usdb_cover_url(song_dir):
    for f in song_dir.glob('*.usdb'):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        url = (data.get('cover') or {}).get('resource')
        if url and url.startswith('http'):
            return url
    return None


def official_cover(song_dir, vxla_index):
    """The loose cover file next to the same official vxla in the extracted games (2024+ DLCs), or None."""
    official = song_dir / naming.OFFICIAL_VXLA_NAME
    found = vxla_index.get(sha1(official)) if official.exists() else None
    if not found:
        return None
    covers = found.parent.parent / 'covers'
    for ext in ('.png', '.jpg', '.jpeg'):
        if (covers / (found.stem + ext)).exists():
            return covers / (found.stem + ext)
    return None


def _simple(text):
    import unicodedata
    text = unicodedata.normalize('NFKD', text.lower())
    text = re.sub(r'\(.*?\)|\[.*?\]| - .*$', '', ''.join(c for c in text if not unicodedata.combining(c)))
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', text).split())


def store_cover_url(artist, title):
    """Cover of the single/album in the iTunes store, only when artist AND title really match (the first result
    of a loose search is often another song: that is how wrong artists/titles were made in the past)."""
    query = urllib.parse.urlencode({'term': f"{artist} {title}", 'entity': 'song', 'limit': 25})
    request = urllib.request.Request(f"https://itunes.apple.com/search?{query}",
                                     headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        results = json.loads(response.read().decode('utf-8')).get('results', [])
    want_title, first_artist = _simple(title), _simple(re.split(r' feat\.? | ft\.? |,| & | x | \+ ', artist)[0])
    for r in results:
        if _simple(r.get('trackName', '')) == want_title and first_artist in _simple(r.get('artistName', '')):
            url = r.get('artworkUrl100')
            if url:
                return url.replace('100x100bb', '1000x1000bb')
    return None


def video_frame(song_dir, data):
    """A frame of the song's own video (a third of the way in), as JPEG bytes, or None."""
    import subprocess
    _, video, _ = ConvertFiles.resolve_song_sources(song_dir, data, naming.all_name_ids(song_dir.name.rstrip('.')))
    if video is None or video.suffix.lower() == '.bk2':
        return None
    at = max(1.0, ConvertFiles.get_duration(video) / 3)
    result = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{at:.1f}', '-i', str(video), '-frames:v', '1',
                             '-f', 'image2', '-c:v', 'mjpeg', '-q:v', '2', 'pipe:1'], capture_output=True, timeout=120)
    return result.stdout or None


def download_image(url):
    """The image bytes and its extension, only if it really is an image."""
    from PIL import Image
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(20 * 1024 * 1024)
    with Image.open(io.BytesIO(data)) as img:
        img.verify()
        fmt = img.format
    return data, {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}.get(fmt, '.jpg')


def set_cover_tag(txt_path, cover_name):
    raw = txt_path.read_bytes()
    encoding = UltrastarToSingit._detect_encoding_bytes(raw)
    if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8'
    text = raw.decode(encoding)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.upper().startswith('#COVER:'):
            lines[i] = f"#COVER:{cover_name}"
            break
    else:
        lines.insert(next((i for i, l in enumerate(lines) if not l.startswith('#')), 0), f"#COVER:{cover_name}")
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
    parser.add_argument('--extracted', help="folder with the extracted Let's Sing games (official covers)")
    parser.add_argument('--frames', action='store_true', help="also replace covers taken from a video frame")
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    songs = [p for p in sorted(Path(args.songs).iterdir()) if p.is_dir()]
    by_hash = collections.defaultdict(list)
    for d in songs:
        try:
            cover = current_cover(d)
        except Exception:
            continue
        if cover is not None:
            by_hash[sha1(cover)].append(d)
    shared = [d for group in by_hash.values() if len(group) > 1 for d in group]
    vxla_index = {}
    if args.extracted:
        for f in Path(args.extracted).rglob('*.vxla'):
            vxla_index.setdefault(sha1(f), f)
    if args.frames:  # covers made from a frame of the video: try to get a real one
        shared += [d for d in songs if (d / (NEW_COVER + '.jpg')).exists() and d not in shared
                   and not usdb_cover_url(d) and not official_cover(d, vxla_index)]
    print(f"{len(shared)} songs share their cover with other songs")

    fixed, failed = 0, []
    for d in shared:
        txt = ConvertFiles.choose_txt_file([p for p in d.iterdir() if p.suffix.lower() == '.txt'])
        data = UltrastarToSingit.parse_file(txt)
        url = usdb_cover_url(d)
        source = None if url else official_cover(d, vxla_index)
        if not url and not source:
            try:
                url = store_cover_url(data.get('ARTIST', ''), data.get('TITLE', ''))
            except Exception:
                url = None
        print(f"   {d.name}  <-  {url or source or 'a frame of its video'}")
        if not args.apply:
            continue
        try:
            if url:
                image, ext = download_image(url)
            elif source:
                image, ext = source.read_bytes(), source.suffix.lower()
            else:
                image, ext = video_frame(d, data), '.jpg'
                if not image:
                    raise ValueError("no video to take a frame from")
            target = d / (NEW_COVER + ext)
            target.write_bytes(image)
            set_cover_tag(txt, target.name)
            fixed += 1
        except Exception as e:  # a dead link must not stop the others
            failed.append((d.name, str(e)[:120]))
    if args.apply:
        print(f"\n{fixed} cover(s) fixed")
    else:
        print("\nRun again with --apply to fix them.")
    for name, reason in failed:
        print(f"   NOT FIXED {name}: {reason}")


if __name__ == '__main__':
    main()
