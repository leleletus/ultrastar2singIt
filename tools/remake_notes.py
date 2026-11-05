"""Writes again the notes of the songs made by SongMaker with the current note maker (SongMaker.remake_notes): from
what each folder already has, without internet (except songs made before lrclib.json was kept) and without touching
videos. Convert afterwards: only the lyrics files (.vxla, _feat.vxla, beats) are made again, .bk2 videos are kept.

Usage:
    python tools/remake_notes.py <songs folder> [--keep <folder for the old txt>] [--only "LISA - MONEY" ...] [--force]
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import SongMaker  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--keep', help='copy every old txt here first (default: <songs>/../_papelera/notas_v1)')
    parser.add_argument('--only', nargs='*', help='song folders to do (default: every SongMaker song)')
    parser.add_argument('--force', action='store_true', help='also songs already remade or fixed by hand')
    args = parser.parse_args()
    songs = Path(args.songs)
    keep = Path(args.keep) if args.keep else songs.parent / '_papelera' / 'notas_v1'
    folders = [songs / d for d in (args.only or sorted(os.listdir(songs))) if (songs / d / 'songmaker.json').exists()]
    failed = []
    for folder in folders:
        try:
            SongMaker.remake_notes(folder, keep, force=args.force)
        except Exception as e:
            failed.append(folder.name)
            print(f"FAILED {folder.name}: {e}", flush=True)
    print(f"{len(folders) - len(failed)} done" + (f", failed: {failed}" if failed else ''))


if __name__ == '__main__':
    main()
