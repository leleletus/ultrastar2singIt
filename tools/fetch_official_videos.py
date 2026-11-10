"""Gives song folders without a video the official music video from YouTube, cut to the song's own audio.

For each folder with no #VIDEO: YouTube is searched for "<artist> <title> official video"; lyric videos, live
versions, audio-only uploads, covers, karaoke and remixes (unless the song is one) are left out, and the rest are
ranked (official/VEVO, the artist's channel, a length close to the song's). The best ones are downloaded in turn and
measured against the song's audio (tools/align_video.py: start, middle and end must agree, so another cut of the
song is refused); the first that follows the song is cut to it and saved as the folder's video. The lyrics belong to
the song's audio, so nothing else changes: no #GAP. Resumable: folders that have a #VIDEO are skipped.

Usage:
    python tools/fetch_official_videos.py <songs folder or song folders...> [--tries 3] [--only "Artist - Title"]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ConvertFiles  # noqa: E402
import UltrastarToSingit  # noqa: E402
import align_video  # noqa: E402

BAD = re.compile(r'\b(lyrics?|letra|live|en vivo|concert|audio|visualizer|karaoke|cover|instrumental|reaction|'
                 r'remix|sped up|slowed|8d|nightcore|teaser|trailer|behind the scenes|making of|dance practice|'
                 r'tutorial|1 hour|loop)\b', re.IGNORECASE)


def tags(folder):
    txts = [p for p in folder.iterdir() if p.suffix.lower() == '.txt']
    if not txts:
        return None, {}
    txt = ConvertFiles.choose_txt_file(txts)
    return txt, UltrastarToSingit.parse_file(txt)


def candidates(artist, title, length):
    query = f"ytsearch8:{artist} {title} official video"
    out = subprocess.run([*align_video.yt_dlp_command(), '--flat-playlist', '--print',
                          '%(id)s\t%(duration)s\t%(title)s\t%(channel)s', query],
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    found = []
    main_artist = re.split(r'\s+(?:feat\.?|ft\.?|&|x|,|y|\+)\s+', artist, flags=re.IGNORECASE)[0].lower()
    for row in out.stdout.splitlines():
        parts = row.split('\t')
        if len(parts) < 4:
            continue
        vid, duration, name, channel = parts[0], parts[1], parts[2], parts[3]
        low = name.lower()
        bad = BAD.search(name)
        if bad and not (bad.group(0).lower() in ('remix', 'audio') and bad.group(0).lower() in title.lower()):
            continue
        try:
            seconds = float(duration)
        except ValueError:
            continue
        if seconds < length - 8 or seconds > length + 240:
            continue
        score = 0
        score += 3 if 'official' in low and 'video' in low else 0
        score += 2 if 'vevo' in channel.lower() else 0
        score += 2 if main_artist and main_artist in channel.lower() else 0
        score += 1 if title.lower().split('(')[0].strip() in low else 0
        score -= abs(seconds - length) / 60
        found.append((score, f"https://www.youtube.com/watch?v={vid}", name, channel, seconds))
    return sorted(found, reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folders', nargs='+')
    parser.add_argument('--tries', type=int, default=3)
    parser.add_argument('--only', nargs='*', default=[])
    args = parser.parse_args()
    folders = []
    for f in map(Path, args.folders):
        if (f / 'letssing_original.vxla').exists() or any(f.glob('*.txt')):
            folders.append(f)
        else:
            folders += sorted(p for p in f.iterdir() if p.is_dir())
    ConvertFiles._ffmpeg_path = ConvertFiles._ffmpeg_path or 'ffmpeg'
    ConvertFiles._ffprobe_path = getattr(ConvertFiles, '_ffprobe_path', None) or 'ffprobe'
    done = failed = 0
    for folder in folders:
        if args.only and folder.name not in args.only:
            continue
        txt, data = tags(folder)
        if txt is None or data.get('VIDEO'):
            continue
        audio = folder / data.get('MP3', data.get('AUDIO', 'audio.ogg'))
        length = ConvertFiles.get_duration(audio)
        found = candidates(data.get('ARTIST', ''), data.get('TITLE', ''), length)
        saved = False
        for score, url, name, channel, seconds in found[:args.tries]:
            work = Path(tempfile.mkdtemp(prefix='video_', dir=ConvertFiles._big_temp_dir()))
            try:
                video = align_video.download(url, work)
                offset, fits, sure = align_video.measure(audio, video)
                ok = min(fits) >= 0.8 and sure >= 0.2
                print(f"{folder.name}: {'OK ' if ok else 'no '} {name} [{channel}] {seconds:.0f}s "
                      f"start {offset:+.1f}s fits {min(fits):.0%} match {sure:.2f}", flush=True)
                if ok:
                    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'align_video.py'),
                                        str(folder), str(video), '--apply'], capture_output=True, text=True)
                    saved = r.returncode == 0
                    if not saved:
                        print(f"   apply failed: {r.stderr.strip()[-300:]}", flush=True)
            except Exception as e:
                print(f"{folder.name}: error with {url}: {e}", flush=True)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            if saved:
                break
            time.sleep(1)
        if saved:
            done += 1
        else:
            failed += 1
            print(f"{folder.name}: NO VIDEO FOUND ({len(found)} candidates)", flush=True)
    print(f"######## videos: {done} saved, {failed} without", flush=True)


if __name__ == '__main__':
    sys.exit(main())
