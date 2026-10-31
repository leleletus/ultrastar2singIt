"""Checks the sync of every UltraStar song against the singer's voice and writes a report (changes no txt).

Usage:
    python tools/sync_scan.py <songs folder> [--report informe.csv] [--only-analyzed] [--song "<folder>"]

For each song without an official vxla (those use the game's own timing) the voice is isolated with Demucs
(2-3 minutes per song on CPU, saved as <id>.voice.npz next to the song so the sync editor shows it at once) and
every lyrics line is compared with it. Verdicts:
    ok            the lyrics are on the voice
    desfase       all the lyrics are early or late by the same amount: fix #GAP in the sync editor
    parcial       some lines are out of time (a gap in the middle): cut + "Fit to voice" in the sync editor
    otra_version  the lyrics do not fit in the audio: the audio is another cut of the song
    dudosa        little voice matches the notes (quiet voice, many backing vocals...): check it by ear
--only-analyzed skips the songs whose voice has not been analyzed yet (no Demucs, a few seconds in total).
"""
import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ConvertFiles  # noqa: E402
import SyncModel  # noqa: E402
import UltrastarToSingit  # noqa: E402
import naming  # noqa: E402
from pathlib import Path  # noqa: E402


def song_timing(song_dir):
    """(song, audio file, seconds added to every note) exactly as the sync editor plays it."""
    folder = song_dir.name.rstrip('.')
    name_id = naming.construct_name_id_from_directory_name(folder)
    txt = ConvertFiles.choose_txt_file([p for p in song_dir.iterdir() if p.suffix.lower() == '.txt'])
    data = UltrastarToSingit.parse_file(txt)
    song = SyncModel.load_txt(data)
    gap = float(data.get('GAP', '0').replace(',', '.') or 0) / 1000
    try:
        video_gap = float(data.get('VIDEOGAP', '0').replace(',', '.') or 0)
    except ValueError:
        video_gap = 0.0
    meta = {}
    try:
        with open(song_dir / (name_id + naming.AUDIO_META_SUFFIX), encoding='utf-8') as f:
            meta = json.load(f)
    except (OSError, ValueError):
        pass
    start_offset, trim_start = float(meta.get('lyrics_offset') or 0), float(meta.get('trim_start') or 0)
    converted = song_dir / (name_id + naming.AUDIO_SUFFIX)
    official = song_dir / naming.OFFICIAL_VXLA_NAME
    if official.exists() and converted.exists():
        # the official vxla is used as it is: its times are already those of the audio
        return SyncModel.load_official(str(official)), converted, 0.0
    if converted.exists():
        return song, converted, gap + video_gap - start_offset
    audio, _, _ = ConvertFiles.resolve_song_sources(song_dir, data, naming.all_name_ids(folder))
    return song, audio, gap - (start_offset - trim_start)


def suspicion(song_dir, usdb_other):
    """0 = most likely out of sync (checked first), 2 = no sign of trouble. Cheap: no voice analysis."""
    try:
        song, audio, shift = song_timing(song_dir)
    except Exception:
        return 0
    if song_dir.name in usdb_other or audio is None or not song.notes:
        return 0
    try:
        if song.line_ends[-1] + shift > ConvertFiles.get_duration(audio) + 1:
            return 0
    except Exception:
        return 0
    if shift < 0 or song.notes[0].t + shift < 0.5 or not 50 <= (song.bpm or 100) <= 400:
        return 1
    return 2


