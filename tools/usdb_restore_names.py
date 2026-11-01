"""Names the files of every song as usdb_syncer does ("Artist - Title.ext"), so usdb_syncer recognizes its songs.

Usage:
    python tools/usdb_restore_names.py <songs folder>            # only lists
    python tools/usdb_restore_names.py <songs folder> --apply    # renames (a .bak of the txt is kept)

Older scripts renamed the media of every USDB song to generic names: the original audio became <id>.m4a, the txt
pointed to audio.ogg (a copy of the converted audio), the video was video.mp4 and the cover cover.png. usdb_syncer then
believes its files are missing and, if the song is downloaded again, writes its own video over a video cut by hand.
Songs taken from the games (no .usdb): audio.ogg, video.mp4 and the cover get the same "Artist - Title" names.
For every folder with a .usdb file:
  - audio: <id>.m4a (same length as the txt's audio) -> "<Artist - Title>.m4a"; #MP3 points to it; audio.ogg is
    deleted only when it is a byte-identical copy of the converted <id>.ogg;
  - video: video.mp4 -> "<Artist - Title>.mp4"; #VIDEO points to it;
  - cover: the cover the txt uses -> "<Artist - Title> [CO].<ext>"; #COVER points to it;
  - the .usdb file records the new names and dates, so usdb_syncer sees its files as present and up to date.
Files are only renamed (contents and dates kept): converted files (.bk2, .ogg, covers) are not made again.
"""
import argparse
import filecmp
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import naming  # noqa: E402
import UltrastarToSingit  # noqa: E402


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


def mtime_us(path):
    return int(path.stat().st_mtime * 1_000_000)  # what usdb_syncer stores (utils.get_mtime)


def read_txt(txt):
    raw = txt.read_bytes()
    encoding = UltrastarToSingit._detect_encoding_bytes(raw)
    if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8'
    return raw, encoding, raw.decode(encoding).splitlines(keepends=True)


def set_tag(lines, tag, value):
    for i, line in enumerate(lines):
        if line.upper().startswith(f'#{tag}:'):
            newline = '\r\n' if line.endswith('\r\n') else '\n'
            lines[i] = f"#{tag}:{value}{newline}"
            return
    raise ValueError(f"no #{tag}")


def plan_song(d):
    """List of (kind, source Path, target Path) renames and extra deletions for one folder."""
    usdb_file = next(d.glob('*.usdb'), None)
    txt = ConvertFiles.choose_txt_file([p for p in d.iterdir() if p.suffix.lower() == '.txt'])
    if txt is None:
        return None
    data = UltrastarToSingit.parse_file(txt)
    usdb = json.loads(usdb_file.read_text(encoding='utf-8')) if usdb_file else {}
    ids = [naming.construct_name_id_from_directory_name(d.name)] + naming.legacy_name_ids(d.name)
    base = d.name
    renames, deletes, notes = [], [], []

    def target(kind, ext):
        fname = (usdb.get(kind) or {}).get('fname')
        name = fname if fname and Path(fname).suffix.lower() == ext.lower() else base + ext
        return d / name

    mp3 = (data.get('MP3') or '').strip()
    if mp3 == 'audio.ogg' and usdb_file is None:  # songs taken from the games: their audio is the official one
        if (d / mp3).exists():
            renames.append(('MP3', 'audio', d / mp3, d / (base + '.ogg')))
    elif mp3 == 'audio.ogg':
        originals = list(d.glob('*.m4a'))  # the download, renamed to the converter's ID by an older script
        if len(originals) == 1:
            src = originals[0]
            a, b = duration(src), duration(d / mp3)
            if a and b and abs(a - b) < 0.5:
                renames.append(('MP3', 'audio', src, target('audio', '.m4a')))
                converted = [d / (i + '.ogg') for i in ids if (d / (i + '.ogg')).exists()]
                if converted and filecmp.cmp(d / mp3, converted[0], shallow=False):
                    deletes.append(d / mp3)
            else:
                notes.append(f"audio: {src.name} {a} s vs {mp3} {b} s, not touched")
        elif originals:
            notes.append(f"audio: several .m4a {[p.name for p in originals]}, not touched")
    video = (data.get('VIDEO') or '').strip()
    if video == 'video.mp4' and (d / video).exists():
        renames.append(('VIDEO', 'video', d / video, target('video', '.mp4')))
    cover = (data.get('COVER') or '').strip()
    if cover and (d / cover).exists() and '[CO]' not in cover:
        renames.append(('COVER', 'cover', d / cover, d / f"{base} [CO]{Path(cover).suffix.lower()}"))
    renames = [r for r in renames if r[2] != r[3]]
    for tag, kind, src, dst in renames:
        if dst.exists():
            notes.append(f"{kind}: {dst.name} already exists, not touched")
    renames = [r for r in renames if not r[3].exists()]
    return txt, usdb_file, usdb, renames, deletes, notes


def apply_song(d, plan):
    txt, usdb_file, usdb, renames, deletes, _ = plan
    raw, encoding, lines = read_txt(txt)
    for tag, kind, src, dst in renames:
        set_tag(lines, tag, dst.name)
    backup = txt.with_name(txt.name + '.bak')
    if not backup.exists():
        backup.write_bytes(raw)
    for tag, kind, src, dst in renames:
        size = src.stat().st_size
        os.rename(src, dst)
        assert dst.stat().st_size == size
        if usdb_file is None:
            continue
        entry = usdb.get(kind) or {}
        entry.update({'fname': dst.name, 'mtime': mtime_us(dst)})
        entry.setdefault('status', 'success')
        usdb[kind] = entry
    tmp = txt.with_name(txt.name + '.tmp')
    tmp.write_bytes(''.join(lines).encode(encoding))
    os.replace(tmp, txt)
    for p in deletes:
        p.unlink()
    if usdb_file is None:
        return
    tmp = usdb_file.with_name(usdb_file.name + '.tmp')
    tmp.write_text(json.dumps(usdb, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, usdb_file)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--skip', action='append', default=[], help="folder to leave as it is (can be repeated)")
    args = parser.parse_args()
    total = changed = usdb_songs = 0
    for d in sorted(p for p in Path(args.songs).iterdir() if p.is_dir() and p.name not in args.skip):
        plan = plan_song(d)
        if plan is None:
            continue
        total += 1
        usdb_songs += plan[1] is not None
        _, _, _, renames, deletes, notes = plan
        for note in notes:
            print(f"   ! {d.name}: {note}")
        if not renames:
            continue
        changed += 1
        print(f"{d.name}: " + ", ".join(f"{s.name} -> {t.name}" for _, _, s, t in renames)
              + (f"; deletes copy {', '.join(p.name for p in deletes)}" if deletes else ""), flush=True)
        if args.apply:
            apply_song(d, plan)
    print(f"\n{changed} of {total} songs ({usdb_songs} from USDB) "
          f"{'renamed' if args.apply else 'to rename (run again with --apply)'}")


if __name__ == '__main__':
    main()
