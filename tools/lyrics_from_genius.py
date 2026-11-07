"""Gives SongMaker songs their whole Genius lyrics, placed on the song by the speech model, when the LRCLIB lyrics
are of another version or miss verses. Shows where each line fell and how sure the model is (below -6: listen to
it in the sync editor). The old txt is kept in ~/LetsSing/_respaldo_songmaker/<song>/.

Usage:
    python tools/lyrics_from_genius.py "<song folder>" [...] [--dry-run]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import SongMaker  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folders', nargs='+')
    parser.add_argument('--dry-run', action='store_true', help='only show where the lines fall')
    args = parser.parse_args()
    keep = os.path.join(os.path.expanduser('~'), 'LetsSing', '_respaldo_songmaker', time.strftime('%Y%m%d_%H%M%S'))
    for folder in args.folders:
        timed = SongMaker.lyrics_from_genius(folder, keep_dir=keep, dry_run=args.dry_run)
        unsure = 0
        for t, text, sure in timed:
            flag = '  <- escuchar' if sure is None or sure < SongMaker.ALIGN_MIN_LOGP else ''
            unsure += bool(flag)
            print(f"{int(t // 60)}:{t % 60:04.1f}  {'' if sure is None else f'{sure:5.1f}'}  {text}{flag}")
        print(f"#### {os.path.basename(os.path.normpath(folder))}: {len(timed)} lines, {unsure} unsure"
              + ('' if args.dry_run else f", old txt in {keep}"))


if __name__ == '__main__':
    main()
