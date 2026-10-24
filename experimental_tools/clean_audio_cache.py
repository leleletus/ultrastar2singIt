"""Deletes the converted audio (<id>.ogg, <id>_preview.ogg and their .meta.json) so it is made again.

Usage:
    python experimental_tools/clean_audio_cache.py <songs folder> [<output Songs folder>]           # only lists
    python experimental_tools/clean_audio_cache.py <songs folder> [<output Songs folder>] --apply   # deletes

Only files written by the converter for that song are touched: the song's own audio, videos (.bk2 included),
covers and txt are never deleted.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import naming  # noqa: E402

AUDIO_FILES = (naming.AUDIO_SUFFIX, naming.AUDIO_PREVIEW_SUFFIX, naming.AUDIO_META_SUFFIX)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('songs')
parser.add_argument('output_songs', nargs='?', help="romfs/Songs folder of the patch (its audio/ is cleaned too)")
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()

found = []
for d in sorted(os.listdir(args.songs)):
    song_dir = os.path.join(args.songs, d)
    if not os.path.isdir(song_dir):
        continue
    name_ids = naming.all_name_ids(d.rstrip('.'))
    for nid in name_ids:
        for suffix in AUDIO_FILES:
            path = os.path.join(song_dir, nid + suffix)
            if os.path.isfile(path):
                found.append(path)
            if args.output_songs and suffix != naming.AUDIO_META_SUFFIX:
                sub = 'audio_preview' if suffix == naming.AUDIO_PREVIEW_SUFFIX else 'audio'
                out_file = os.path.join(args.output_songs, sub, nid + suffix)
                if os.path.isfile(out_file):
                    found.append(out_file)

for path in found:
    print(path)
    if args.apply:
        os.remove(path)
print(f"\n{len(found)} converted audio file(s) {'deleted' if args.apply else 'found (run again with --apply to delete)'}.")