def write_sidecar(song_dir, verdict, detail):
    """<id>.sync.json next to the song: the GUI shows it in its sync column (dropped when the txt changes)."""
    folder = song_dir.name.rstrip('.')
    txt = ConvertFiles.choose_txt_file([p for p in song_dir.iterdir() if p.suffix.lower() == '.txt'])
    path = song_dir / (naming.construct_name_id_from_directory_name(folder) + naming.SYNC_REPORT_SUFFIX)
    data = {'verdict': verdict, 'detail': detail, 'txt': txt.name, 'txt_mtime': txt.stat().st_mtime,
            'checked': time.strftime('%Y-%m-%d %H:%M')}
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def check_song(song_dir, analyze=True):
    song, audio, shift = song_timing(song_dir)
    if audio is None:
        return {'verdict': 'sin_audio', 'detail': ''}
    cache = SyncModel.voice_cache_path(str(song_dir))
    voice = SyncModel.load_voice(cache, str(audio))
    if voice is None:
        if not analyze:
            return None
        SyncModel.analyze_voice(str(audio), cache)
        voice = SyncModel.load_voice(cache, str(audio))
    report = SyncModel.line_report(song, voice, lambda i: shift)
    duration = len(voice['active']) * SyncModel.FRAME
    lyrics_end = (song.line_ends[-1] + shift) if song.line_ends else 0.0
    verdict, detail = SyncModel.song_verdict(report, [s + shift for s in song.line_starts], duration, lyrics_end)
    scores = [r[0] for r in report if r[0] is not None]
    write_sidecar(song_dir, verdict, detail)
    return {'verdict': verdict, 'detail': detail,
            'match': f"{sum(scores) / len(scores):.0%}" if scores else '',
            'lines_out': sum(1 for r in report if r[0] is not None and abs(r[1]) >= 0.3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--report', default='informe_sincronia.csv')
    parser.add_argument('--only-analyzed', action='store_true')
    parser.add_argument('--song', action='append', help="only this folder (can be repeated)")
    parser.add_argument('--jobs', type=int, default=1, help="songs analyzed at the same time (CPU cores are shared)")
    parser.add_argument('--official', type=int, default=0,
                        help="also check this many songs with an official vxla (their timing is the game's: a "
                             "reference to see how often the check is wrong)")
    args = parser.parse_args()
    if args.jobs > 1:  # every Demucs gets its share of the cores instead of all of them fighting
        os.environ.setdefault('OMP_NUM_THREADS', str(max(2, (os.cpu_count() or 4) // args.jobs)))

    base = Path(args.songs)
    dirs = sorted(p for p in base.iterdir() if p.is_dir() and (not args.song or p.name in args.song))
    todo = [d for d in dirs if not (d / naming.OFFICIAL_VXLA_NAME).exists()]
    reference = []
    if args.official:
        import random
        official = [d for d in dirs if (d / naming.OFFICIAL_VXLA_NAME).exists()]
        reference = random.Random(1).sample(official, min(args.official, len(official)))
    if not args.only_analyzed:
        # the songs most likely out of sync first, so the report is useful long before the scan ends
        import usdb_sources
        usdb_other = {folder for folder, _, _ in usdb_sources.check(str(base))[0]}
        todo.sort(key=lambda d: (suspicion(d, usdb_other), d.name.lower()))
    todo = reference + todo
    print(f"{len(todo)} UltraStar songs to check ({len(dirs) - len(todo)} use the official vxla and are skipped)",
          flush=True)
    rows = []
    started = time.time()
    done = 0
    order = {'otra_version': 0, 'parcial': 1, 'desfase': 2, 'dudosa': 3, 'error': 4, 'sin_audio': 5,
             'sin_notas': 6, 'ok': 7}

    def work(d):
        t0 = time.time()
        try:
            result = check_song(d, analyze=not args.only_analyzed)
        except Exception as e:  # one broken song must not stop the scan
            result = {'verdict': 'error', 'detail': str(e)[:200]}
        return d, result, time.time() - t0

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for d, result, took in pool.map(work, todo):
            done += 1
            if result is None:
                continue
            kind = 'oficial' if d in reference else 'ultrastar'
            rows.append({'song': d.name, 'kind': kind, **result})
            left = (time.time() - started) / done * (len(todo) - done)
            print(f"[{done}/{len(todo)}] {result['verdict']:12} {'(oficial) ' if kind == 'oficial' else ''}{d.name}  "
                  f"{result.get('detail', '')}  ({took:.0f} s, faltan ~{left / 60:.0f} min)", flush=True)
            with open(args.report, 'w', newline='', encoding='utf-8-sig') as f:  # rewritten after every song
                writer = csv.DictWriter(f, fieldnames=['song', 'kind', 'verdict', 'detail', 'match', 'lines_out'],
                                        delimiter=';', extrasaction='ignore')
                writer.writeheader()
                writer.writerows(sorted(rows, key=lambda r: (r['kind'] == 'oficial', order.get(r['verdict'], 9),
                                                             r['song'])))
    counts = {}
    for r in rows:
        counts[r['verdict']] = counts.get(r['verdict'], 0) + 1
    print(f"=== SCAN TERMINADO: {counts}  informe: {os.path.abspath(args.report)}", flush=True)


if __name__ == '__main__':
    main()
