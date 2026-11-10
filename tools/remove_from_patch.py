"""Takes songs out of a converted patch (Let's Sing 2026 / songs_xx.json patches): their entry in the song list and
their files (audio, preview, cover, vxla, feat, beats, video) leave the patch. Nothing is deleted: the files are moved
to a trash folder, so a .bk2 can come back. The converter never does this by itself, so a song whose folder left the
library (replaced by the official one) stays in the patch until it is taken out here. On the Switch, the files are
removed by tools/switch_update.py --apply --prune.

Usage:
    python tools/remove_from_patch.py <patch folder>/romfs <ID> [<ID> ...] --trash <folder> [--apply]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('romfs')
    parser.add_argument('ids', nargs='+')
    parser.add_argument('--trash', required=True)
    parser.add_argument('--apply', action='store_true', help='without it, only shows what would be moved')
    args = parser.parse_args()
    romfs = Path(args.romfs)
    lists = sorted(romfs.glob('songs_*.json'))
    if not lists:
        sys.exit(f"No songs_*.json in {romfs}: only JSON patches are supported.")
    ids = set(args.ids)
    def song_id(name):  # <ID>.ogg, <ID>_preview.ogg, <ID>_feat.vxla, <ID>.bk2...
        stem = name.split('.')[0]
        for suffix in ('_preview', '_feat'):
            if stem.endswith(suffix) and stem[:-len(suffix)] in ids:
                return stem[:-len(suffix)]
        return stem
    files = sorted(p for p in (romfs / 'Songs').glob('*/*') if p.is_file() and song_id(p.name) in ids)
    trash = Path(args.trash)
    for song_list in lists:
        data = json.loads(song_list.read_text(encoding='utf-8'))
        keep = [s for s in data['songs'] if s['id'] not in ids]
        gone = [s['id'] for s in data['songs'] if s['id'] in ids]
        print(f"{song_list.name}: {len(gone)} of {len(data['songs'])} entries out: {', '.join(gone)}")
        missing = ids - set(gone)
        if missing:
            print(f"   not in the list: {', '.join(sorted(missing))}")
        if args.apply and gone:
            trash.mkdir(parents=True, exist_ok=True)
            shutil.copy2(song_list, trash / song_list.name)
            data['songs'] = keep
            tmp = song_list.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding='utf-8')
            tmp.replace(song_list)
    print(f"{len(files)} file(s), {sum(f.stat().st_size for f in files) / 2**20:.0f} MB "
          f"{'moved to' if args.apply else 'would go to'} {trash}")
    if args.apply:
        for f in files:
            dest = trash / f.relative_to(romfs)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(f, dest)
    return 0


if __name__ == '__main__':
    sys.exit(main())
