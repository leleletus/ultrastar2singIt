"""Extracts the songs (RomFS) of Let's Sing Switch dumps: base game with its update applied, and every DLC.

Each NSP goes to <out>/<NSP name>/romfs (audio, videos, covers, vxla, *_meta.xml or songs_*.json...). The title key
is read from the NSP's own ticket; the console keys come from ~/.switch/prod.keys (never changed). An update is
applied on top of its base (hactool --basenca), so the result is the game as it is played. Resumable: an NSP whose
romfs folder is complete is skipped. The temporary NCA files go to <out>/_tmp and are removed after each NSP.

Usage:
    python tools/extract_switch_songs.py <folder with NSPs> --out <folder> [--hactool PATH] [--keys PATH]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HACTOOL = os.path.expanduser('~/hactool_build/hactool/hactool')
KEYS = os.path.expanduser('~/.switch/prod.keys')
DONE = '.extraction_done'


def title_id(nsp):
    m = re.search(r'\[([0-9A-Fa-f]{16})\]', nsp.name)
    return m.group(1).upper() if m else None


def kind(tid):
    """'base', 'update' or 'dlc' from a title ID."""
    if tid.endswith('800'):
        return 'update'
    return 'base' if tid.endswith('000') else 'dlc'


ENV = dict(os.environ)


def run(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=ENV)
    if out.returncode != 0 and 'Done' not in out.stdout:
        raise RuntimeError(f"{' '.join(cmd[:3])}...: {out.stderr.strip() or out.stdout.strip()[-300:]}")
    return out.stdout


def unpack(nsp, tmp, hactool, keys):
    """NCA files of an NSP and its title key: {content type: path}, key."""
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    run([hactool, '-k', keys, '-t', 'pfs0', f'--outdir={tmp}', str(nsp)])
    for tik in tmp.glob('*.tik'):  # rights id -> title key, for hactool's title.keys (base and update differ)
        raw = tik.read_bytes()
        with open(Path(ENV['HOME']) / '.switch' / 'title.keys', 'a', encoding='ascii') as f:
            f.write(f"{raw[0x2a0:0x2b0].hex()} = {raw[0x180:0x190].hex()}\n")
    ncas = {}
    for nca in tmp.glob('*.nca'):
        if nca.name.endswith('.cnmt.nca'):
            continue
        info = run([hactool, '-k', keys, str(nca)])
        m = re.search(r'Content Type:\s+(\w+)', info)
        if m:
            ncas.setdefault(m.group(1), nca)
    return ncas


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source')
    parser.add_argument('--out', required=True)
    parser.add_argument('--hactool', default=HACTOOL)
    parser.add_argument('--keys', default=KEYS)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # hactool reads ~/.switch/title.keys: a private HOME with a copy of the user's keys plus the NSPs' own title
    # keys (the user's files are never changed)
    home = out / '_home'
    (home / '.switch').mkdir(parents=True, exist_ok=True)
    for f in ('prod.keys', 'title.keys'):
        src = Path(os.path.expanduser('~/.switch')) / f
        if src.exists():
            shutil.copy(src, home / '.switch' / f)
    ENV['HOME'] = str(home)
    nsps = sorted(Path(args.source).rglob('*.nsp'))
    by_kind = {'base': {}, 'update': {}, 'dlc': {}}
    for nsp in nsps:
        tid = title_id(nsp)
        if tid:
            by_kind[kind(tid)][tid] = nsp
    jobs = []
    for tid, nsp in sorted(by_kind['base'].items()):
        update = by_kind['update'].get(tid[:-3] + '800')
        jobs.append((nsp, update))
    for tid, nsp in sorted(by_kind['dlc'].items()):
        jobs.append((nsp, None))
    for nsp, update in jobs:
        name = (update or nsp).stem
        dest = out / name / 'romfs'
        if (out / name / DONE).exists():
            print(f"skip {name}", flush=True)
            continue
        if dest.exists():
            shutil.rmtree(dest)
        tmp = out / '_tmp'
        try:
            ncas = unpack(nsp, tmp / 'main', args.hactool, args.keys)
            main_nca = ncas.get('Program') or ncas.get('PublicData') or ncas.get('Data')
            if main_nca is None:
                raise RuntimeError(f"no Program/PublicData NCA in {nsp.name}: {list(ncas)}")
            cmd = [args.hactool, '-k', args.keys]
            if update:  # the game as it is played: the update's patch applied to the base
                patch = unpack(update, tmp / 'update', args.hactool, args.keys)
                cmd += [f'--basenca={main_nca}']
                main_nca = patch.get('Program')
            dest.parent.mkdir(parents=True, exist_ok=True)
            run(cmd + [f'--romfsdir={dest}', str(main_nca)])
            files = sum(1 for _ in dest.rglob('*') if _.is_file())
            (out / name / DONE).write_text(f"{nsp.name}\n{update.name if update else ''}\n{files} files\n",
                                           encoding='utf-8')
            print(f"ok   {name}: {files} files" + (" (update applied)" if update else ''), flush=True)
        except Exception as e:
            print(f"FAILED {name}: {e}", flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(home, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
