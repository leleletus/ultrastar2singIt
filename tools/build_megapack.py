"""Gathers chosen songs of extracted Let's Sing games into a megapack folder (the layout LetSing_ExtractorPro.py and
attach_official_vxla.py read): Songs/{audio,audio_preview,videos,vxla,vxla_duet,covers}/<ID>.* and
songs_int_combined.json with artist, title and year. Covers that the game keeps inside its Unity files (Let's Sing
11 and 12: a 512x512 Texture2D named like the song) are exported with UnityPy.

Usage:
    python tools/build_megapack.py <plan.json from official_inventory.py> --out <megapack folder>
        [--groups nuevas reemplazar_hecha_por_nosotros ...] [--also "Anywhere" ...]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

MEDIA = {'audio': ('.ogg',), 'audio_preview': ('_preview.ogg',), 'videos': ('.mp4', '.webm', '.bk2'),
         'vxla': ('.vxla',), 'vxla_duet': ('_duet.vxla', '_DUET.vxla'), 'covers': ('.png', '.jpg')}


def unity_covers(data_dir, ids, dest):
    """Exports the cover texture of each song ID found in the game's Unity files; returns the IDs exported."""
    try:
        import UnityPy
    except ImportError:
        return set()
    done = set()
    env = UnityPy.load(str(data_dir))
    for obj in env.objects:
        if obj.type.name != 'Texture2D':
            continue
        try:
            name = obj.peek_name()
        except Exception:
            continue
        if name in ids and name not in done:
            obj.read().image.convert('RGB').save(dest / f"{name}.png")
            done.add(name)
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan')
    parser.add_argument('--out', required=True)
    parser.add_argument('--groups', nargs='*', default=['nuevas', 'reemplazar_hecha_por_nosotros',
                                                         'reemplazar_oficial_mas_vieja'])
    parser.add_argument('--also', nargs='*', default=[], help='song IDs of other groups to include')
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    chosen = [s for g in args.groups for s in plan.get(g, [])]
    chosen += [s for g in plan.values() for s in g if s['id'] in args.also and s not in chosen]
    out = Path(args.out) / 'Songs'
    for sub in MEDIA:
        (out / sub).mkdir(parents=True, exist_ok=True)
    meta, missing_cover, used = [], {}, set()
    for s in chosen:
        src = Path(s['songs_dir'])
        sid = name = s['id']
        while name in used:  # two different songs with the same ID in different games ("Up" in 2014 and 2016)
            name += '_2'
        used.add(name)
        if s.get('platform') == 'wii':  # files/common/{audio,vxla,textures/covers}; videos are Wii MobiClip (.mo)
            wii = {'audio': src / 'common' / 'audio' / f"{sid}.ogg", 'vxla': src / 'common' / 'vxla' / f"{sid}.vxla",
                   'vxla_duet': src / 'common' / 'vxla' / f"{sid}_DUET.vxla",
                   'covers': src / 'common' / 'textures' / 'covers' / f"{sid}.png"}
            for sub, f in wii.items():
                if f.exists():
                    shutil.copy2(f, out / sub / (f"{name}_duet.vxla" if sub == 'vxla_duet' else name + f.suffix))
            meta.append({'id': name, 'artist': s['artist'], 'title': s['title'], 'year': s.get('year', ''),
                         'source': s['pack']})
            continue
        for sub, suffixes in MEDIA.items():
            for suffix in suffixes:
                f = src / sub / f"{sid}{suffix}"
                if f.exists():
                    shutil.copy2(f, out / sub / f.name)
                    break
        if not any((out / 'covers').glob(f"{sid}.*")):
            data_dir = next((p.parent for p in src.parents[0].parent.rglob('resources.assets')), None)
            if data_dir is None:
                data_dir = next((p.parent for p in Path(s['vxla']).parents[4].rglob('resources.assets')), None)
            missing_cover.setdefault(str(data_dir), set()).add(sid)
        meta.append({'id': sid, 'artist': s['artist'], 'title': s['title'], 'year': s.get('year', ''),
                     'source': s['pack']})
    for data_dir, ids in missing_cover.items():
        if data_dir != 'None':
            got = unity_covers(Path(data_dir), ids, out / 'covers')
            for sid in sorted(ids - got):
                print(f"no cover: {sid}", flush=True)
    (Path(args.out) / 'songs_int_combined.json').write_text(
        json.dumps({'songs': meta}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"{len(chosen)} songs -> {args.out}")


if __name__ == '__main__':
    sys.exit(main())
