"""Removes leftovers from the song folders, keeping the song files and the converted ones.

Usage:
    python tools/clean_song_folders.py <songs folder>                  # only lists
    python tools/clean_song_folders.py <songs folder> --apply          # moves them to the bin
    python tools/clean_song_folders.py <songs folder> --apply --bak    # also the .bak copies of the txt files

Nothing is deleted: the files go to <songs folder>/../_papelera/<date>/<song>/ (same folders), to be emptied by hand
once everything is checked. Moved:
  - ffmpeg two-pass logs (passlog-*.log, *.mbtree), demucs_out folders, half-written *.tmp files;
  - the x264 intermediate <id>.avi when the song already has its real .bk2 (it is only used to make the .bk2), and
    the still videos made from the cover (<id>_cover.avi / _cover.mp4) once the .bk2 is a real video;
  - covers and audio files the txt no longer uses when it uses another one that exists (e.g. cover.png after
    tools/fix_covers.py, audio.ogg after tools/usdb_restore_names.py);
  - a .bk2 with an old ID only when it is byte-identical to the song's current .bk2 (a duplicate).
Never deleted: the txt, the .usdb, the files the txt points to (audio, video, cover, background), the song's current
.bk2 and the other converted files, letssing_original.vxla, the voice analysis, the Genius cache.
"""
import argparse
import filecmp
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import naming  # noqa: E402
import UltrastarToSingit  # noqa: E402

IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
AUDIO = {'.ogg', '.mp3', '.m4a', '.wav', '.opus', '.flac', '.aac', '.webm'}


def real_video_bk2(d, name_id, bk2):
    """The .bk2 is a real video (not the still cover): judged by its size for the length of the song."""
    try:
        with open(d / (name_id + naming.VXLA_META_SUFFIX), encoding='utf-8') as f:
            duration = json.load(f).get('duration')
    except (OSError, ValueError):
        duration = None
    return bool(duration) and not ConvertFiles.is_still_bk2(bk2, duration)


def leftovers(d, with_bak=False):
    """[(Path, reason)] of the files of one song folder that can go."""
    txt = ConvertFiles.choose_txt_file([p for p in d.iterdir() if p.suffix.lower() == '.txt'])
    if txt is None:
        return []
    data = UltrastarToSingit.parse_file(txt)
    used = {(data.get(k) or '').strip() for k in ('MP3', 'AUDIO', 'VIDEO', 'COVER', 'BACKGROUND', 'VOCALS',
                                                  'INSTRUMENTAL')} - {''}
    used_existing = {u for u in used if (d / u).exists()}
    name_id = naming.construct_name_id_from_directory_name(d.name)
    ids = [name_id] + naming.legacy_name_ids(d.name)
    bk2 = d / (name_id + naming.VIDEO_BK2_SUFFIX)
    out = []
    for p in sorted(d.iterdir()):
        n = p.name
        if p.is_dir():
            if n == 'demucs_out':
                out.append((p, 'voice separation leftovers'))
            continue
        if n == txt.name or n in used or n.endswith('.usdb') or n == naming.OFFICIAL_VXLA_NAME:
            continue
        if n.startswith('passlog') and (n.endswith('.log') or n.endswith('.mbtree')):
            out.append((p, 'ffmpeg log'))
        elif n.endswith('.tmp') or '.tmp.' in n:
            out.append((p, 'half-written file'))
        elif with_bak and n.endswith('.bak'):
            out.append((p, 'backup copy of the txt'))
        elif n in (name_id + naming.VIDEO_INTERMEDIATE_SUFFIX, name_id + naming.STILL_VIDEO_SUFFIX,
                   name_id + naming.STILL_VIDEO_MP4_SUFFIX):
            if bk2.exists() and real_video_bk2(d, name_id, bk2):
                out.append((p, 'intermediate of a finished .bk2'))
        elif p.suffix.lower() == naming.VIDEO_BK2_SUFFIX:
            if p != bk2 and bk2.exists() and p.stat().st_size == bk2.stat().st_size \
                    and filecmp.cmp(p, bk2, shallow=False):
                out.append((p, f'identical copy of {bk2.name}'))
        elif naming.is_generated_file(n, ids):
            continue
        elif p.suffix.lower() in IMAGES and any(Path(u).suffix.lower() in IMAGES for u in used_existing) \
                and n.lower().startswith('cover'):
            out.append((p, 'old cover the txt no longer uses'))
        elif p.suffix.lower() in AUDIO and n.lower().startswith('audio') and \
                any(Path(u).suffix.lower() in AUDIO for u in used_existing if u in (data.get('MP3'), data.get('AUDIO'))):
            out.append((p, 'old audio the txt no longer uses'))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--bak', action='store_true', help="also delete the .bak copies of the txt files")
    args = parser.parse_args()
    count, size = 0, 0
    by_reason = {}
    bin_dir = Path(args.songs).resolve().parent / '_papelera' / time.strftime('%Y-%m-%d_%H%M%S')
    for d in sorted(p for p in Path(args.songs).iterdir() if p.is_dir()):
        for p, reason in leftovers(d, args.bak):
            bytes_ = sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.is_dir() else p.stat().st_size
            count += 1
            size += bytes_
            n, s = by_reason.get(reason, (0, 0))
            by_reason[reason] = (n + 1, s + bytes_)
            print(f"   {reason:35} {bytes_ / 2**20:8.1f} MB  {d.name}/{p.name}", flush=True)
            if args.apply:
                target = bin_dir / d.name / p.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(p, target)
    for reason, (n, s) in sorted(by_reason.items(), key=lambda x: -x[1][1]):
        print(f"{n:5} {reason} ({s / 2**30:.2f} GB)")
    print(f"\n{count} file(s), {size / 2**30:.2f} GB "
          f"{f'moved to {bin_dir}' if args.apply else 'can go (run again with --apply)'}")


if __name__ == '__main__':
    main()
