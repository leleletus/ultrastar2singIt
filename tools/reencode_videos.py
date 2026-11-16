"""Encodes again the .bk2 videos of the library that were made with too little data (blocky when the picture moves):
from the ORIGINAL video of each song folder, at a constant quality (Bink "/Q"), not at the bitrate of the source.
Unattended and resumable: what is done is written to a state file and skipped the next time; stop it whenever
you want (Ctrl+C, or create the file <state>.stop to stop after the songs being encoded) and run it again later.

Why: the converter gave each .bk2 the bitrate of its source video (capped by "Max video size"). Bink 2 needs
several times the bits of H.264/VP9/AV1 for the same picture, and the x264 intermediate at that same bitrate lost
quality a second time. Measured (VMAF against the source, 100 = identical): 60 at 900 kbps and 82 at 2500 kbps with
that method; 94-97 with this one.

A video is ONLY encoded again when all of this holds (anything else is left exactly as it is and listed):
  - the song folder has its original video (not a .bk2 of a game, not only a cover);
  - the current .bk2 is a real clip, not the still cover;
  - the original video lasts what the current .bk2 lasts (so it is the video that .bk2 was made from: a clip
    cut or replaced by hand whose original is not in the folder is never swapped for something else).
The old .bk2 (and its old .avi intermediate) is moved to <songs>/../_replaced_videos/<song>/; with --delete-old it
is deleted instead, once the new one has been checked (length, size, 1280x720) and is in place.
The new one replaces it in the song folder and in the patch (<patch>/romfs/Songs/videos/<ID>.bk2); copy the patch
to the console afterwards with tools/switch_update.py.

Usage:
    python tools/reencode_videos.py <songs folder> <patch folder>                 # only the plan (changes nothing)
    python tools/reencode_videos.py <songs folder> <patch folder> --apply         # encodes, worst videos first
    options: --quality 0.2  --workers 3  --below 99999 (only .bk2 under this many kbps)  --only "<song folder>" ...
             --limit N  --state <file.json>  --min-free-gb 25  --delete-old
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import ConfigLoader  # noqa: E402
import UltrastarToSingit  # noqa: E402
import naming  # noqa: E402

VIDEO_FILTER = 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=25'  # as the converter
INTERMEDIATE_CRF = '12'      # x264 intermediate for binkc: visually lossless, deleted after the encode
DURATION_TOLERANCE_S = 1.5   # original video against the current .bk2
MIN_KBPS = 256               # a real clip is never left under this (the converter takes tiny .bk2 for still covers)
MAX_KBPS = 6000              # nor over this (a noisy source): encoded again at this data rate
FAILURES_TO_STOP = 5         # in a row: something is wrong (no display for Wine, disk...), stop instead of going on

_lock = threading.Lock()
_stop = threading.Event()


def log(message):
    print(f"{datetime.datetime.now():%m-%d %H:%M:%S} {message}", flush=True)


def bink_info(path):
    """(seconds, kbps, width, height) of a .bk2 from its header, or None."""
    try:
        with open(path, 'rb') as f:
            head = f.read(36)
        if len(head) < 36 or head[:3] not in (b'KB2', b'BIK'):
            return None
        frames = struct.unpack_from('<I', head, 8)[0]
        width, height, num, den = struct.unpack_from('<4I', head, 20)
        if not frames or not num or not den:
            return None
        seconds = frames * den / num
        return seconds, os.path.getsize(path) * 8 / seconds / 1000, width, height
    except OSError:
        return None


def probe_seconds(path):
    out = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', os.fspath(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def fingerprint(path):
    """Size and hash of the first MB: the .bk2 of the patch is a copy of the one of the song folder."""
    with open(path, 'rb') as f:
        return os.path.getsize(path), hashlib.sha1(f.read(1 << 20)).hexdigest()


def inspect(folder, patch_videos):
    """What to do with the video of a song folder: {'song', 'action': 'encode' or the reason it is left, ...}."""
    row = {'song': folder.name}
    txts = [x for x in folder.iterdir() if x.is_file() and x.suffix.lower() == '.txt']
    txt = ConvertFiles.choose_txt_file(txts) if txts else None
    if txt is None:
        return dict(row, action='not a song')
    name_id = naming.construct_name_id_from_directory_name(folder.name)
    name_ids = [name_id] + naming.legacy_name_ids(folder.name)
    bk2 = folder / (name_id + '.bk2')
    if not bk2.exists():
        return dict(row, action='no .bk2 yet (convert the song first)')
    info = bink_info(bk2)
    if info is None:
        return dict(row, action='its .bk2 cannot be read')
    seconds, kbps, _, _ = info
    row.update(name_id=name_id, bk2=os.fspath(bk2), old_kbps=round(kbps), old_mb=round(bk2.stat().st_size / 2 ** 20, 1),
               seconds=round(seconds, 1))
    if ConvertFiles.is_still_bk2(bk2, seconds):
        return dict(row, action='still cover (no clip)')
    try:
        data = UltrastarToSingit.parse_file(txt)
    except Exception as e:  # a txt the converter cannot read either
        return dict(row, action=f'txt not readable: {e}')
    _, video, _ = ConvertFiles.resolve_song_sources(folder, data, name_ids)
    if video is None:
        return dict(row, action='NO ORIGINAL VIDEO in the folder: its .bk2 is kept as it is')
    if video.suffix.lower() == '.bk2':
        return dict(row, action='video of a game (already .bk2)')
    trim = 0.0
    try:
        meta = json.loads((folder / (name_id + naming.AUDIO_META_SUFFIX)).read_text(encoding='utf-8'))
        trim = float(meta.get('trim_start') or 0.0)
    except (OSError, ValueError):
        pass
    source_seconds = probe_seconds(video)
    row.update(video=os.fspath(video), trim=trim, source_seconds=round(source_seconds, 1))
    if source_seconds <= 0:
        return dict(row, action=f'original video not readable: {video.name}')
    if trim > 0 and abs(source_seconds - seconds) <= DURATION_TOLERANCE_S:
        # the .bk2 was made from the whole clip while the song starts at #START: the same video, but it runs `trim`
        # seconds behind the song. The new one is cut like the audio, as the converter does now.
        row.update(seconds=round(source_seconds - trim, 1), was_whole_clip=True)
    elif abs((source_seconds - trim) - seconds) > DURATION_TOLERANCE_S:
        return dict(row, action=f'THE VIDEO IN THE FOLDER IS NOT THE ONE OF THE .bk2 ({video.name}: '
                                f'{source_seconds - trim:.1f} s, .bk2: {seconds:.1f} s): kept, check by hand')
    game_id = naming.game_song_id(folder.name)
    target = patch_videos / (game_id + '.bk2')
    if not (target.exists() and target.stat().st_size == bk2.stat().st_size):
        size, digest = fingerprint(bk2)
        target = next((p for p in patch_videos.glob('*.bk2') if p.stat().st_size == size
                       and fingerprint(p)[1] == digest), None)
    row['patch'] = os.fspath(target) if target else None
    return dict(row, action='encode')


def run(args, timeout):
    env = dict(os.environ, WINEDEBUG='-all')
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)


def wine_path(path):
    return 'Z:' + os.fspath(path).replace('/', '\\')


def bink(source, target, option, seconds):
    if target.exists():
        target.unlink()
    result = run([WINE, RAD, 'binkc', wine_path(source), wine_path(target), '/V200', '/(1280', '/)720', '/L-1',
                  option, '/#'], timeout=max(1800, int(seconds * 40)))
    if not target.exists() or target.stat().st_size < ConvertFiles.MIN_VALID_BK2_BYTES:
        tail = ' | '.join(x.strip() for x in (result.stdout + result.stderr).splitlines() if x.strip())[-300:]
        raise RuntimeError(f"binkc gave no video (exit {result.returncode}) {tail}")


def encode(row, quality, keep_root, temp_root, delete_old=False):
    """Makes the new .bk2 of a song and swaps it in. Returns (new MB, new kbps)."""
    folder = Path(row['bk2']).parent
    bk2, new = Path(row['bk2']), Path(row['bk2'] + '.new')
    work = temp_root / f"reencode_{os.getpid()}_{threading.get_ident()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        intermediate, out = work / 'input.avi', work / 'output.bk2'
        seek = ['-ss', str(row['trim'])] if row['trim'] > 0 else []
        made = run([FFMPEG, '-v', 'error', '-y'] + seek + ['-i', row['video'], '-c:v', 'libx264', '-preset', 'medium',
                    '-bf', '0', '-crf', INTERMEDIATE_CRF, '-an', '-vf', VIDEO_FILTER, os.fspath(intermediate)],
                   timeout=3600)
        if made.returncode != 0 or not intermediate.exists():
            raise RuntimeError(f"ffmpeg failed: {made.stderr.strip()[-300:]}")
        bink(intermediate, out, f'/Q{quality}', row['seconds'])
        info = bink_info(out)
        if info and info[1] < MIN_KBPS:
            bink(intermediate, out, f'/D{MIN_KBPS * 125}', row['seconds'])
        elif info and info[1] > MAX_KBPS:
            bink(intermediate, out, f'/D{MAX_KBPS * 125}', row['seconds'])
        info = bink_info(out)
        if info is None or abs(info[0] - row['seconds']) > DURATION_TOLERANCE_S or (info[2], info[3]) != (1280, 720):
            raise RuntimeError(f"the new .bk2 is not right: {info} (expected {row['seconds']} s, 1280x720)")
        shutil.move(os.fspath(out), new)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # swap: the old files go to the keep folder (or are deleted, with --delete-old, once the new one is in place)
    old_files = [p for p in (bk2, folder / (row['name_id'] + naming.VIDEO_INTERMEDIATE_SUFFIX)) if p.exists()]
    if delete_old:
        aside = Path(row['bk2'] + '.old')
        os.replace(bk2, aside)
        os.replace(new, bk2)
        for old in [aside] + old_files[1:]:
            old.unlink()
    else:
        keep = keep_root / folder.name
        keep.mkdir(parents=True, exist_ok=True)
        stamp = f"{datetime.datetime.now():%Y%m%d_%H%M%S}"
        for old in old_files:
            place = keep / old.name
            if place.exists():
                place = keep / f"{old.stem}.{stamp}{old.suffix}"
            shutil.move(os.fspath(old), place)
        os.replace(new, bk2)
    if row.get('patch'):
        patch_tmp = Path(row['patch'] + '.new')
        subprocess.run(['cp', '--reflink=auto', os.fspath(bk2), os.fspath(patch_tmp)], check=True)
        os.replace(patch_tmp, row['patch'])
    return round(bk2.stat().st_size / 2 ** 20, 1), round(info[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('patch', help='the DLC folder of the output, e.g. <output>/0100EE4020D19003')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--quality', type=float, default=0.2, help='Bink quality, 0.001 to 1.0 (default 0.2)')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--below', type=float, default=99999, help='only .bk2 under this many kbps')
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--state')
    parser.add_argument('--min-free-gb', type=float, default=25)
    parser.add_argument('--delete-old', action='store_true',
                        help='delete each old .bk2 (and .avi) once its new one is in place, instead of keeping it')
    args = parser.parse_args()
    songs, patch_videos = Path(args.songs), Path(args.patch) / 'romfs' / 'Songs' / 'videos'
    if not patch_videos.is_dir():
        sys.exit(f"No videos folder in the patch: {patch_videos}")
    cfg = ConfigLoader.load_config() if hasattr(ConfigLoader, 'load_config') else None
    global FFMPEG, FFPROBE, RAD, WINE
    FFMPEG = (cfg and str(cfg.tools.ffmpeg_path or '')) or shutil.which('ffmpeg')
    FFPROBE = shutil.which('ffprobe') or os.path.join(os.path.dirname(FFMPEG), 'ffprobe')
    RAD = (cfg and str(cfg.tools.rad_path or '')) or ''
    WINE = shutil.which('wine')
    if not (FFMPEG and RAD and os.path.exists(RAD) and WINE):
        sys.exit(f"ffmpeg ({FFMPEG}), RAD Video Tools ({RAD}) and wine ({WINE}) are needed")
    ConvertFiles._input_dir = os.fspath(songs)
    state_path = Path(args.state) if args.state else songs.parent / 'reencode_videos.json'
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}

    folders = [songs / d for d in (args.only or sorted(os.listdir(songs))) if (songs / d).is_dir()]
    log(f"Looking at {len(folders)} song folders...")
    rows = []
    for folder in folders:
        done = state.get(folder.name)
        if done and done.get('status') == 'done':
            current = folder / (done.get('name_id', '') + '.bk2')
            if current.exists() and abs(current.stat().st_size / 2 ** 20 - done.get('new_mb', -1)) < 0.2:
                rows.append({'song': folder.name, 'action': 'already encoded again'})
                continue
        try:
            rows.append(inspect(folder, patch_videos))
        except Exception as e:
            rows.append({'song': folder.name, 'action': f'error looking at it: {e}'})
    todo = sorted((r for r in rows if r['action'] == 'encode' and r['old_kbps'] < args.below),
                  key=lambda r: r['old_kbps'])
    if args.limit:
        todo = todo[:args.limit]
    left = {}
    for r in rows:
        if r['action'] != 'encode':
            left.setdefault(r['action'].split(' (')[0].split(':')[0], []).append(r['song'])
    hours = sum(r['seconds'] for r in todo) / 3600
    whole = [r['song'] for r in todo if r.get('was_whole_clip')]
    if whole:
        log(f"{len(whole)} of them have a .bk2 made from the whole clip although the song starts later (#START): the "
            f"new video is cut like the audio, so it will be in step with the song (check them): {'; '.join(whole)}")
    log(f"To encode again: {len(todo)} videos, {hours:.1f} h of video, "
        f"{sum(r['old_mb'] for r in todo) / 1024:.1f} GB now")
    for low, high in ((0, 800), (800, 1500), (1500, 2500), (2500, 3500), (3500, 10 ** 6)):
        part = [r for r in todo if low <= r['old_kbps'] < high]
        if part:
            log(f"   now at {low}-{high if high < 10 ** 6 else '...'} kbps: {len(part)} "
                f"({sum(r['seconds'] for r in part) / 3600:.1f} h)")
    for reason, names in sorted(left.items(), key=lambda kv: -len(kv[1])):
        log(f"Left as they are, {reason}: {len(names)}" + ('' if len(names) > 12 else ' -> ' + '; '.join(names)))
    plan = songs.parent / 'reencode_videos_plan.json'
    plan.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    log(f"Plan written to {plan}")
    if not args.apply:
        log("Nothing encoded (run again with --apply).")
        return
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        sys.exit("binkc (Wine) needs the desktop session: run this from a terminal of the desktop.")

    keep_root = songs.parent / '_replaced_videos'
    temp_root = Path(ConvertFiles._big_temp_dir() or os.path.expanduser('~/.cache'))
    for stale in temp_root.glob('reencode_*'):
        shutil.rmtree(stale, ignore_errors=True)
    stop_file = Path(os.fspath(state_path) + '.stop')
    if stop_file.exists():  # left by the last stop
        stop_file.unlink()
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    started, counters = time.monotonic(), {'done': 0, 'failed': 0, 'row': 0, 'video_s': 0.0, 'streak': 0}

    def save():
        tmp = Path(os.fspath(state_path) + '.tmp')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, state_path)

    def work(row):
        if _stop.is_set() or stop_file.exists():
            _stop.set()
            return
        if shutil.disk_usage(songs).free / 2 ** 30 < args.min_free_gb:
            log(f"STOPPING: less than {args.min_free_gb:.0f} GB free on the disk of the songs.")
            _stop.set()
            return
        began = time.monotonic()
        try:
            new_mb, new_kbps = encode(row, args.quality, keep_root, temp_root, args.delete_old)
            entry = {'status': 'done', 'name_id': row['name_id'], 'old_mb': row['old_mb'], 'old_kbps': row['old_kbps'],
                     'new_mb': new_mb, 'new_kbps': new_kbps, 'quality': args.quality,
                     'minutes': round((time.monotonic() - began) / 60, 1), 'patch': bool(row.get('patch')),
                     'when': f"{datetime.datetime.now():%Y-%m-%d %H:%M}"}
        except Exception as e:
            entry = {'status': 'failed', 'error': str(e)[:400], 'when': f"{datetime.datetime.now():%Y-%m-%d %H:%M}"}
            leftover = Path(row['bk2'] + '.new')
            if leftover.exists() and Path(row['bk2']).exists():
                leftover.unlink()
        with _lock:
            state[row['song']] = entry
            save()
            counters['row'] += 1
            if entry['status'] == 'done':
                counters['done'] += 1
                counters['streak'] = 0
                counters['video_s'] += row['seconds']
                speed = counters['video_s'] / max(1.0, time.monotonic() - started)
                remaining = sum(r['seconds'] for r in todo[counters['row']:]) / max(speed, 1e-6) / 3600
                log(f"[{counters['row']}/{len(todo)}] {row['song']}: {row['old_mb']} MB ({row['old_kbps']} kbps) -> "
                    f"{entry['new_mb']} MB ({entry['new_kbps']} kbps) in {entry['minutes']} min"
                    + ('' if entry['patch'] else '  (NOT in the patch: convert the song)')
                    + f" | about {remaining:.1f} h left")
            else:
                counters['failed'] += 1
                counters['streak'] += 1
                log(f"[{counters['row']}/{len(todo)}] FAILED {row['song']}: {entry['error']}")
                if counters['streak'] >= FAILURES_TO_STOP:
                    log(f"STOPPING: {FAILURES_TO_STOP} failures in a row. Fix the cause and run it again.")
                    _stop.set()

    log(f"Encoding with quality {args.quality}, {args.workers} at a time. Old videos are "
        + ("DELETED once the new one is in place" if args.delete_old else f"kept in {keep_root}"))
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            list(pool.map(work, todo))
    except KeyboardInterrupt:
        _stop.set()
        log("Interrupted: run the same command again to carry on.")
    grown = sum(v['new_mb'] - v['old_mb'] for v in state.values() if v.get('status') == 'done') / 1024
    log(f"Finished this run: {counters['done']} encoded, {counters['failed']} failed, "
        f"{len(todo) - counters['row']} not started. In all the patch has grown {grown:.1f} GB. State: {state_path}")


if __name__ == '__main__':
    main()
