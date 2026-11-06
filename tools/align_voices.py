"""Prepares the lyrics alignment of songs (VoiceAlign): isolates the voice (Demucs, <id>.vocals.flac) and runs the
speech model on it (<id>.ctc.npz). Resumable: what a folder already has is skipped, so after a power cut the same
command carries on. One song at a time (CPU and memory heavy).

Usage:
    python tools/align_voices.py <songs folder> [--only "LISA - MONEY" ...] [--list file] [--songmaker] [--vocals-only]

--songmaker: every SongMaker song; --list: a file with one folder name per line.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import VoiceAlign  # noqa: E402


def audio_of(folder):
    """The audio file the voice analysis was made from (else the txt's #MP3/#AUDIO)."""
    for npz in folder.glob('*.voice.npz'):
        try:
            name = str(np.load(npz)['audio'])
            if (folder / name).exists():
                return folder / name
        except (OSError, KeyError, ValueError):
            pass
    for txt in folder.glob('*.txt'):
        for line in txt.read_text(encoding='utf-8', errors='replace').splitlines():
            if line.startswith(('#AUDIO:', '#MP3:')) and (folder / line.split(':', 1)[1].strip()).exists():
                return folder / line.split(':', 1)[1].strip()
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('--only', nargs='*', default=[])
    parser.add_argument('--list')
    parser.add_argument('--songmaker', action='store_true')
    parser.add_argument('--vocals-only', action='store_true', help='only Demucs (the model is not needed)')
    args = parser.parse_args()
    songs = Path(args.songs)
    names = list(args.only)
    if args.list:
        names += [x.strip().rstrip('/') for x in Path(args.list).read_text(encoding='utf-8').splitlines() if x.strip()]
    if args.songmaker:
        names += sorted(d for d in os.listdir(songs) if (songs / d / 'songmaker.json').exists())
    done, failed = 0, []
    for name in dict.fromkeys(names):
        folder = songs / name
        audio = audio_of(folder)
        if audio is None:
            print(f"{name}: no audio, skipped", flush=True)
            continue
        vocals, ctc = VoiceAlign.paths(str(folder))
        if os.path.exists(ctc if not args.vocals_only else vocals):
            continue
        t = time.time()
        try:
            if args.vocals_only:
                import tempfile
                import SyncModel
                root = os.path.join(os.path.expanduser('~'), '.cache', 'letssing_converter')
                os.makedirs(root, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=root) as tmp:
                    VoiceAlign.save_vocals(SyncModel.isolate_voice(str(audio), tmp), vocals)
            else:
                VoiceAlign.prepare(str(folder), str(audio))
            done += 1
            print(f"{name}: ready in {time.time() - t:.0f} s", flush=True)
        except Exception as e:
            failed.append(name)
            print(f"FAILED {name}: {e}", flush=True)
    print(f"######## {done} done" + (f", failed: {failed}" if failed else ''), flush=True)


if __name__ == '__main__':
    main()
