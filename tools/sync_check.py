"""Checks whether the lyrics of a song fall where the singer really sings (only reads, changes nothing).

Usage: python tools/sync_check.py <song folder> [--vocals vocals.wav]

The voice is isolated with Demucs (a few minutes on CPU; --vocals reuses a file already separated) and compared
with the notes of the txt, taking #GAP, #START and #END into account the same way the converter does. Prints the
part of the note time that has voice under it, the #GAP shift that fits best and a timeline in 5 s blocks.
A low score that no shift improves means the audio is another cut of the song (see tools/usdb_sources.py).
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ConvertFiles  # noqa: E402
import UltrastarToSingit  # noqa: E402
import naming  # noqa: E402

FRAME = 0.02  # s
BLOCK = 5     # s, timeline


def note_times(txt_data, source_duration):
    """(start, length) of every note in seconds of the source audio file."""
    bpm = float(txt_data['BPM'].replace(',', '.'))
    gap = float(txt_data.get('GAP', '0').replace(',', '.')) / 1000
    lyrics_offset, trim_start, _ = ConvertFiles.audio_window(txt_data, source_duration)
    shift = gap - (lyrics_offset - trim_start)  # the audio is cut at trim_start, the lyrics move by lyrics_offset
    return [(int(n[1]) * 60 / bpm / 4 + shift, int(n[2]) * 60 / bpm / 4)
            for n in txt_data['notes'] if n[0] in (':', '*', 'F', 'R', 'G')]


def voice_activity(vocals_path):
    sr, audio = wavfile.read(vocals_path)
    audio = audio.astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    hop = int(sr * FRAME)
    frames = len(audio) // hop
    energy = np.sqrt(np.mean(audio[:frames * hop].reshape(frames, hop) ** 2, axis=1))
    return energy, (energy > np.percentile(energy, 60)).astype(np.float32)


def coverage(notes, active, shift=0.0):
    cum = np.concatenate([[0], np.cumsum(active)])
    total = inside = 0.0
    for t, d in notes:
        a, b = (t + shift) / FRAME, (t + d + shift) / FRAME
        ia, ib = int(max(0, a)), int(min(len(active), b))
        total += b - a
        if ib > ia:
            inside += cum[ib] - cum[ia]
    return inside / total if total else 0.0


def separate(audio_path, work_dir):
    subprocess.run([sys.executable, '-m', 'demucs', '-n', 'htdemucs', '--two-stems', 'vocals', '-o', work_dir,
                    str(audio_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.join(work_dir, 'htdemucs', Path(audio_path).stem, 'vocals.wav')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('song')
    parser.add_argument('--vocals', help="vocals.wav already separated from the song's audio")
    args = parser.parse_args()

    song_dir = Path(args.song)
    folder = song_dir.name
    txt_path = ConvertFiles.choose_txt_file([p for p in song_dir.iterdir() if p.suffix.lower() == '.txt'])
    txt_data = UltrastarToSingit.parse_file(txt_path)
    audio, _, _ = ConvertFiles.resolve_song_sources(song_dir, txt_data, naming.all_name_ids(folder.rstrip('.')))
    if audio is None:
        sys.exit("no audio file found")
    duration = ConvertFiles.get_duration(audio)
    notes = note_times(txt_data, duration)

    with tempfile.TemporaryDirectory() as tmp:
        vocals = args.vocals or separate(audio, tmp)
        energy, active = voice_activity(vocals)

    now = coverage(notes, active)
    best = max((coverage(notes, active, s), s) for s in np.arange(-60, 60, 0.05))
    # a real offset is the same at the start and at the end of the song
    half = len(notes) // 2
    halves = [max((coverage(part, active, s), s) for s in np.arange(best[1] - 5, best[1] + 5, 0.05))[1]
              for part in (notes[:half], notes[half:])]
    steady = abs(halves[0] - halves[1]) <= 0.3
    end = notes[-1][0] + notes[-1][1]
    print(f"{folder}\n  audio {audio.name}: {duration:.1f} s   letra {notes[0][0]:.1f}-{end:.1f} s")
    if end > duration + 1:
        print(f"  ¡la letra termina {end - duration:.1f} s después del audio!")
    print(f"  notas con voz debajo: {now:.0%} ahora, {best[0]:.0%} moviendo #GAP {best[1] * 1000:+.0f} ms"
          f" (1.ª mitad {halves[0] * 1000:+.0f} ms, 2.ª mitad {halves[1] * 1000:+.0f} ms)")
    if end > duration + 1:
        print("  -> la letra no cabe en este audio: es otra versión de la canción (tools/usdb_sources.py)")
    elif best[0] - now >= 0.05 and steady:
        print(f"  -> desfase fijo: probar #GAP {float(txt_data.get('GAP', '0').replace(',', '.')) + best[1] * 1000:.0f}"
              f" en el Sync Editor")
    elif now >= 0.75:
        print("  -> sincronía correcta")
    else:
        print("  -> ningún desplazamiento fijo la arregla: ¿otra versión del audio? (tools/usdb_sources.py)")

    print(f"\n  {'s':>4}  {'voz':30}  notas")
    blocks = int(max(duration, end) // BLOCK) + 1
    top = max(energy.max(), 1e-9)
    per_block = int(BLOCK / FRAME)
    note_time = [0.0] * blocks
    for t, d in notes:
        if 0 <= t < blocks * BLOCK:
            note_time[int(t // BLOCK)] += d
    for i in range(blocks):
        chunk = energy[i * per_block:(i + 1) * per_block]
        level = float(np.sqrt(np.mean(chunk ** 2))) / top if len(chunk) else 0.0
        print(f"  {i * BLOCK:4d}  {'#' * int(min(level * 60, 30)):30}  {'*' * int(note_time[i] / BLOCK * 30)}")


if __name__ == '__main__':
    main()
