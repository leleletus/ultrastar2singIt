"""Lists songs downloaded with a USDB syncer whose audio does not come from the video the txt was timed with.

Usage: python tools/usdb_sources.py <songs folder>      (only reads)

The .usdb file next to the txt keeps the video the creator synced the lyrics to ("v=" in meta_tags) and the
source the audio was really downloaded from. When the syncer could not get the first one it falls back to
another upload, often a different cut of the song: the lyrics then come early, late or after the audio ends.
Fix: download the audio again from the expected video, or adjust #GAP with the Sync Editor.
"""
import glob
import json
import os
import sys


def check(songs_dir):
    found, total = [], 0
    for path in sorted(glob.glob(os.path.join(glob.escape(songs_dir), '*', '*.usdb'))):
        total += 1
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        tags = dict(kv.split('=', 1) for kv in (data.get('meta_tags') or '').split(',') if '=' in kv)
        expected = tags.get('a') or tags.get('v')
        got = (data.get('audio') or {}).get('resource')
        if expected and got and got != expected:
            found.append((os.path.basename(os.path.dirname(path)), expected, got))
    return found, total


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    found, total = check(sys.argv[1])
    for folder, expected, got in found:
        print(f"{folder}\n    synced to https://youtu.be/{expected}  audio from https://youtu.be/{got}")
    print(f"\n{len(found)} of {total} USDB songs have audio from a different video.")


if __name__ == '__main__':
    main()
