"""Makes a queue of songs with SongMaker and converts them; every step is resumable (what is done is skipped), so after
a power cut or a dropped connection the same command carries on.

Usage:
    python tools/make_songs.py <songs folder> <queue.json> fetch      # everything that needs internet (waits for it)
    python tools/make_songs.py <songs folder> <queue.json> build      # notes and txt, no internet
    python tools/make_songs.py <songs folder> <queue.json> convert    # converts finished songs while `build` runs
    python tools/make_songs.py <songs folder> <queue.json> all        # the three, one after the other

<queue.json>: [{"artist", "title", "url", "audio" (optional), "language", "year", "genre"}, ...]. Keep it on disk (not
in /tmp, which is emptied when the PC turns off). `build` and `convert` can run at the same time (two processes):
`convert` converts each song as soon as `build` finishes it and ends when `build` has ended.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import SongMaker  # noqa: E402

BUILD_LOCK = '.songmaker_building'


def log(message):
    print(message, flush=True)


def folder_of(songs, song):
    return Path(songs) / SongMaker.safe_folder(f"{song['artist']} - {song['title']}")


def fetch(songs, queue):
    for song in queue:
        folder = folder_of(songs, song)
        if (folder / 'songmaker_fetched.json').exists() or (folder / 'songmaker.json').exists():
            continue
        log(f"######## fetch {folder.name}")
        try:
            SongMaker.fetch_song(song['artist'], song['title'], song['url'], songs, audio_url=song.get('audio'), log=log)
        except Exception as e:
            log(f"FAILED fetch {folder.name}: {e}")


def build(songs, queue):
    lock = Path(songs) / BUILD_LOCK
    lock.write_text(str(os.getpid()))
    try:
        for song in queue:
            folder = folder_of(songs, song)
            if (folder / 'songmaker.json').exists():
                continue
            log(f"######## build {folder.name}")
            try:
                SongMaker.make_song(song['artist'], song['title'], song['url'], songs,
                                    language=song.get('language', 'Spanish'), year=song.get('year'),
                                    genre=song.get('genre'), audio_url=song.get('audio'), log=log)
            except Exception as e:
                log(f"FAILED build {folder.name}: {e}")
    finally:
        lock.unlink(missing_ok=True)


def unconverted(songs):
    """Finished song folders (SongMaker done, usdb_syncer or official DLC) without their converted vxla or video."""
    import naming
    out = []
    for d in sorted(os.listdir(songs)):
        path = Path(songs) / d
        if not path.is_dir() or d.startswith(('_', '.')):
            continue
        nid = naming.construct_name_id_from_directory_name(d.rstrip('.'))
        if (path / (nid + naming.VXLA_SUFFIX)).exists() and (path / (nid + naming.VIDEO_BK2_SUFFIX)).exists():
            continue
        files = os.listdir(path)
        if 'songmaker.json' in files or any(f.endswith('.usdb') for f in files) or naming.OFFICIAL_VXLA_NAME in files:
            out.append(d)
    return out


def building(songs):
    lock = Path(songs) / BUILD_LOCK
    if not lock.exists():
        return False
    try:
        os.kill(int(lock.read_text()), 0)
        return True
    except (ValueError, OSError):
        return False  # left by a build that did not end (power cut)


def convert(songs):
    """Converts finished songs until `build` has ended and nothing is left; each song is tried once per run (one
    that fails is reported, not retried forever)."""
    import ConvertFiles
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', stream=sys.stdout)
    tried = set()
    while True:
        still_building = building(songs)
        pending = [d for d in unconverted(songs) if d not in tried]
        if pending:
            log(f"######## convert {len(pending)}: {pending}")
            tried.update(pending)
            ConvertFiles.main(only_dirs=pending)
            continue
        if not still_building:
            break
        time.sleep(120)
    left = unconverted(songs)
    log("######## all converted" if not left else f"######## not converted: {left}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('queue')
    parser.add_argument('step', choices=('fetch', 'build', 'convert', 'all'))
    args = parser.parse_args()
    queue = json.loads(Path(args.queue).read_text(encoding='utf-8'))
    if args.step in ('fetch', 'all'):
        fetch(args.songs, queue)
    if args.step in ('build', 'all'):
        build(args.songs, queue)
    if args.step in ('convert', 'all'):
        convert(args.songs)


if __name__ == '__main__':
    main()
