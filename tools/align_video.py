"""Puts a music video in a song folder, cut so it starts and ends with the song's audio.

Usage:
    python tools/align_video.py "<song folder>" <video file or YouTube link>            # only measures
    python tools/align_video.py "<song folder>" <video file or YouTube link> --apply    # cuts and saves it
    python tools/align_video.py "<song folder>" <video without sound> --sound <its audio> [--apply]

The sound of the video is compared with the song's audio to find where the song starts in the video (music videos
often have an intro, a skit or a longer cut). The offset is measured at the start, middle and end of the song: if they
disagree the video is another version of the song and nothing is saved. With --apply the video is cut to the audio
(no sound: the game plays the song's own audio), saved as "<folder>.mp4", the txt's #VIDEO points to it and the
video it replaces is moved to _replaced_videos next to the songs folder. A link is downloaded with yt-dlp (the
YT_DLP environment variable, the yt-dlp of the PATH, the one installed with usdb_syncer by pipx or the Python
module yt_dlp, in that order). The next conversion encodes the .bk2 again only if the current one is the still cover.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import naming  # noqa: E402
import UltrastarToSingit  # noqa: E402

RATE = 4000      # Hz, enough for the rhythm of the music
HOP = 40         # samples: 100 envelope values per second
USDB_SYNCER_YT_DLP = os.path.expanduser('~/.local/share/pipx/venvs/usdb-syncer/bin/yt-dlp')


def yt_dlp_command():
    """How to run yt-dlp on this PC (see the module docstring for the order)."""
    for candidate in (os.environ.get('YT_DLP'), shutil.which('yt-dlp'), USDB_SYNCER_YT_DLP):
        if candidate and os.path.isfile(candidate):
            return [candidate]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, '-m', 'yt_dlp']
    except ImportError:
        sys.exit("yt-dlp not found: install it (pip install yt-dlp) or set YT_DLP to its path")


def envelope(path, seconds=None):
    """Onset strength of the sound of path, 100 values per second."""
    cmd = ['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-']
    if seconds:
        cmd[3:3] = ['-t', str(seconds)]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        sys.exit(f"{Path(path).name} has no sound to compare with the song: pass its audio with --sound")
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    frames = len(samples) // HOP - 4
    if frames <= 0:
        return np.zeros(0)
    window = np.hanning(HOP * 4)
    spec = np.abs(np.fft.rfft(np.lib.stride_tricks.sliding_window_view(samples, HOP * 4)[::HOP][:frames] * window,
                              axis=1))
    flux = np.maximum(0, np.diff(np.log1p(spec), axis=0)).sum(axis=1)
    flux -= flux.mean()
    return flux / (flux.std() or 1)


def correlations(song, video):
    """Correlation of the song with the video for every lag (index: frames to skip in the video; negative wraps)."""
    n = 1 << int(np.ceil(np.log2(len(song) + len(video))))
    corr = np.fft.irfft(np.fft.rfft(video, n) * np.conj(np.fft.rfft(song, n)), n)
    return np.concatenate([corr[:len(video)], corr[n - len(song) + 1:]]) / max(len(song), 1)


def measure(audio, video, parts=4):
    """(offset in seconds of the song inside the video, per-part fit at that offset 0..1, overall match).
    The fit of a part is its correlation at the global offset divided by its best correlation anywhere: near 1 when
    that part of the song is at the same place in the video (a repeated beat can make another place almost as good)."""
    song, clip = envelope(audio), envelope(video)
    corr = correlations(song, clip)
    index = int(np.argmax(corr))
    lag = index if index < len(clip) else index - len(corr)
    fits = []
    size = len(song) // parts
    for i in range(parts):
        piece = song[i * size:(i + 1) * size]
        c = correlations(piece, clip)
        at = lag + i * size
        here = c[at] if -len(piece) < at < len(clip) else 0.0  # negative lags sit at the end of c
        fits.append(float(here / c.max()) if c.max() > 0 else 0.0)
    return lag / 100, fits, float(corr[index])


def download(url, folder):
    out = Path(folder) / 'downloaded.%(ext)s'
    subprocess.run([*yt_dlp_command(), '-q', '--no-playlist', '-f', 'bv*[height<=720]+ba/b[height<=720]/b', '--merge-output-format',
                    'mp4', '-o', str(out), url], check=True)
    return next(Path(folder).glob('downloaded.*'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('song')
    parser.add_argument('video')
    parser.add_argument('--sound', help="audio that goes with the video, when the video file has no sound")
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    d = Path(args.song)
    txt = ConvertFiles.choose_txt_file([p for p in d.iterdir() if p.suffix.lower() == '.txt'])
    data = UltrastarToSingit.parse_file(txt)
    ids = [naming.construct_name_id_from_directory_name(d.name)] + naming.legacy_name_ids(d.name)
    audio, current, _ = ConvertFiles.resolve_song_sources(d, data, ids)
    work = tempfile.mkdtemp(prefix='align_', dir=ConvertFiles._big_temp_dir())
    try:
        video = Path(args.video)
        if args.video.startswith(('http://', 'https://')):
            print("downloading...", flush=True)
            video = download(args.video, work)
        length = ConvertFiles.get_duration(audio)
        offset, fits, sure = measure(audio, args.sound or video)
        print(f"audio {audio.name} {length:.1f} s | video {video.name} {ConvertFiles.get_duration(video):.1f} s")
        print(f"the song starts at {offset:+.2f} s of the video (fit of each quarter of the song there: "
              f"{', '.join(f'{f:.0%}' for f in fits)}; match {sure:.2f})")
        if min(fits) < 0.8 or sure < 0.2:
            sys.exit("the video does not follow the song all the way (another cut or version): nothing saved")
        ConvertFiles._ffmpeg_path = ConvertFiles._ffmpeg_path or 'ffmpeg'
        if ConvertFiles.is_video_still_image(video):
            sys.exit("the video is a still image: nothing saved")
        if not args.apply:
            print("run again with --apply to save it")
            return
        target = d / (d.name + '.mp4')
        tmp = Path(work) / 'cut.mp4'
        start = ['-ss', f'{offset:.3f}'] if offset > 0 else []
        # the first/last frame stays on screen when the video starts after or ends before the song
        missing_end = max(0.0, length - (ConvertFiles.get_duration(video) - offset)) + 0.5
        pad = ['-vf', f'tpad=start_duration={max(0.0, -offset):.3f}:start_mode=clone:'
                      f'stop_duration={missing_end:.3f}:stop_mode=clone']
        subprocess.run(['ffmpeg', '-v', 'error', '-y', *start, '-i', str(video), '-t', f'{length:.3f}', '-an', *pad,
                        '-c:v', 'libx264', '-crf', '18', '-preset', 'slow', '-pix_fmt', 'yuv420p', str(tmp)],
                       check=True)
        if target.exists() or (current and current.exists() and current.suffix.lower() != '.bk2'):
            keep = d.parent.parent / '_replaced_videos' / d.name
            keep.mkdir(parents=True, exist_ok=True)
            for old in {p for p in (target, current) if p and p.exists() and p.suffix.lower() != '.bk2'}:
                shutil.move(old, keep / f"{old.stem}.{time.strftime('%Y%m%d-%H%M%S')}{old.suffix}")
                print(f"moved {old.name} to {keep}")
        shutil.move(tmp, target)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import usdb_restore_names
        raw, encoding, lines = usdb_restore_names.read_txt(txt)
        if any(line.upper().startswith('#VIDEO:') for line in lines):
            usdb_restore_names.set_tag(lines, 'VIDEO', target.name)
        else:
            lines.insert(next(i for i, line in enumerate(lines) if not line.startswith('#')), f"#VIDEO:{target.name}\n")
        backup = txt.with_name(txt.name + '.bak')
        if not backup.exists():
            backup.write_bytes(raw)
        txt_tmp = txt.with_name(txt.name + '.tmp')
        txt_tmp.write_bytes(''.join(lines).encode(encoding))
        os.replace(txt_tmp, txt)
        print(f"saved {target} ({target.stat().st_size / 2**20:.1f} MB); convert the song to make its .bk2")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
