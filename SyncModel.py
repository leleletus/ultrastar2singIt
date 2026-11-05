"""Timing model of the sync editor and of tools/sync_scan.py (no Qt here).

- Notes and shown syllables of an UltraStar txt or of an official vxla, with the line each note belongs to.
- Pitch detection (YIN) for the microphone and for the isolated voice.
- Voice analysis of a song: the voice is isolated with Demucs and its loudness and pitch are kept every 20 ms in
  <id>.voice.npz next to the song, so the analysis is done once.
- Per line, how far the singer is from the notes: finds lyrics that drift, or a part that needs to be moved.
"""
import bisect
import math
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

import naming

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
FRAME = 0.02            # s, voice analysis step
HIT_SEMITONES = 1.0     # sung pitch counted as right within this distance (any octave, like the game)
VOICE_VERSION = 1


def note_name(midi):
    m = int(round(midi))
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def hz_to_midi(hz):
    return 69 + 12 * math.log2(hz / 440.0)


def fold_to(midi, target):
    """The same pitch class in the octave closest to target (the game does not care about the octave)."""
    return midi + 12 * round((target - midi) / 12)


def detect_pitch(samples, sample_rate, fmin=70.0, fmax=1100.0, threshold=0.15, min_rms=0.01):
    """Fundamental frequency (Hz) of a mono float block in [-1, 1] with the YIN method, None if there is no voice."""
    x = np.asarray(samples, dtype=np.float64)
    x = x - x.mean()
    if len(x) < 64 or math.sqrt(float(np.mean(x * x))) < min_rms:
        return None
    n = len(x)
    tau_max = min(int(sample_rate / fmin), n // 2)
    tau_min = max(2, int(sample_rate / fmax))
    if tau_max <= tau_min + 2:
        return None
    w = n - tau_max
    size = 1 << (n + w).bit_length()
    corr = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(x[:w], size)), size)[:tau_max + 1]
    cum = np.concatenate(([0.0], np.cumsum(x * x)))
    taus = np.arange(tau_max + 1)
    diff = cum[w] + (cum[taus + w] - cum[taus]) - 2 * corr
    cmnd = np.ones_like(diff)
    running = np.cumsum(diff[1:])
    cmnd[1:] = diff[1:] * taus[1:] / np.where(running > 0, running, 1)
    below = np.nonzero(cmnd[tau_min:tau_max] < threshold)[0]
    if len(below):
        tau = tau_min + int(below[0])
        while tau + 1 < tau_max and cmnd[tau + 1] < cmnd[tau]:
            tau += 1
    else:
        tau = tau_min + int(np.argmin(cmnd[tau_min:tau_max]))
        if cmnd[tau] > 0.35:
            return None
    if 1 <= tau < tau_max:  # parabolic interpolation around the minimum
        a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
        den = a - 2 * b + c
        if den:
            tau = tau + 0.5 * (a - c) / den
    return sample_rate / tau if tau > 0 else None


# ---------------------------------------------------------------------------------------------- notes
class Note:
    __slots__ = ('t', 'd', 'pitch', 'kind', 'line')

    def __init__(self, t, d, pitch, kind, line=0):
        self.t, self.d, self.pitch, self.kind, self.line = t, d, pitch, kind, line

    @property
    def sung(self):  # rap/freestyle notes have no pitch
        return self.kind in (':', '*')


class Song:
    """notes: Note list (seconds without #GAP for a txt); syllables: (t, d, text, line);
    lines: syllable indices of every line (a line can have no shown syllable); bpm: None for an official vxla."""

    def __init__(self, notes, syllables, lines, bpm=None):
        self.notes, self.syllables, self.lines, self.bpm = notes, syllables, lines, bpm
        self.note_starts = [n.t for n in notes]
        self.line_starts, self.line_ends = [], []
        by_line = {}
        for n in notes:
            by_line.setdefault(n.line, []).append(n)
        for i in range(len(lines)):
            own = by_line.get(i, [])
            previous = self.line_ends[-1] if self.line_ends else 0.0
            self.line_starts.append(min(n.t for n in own) if own else previous)
            self.line_ends.append(max(n.t + n.d for n in own) if own else previous)


def txt_notes(us_data):
    """(notes, raw texts, line count, bpm) of an UltraStar txt: every note in file order with its text as written
    ("~" held notes included), in seconds without #GAP."""
    bpm = float(us_data["BPM"].replace(',', '.'))
    beat = 60.0 / bpm / 4
    notes, texts, line_count, has_notes = [], [], 0, False
    for n in us_data["notes"]:
        if n[0] in (':', '*', 'F', 'R', 'G'):
            t, d = int(n[1]) * beat, max(int(n[2]), 1) * beat
            notes.append(Note(t, d, int(n[3]) + 60, n[0], line_count))  # UltraStar pitch 0 = C4 = MIDI 60
            texts.append(n[4])
            has_notes = True
        elif n[0] == '-' and has_notes:
            line_count += 1
            has_notes = False
    return notes, texts, line_count + (1 if has_notes else 0), bpm


def song_from_notes(notes, texts, line_count, bpm, deleted=()):
    """Song of txt notes (txt_notes) leaving out the deleted note indices; lines keep their numbers (a line whose
    notes are all deleted stays, empty)."""
    kept, syllables, lines = [], [], [[] for _ in range(line_count)]
    for i, (note, raw) in enumerate(zip(notes, texts)):
        if i in deleted:
            continue
        kept.append(note)
        text = raw.replace('~', '')
        if text.strip():
            lines[note.line].append(len(syllables))
            syllables.append((note.t, note.d, text, note.line))
        elif text and syllables:  # "~ ": the space ends the previous word
            t0, d0, prev, ln = syllables[-1]
            syllables[-1] = (t0, d0, prev if prev.endswith(' ') else prev + ' ', ln)
    return Song(kept, syllables, lines, bpm)


def load_txt(us_data):
    """Notes and shown syllables of an UltraStar txt, in seconds without #GAP."""
    return song_from_notes(*txt_notes(us_data))


def load_official(path):
    """Notes and shown syllables of an official vxla, in seconds (the converter uses it as it is)."""
    import OfficialVxla
    layers, _ = OfficialVxla.read_layers(path)
    sing_it = OfficialVxla.to_sing_it(layers, 3600.0)
    pages = sorted((p["t1"], p["t2"]) for p in sing_it["pages"]) or [(0.0, 3600.0)]
    page_ends = [p[1] for p in pages]
    page_of = lambda t: min(bisect.bisect_right(page_ends, t), len(pages) - 1)
    notes = []
    for item in sing_it["notes"]:
        m = re.match(r'#p(\d+)#\.(.*)', item["value"])
        if not m:
            continue
        pitch, rest = int(m.group(1)), m.group(2)
        kind = 'F' if pitch <= 1 else ('*' if '#g' in rest else ':')
        notes.append(Note(item["t1"], item["t2"] - item["t1"], pitch, kind, page_of(item["t1"])))
    notes.sort(key=lambda n: n.t)
    syllables = [(s["t1"], s["t2"] - s["t1"], s["value"], page_of(s["t1"]))
                 for s in sorted(sing_it["text"], key=lambda s: s["t1"])]
    used = sorted({n.line for n in notes} | {s[3] for s in syllables})
    renumber = {old: new for new, old in enumerate(used)}
    for n in notes:
        n.line = renumber[n.line]
    syllables = [(t, d, text, renumber[ln]) for t, d, text, ln in syllables]
    lines = [[] for _ in used]
    for i, s in enumerate(syllables):
        lines[s[3]].append(i)
    return Song(notes, syllables, lines)


# ---------------------------------------------------------------------------------------------- voice
def voice_cache_path(song_dir):
    folder = os.path.basename(os.path.normpath(song_dir)).rstrip('.')
    return os.path.join(song_dir, naming.construct_name_id_from_directory_name(folder) + naming.VOICE_SUFFIX)


def isolate_voice(audio_path, work_dir):
    """vocals.wav of the song with Demucs (a few minutes on CPU)."""
    subprocess.run([sys.executable, '-m', 'demucs', '-n', 'htdemucs', '--two-stems', 'vocals', '-o', work_dir,
                    str(audio_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return os.path.join(work_dir, 'htdemucs', os.path.splitext(os.path.basename(audio_path))[0], 'vocals.wav')


def voice_track(vocals_path):
    """(energy, midi pitch or nan) of the isolated voice every FRAME seconds."""
    from scipy.io import wavfile
    rate, audio = wavfile.read(vocals_path)
    audio = audio.astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if np.issubdtype(np.asarray(audio).dtype, np.floating) and np.abs(audio).max() > 2:
        audio = audio / 32768.0
    hop, win = int(rate * FRAME), int(rate * 0.04)
    frames = max(0, (len(audio) - win) // hop)
    energy = np.zeros(frames, dtype=np.float32)
    pitch = np.full(frames, np.nan, dtype=np.float32)
    for i in range(frames):
        block = audio[i * hop:i * hop + win]
        energy[i] = math.sqrt(float(np.mean(block * block)))
        if energy[i] > 0.01:
            hz = detect_pitch(block, rate, min_rms=0.01)
            if hz:
                pitch[i] = hz_to_midi(hz)
    return energy, pitch


def analyze_voice(audio_path, cache_path):
    """Isolates the voice of audio_path and saves its loudness and pitch to cache_path."""
    # on disk, not in /tmp: /tmp is often in RAM and the separated tracks of a song take hundreds of MB
    work_root = os.path.join(os.path.expanduser('~'), '.cache', 'letssing_converter')
    os.makedirs(work_root, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work_root) as tmp:
        energy, pitch = voice_track(isolate_voice(audio_path, tmp))
    tmp_path = cache_path + '.tmp.npz'
    np.savez_compressed(tmp_path, energy=energy.astype(np.float16), pitch=pitch.astype(np.float16),
                        audio=os.path.basename(audio_path), audio_size=os.path.getsize(audio_path),
                        version=VOICE_VERSION)
    os.replace(tmp_path, cache_path)


def load_voice(cache_path, audio_path):
    """The cached analysis if it was made from this same audio file, else None."""
    try:
        data = np.load(cache_path)
        if int(data['version']) != VOICE_VERSION or int(data['audio_size']) != os.path.getsize(audio_path):
            return None
        energy = data['energy'].astype(np.float32)
        return {'energy': energy, 'pitch': data['pitch'].astype(np.float32),
                'active': energy > max(0.01, float(np.percentile(energy, 60)))}
    except (OSError, KeyError, ValueError):
        return None


def line_report(song, voice, shift_of_line, max_shift=3.0, step=0.04):
    """For every line: (score now, best extra shift in s, score with it). shift_of_line(i) = seconds added to it.
    The score (0-1) is how much of the notes has voice under it, counting double when the pitch is right (any
    octave, like the game); rap notes only need voice."""
    active, pitch = voice['active'].astype(np.float32), voice['pitch']
    frames = len(active)
    steps = int(round(max_shift / step))
    offsets = np.arange(-steps, steps + 1) * step
    offset_frames = np.round(offsets / FRAME).astype(int)[:, None]
    by_line = {}
    for n in song.notes:
        by_line.setdefault(n.line, []).append(n)
    report = []
    for i in range(len(song.lines)):
        notes = by_line.get(i, [])
        if not notes:
            report.append((None, 0.0, None))
            continue
        base = shift_of_line(i)
        total = np.zeros(len(offsets))
        weight = 0.0
        for n in notes:
            count = max(1, int(round(n.d / FRAME)))
            idx = int(round((n.t + base) / FRAME)) + offset_frames + np.arange(count)[None, :]
            inside = (idx >= 0) & (idx < frames)
            idx = np.clip(idx, 0, frames - 1)
            act = active[idx] * inside
            if n.sung:
                p = pitch[idx]
                right = np.abs(((np.nan_to_num(p, nan=-100.0) - n.pitch + 6) % 12) - 6) <= HIT_SEMITONES
                right &= ~np.isnan(p)
                act = act * (0.5 + 0.5 * right)
            total += act.mean(axis=1) * n.d
            weight += n.d
        scores = total / weight
        now = float(scores[steps])
        best = int(np.argmax(scores))
        # prefer no change when the gain is small (repeated notes fit at many offsets), and never trust a best shift
        # at the edge of the search: it is the line fitting the phrase next to it (checked on official songs)
        if scores[best] - now < 0.12 or abs(offsets[best]) > max_shift - 0.25:
            report.append((now, 0.0, now))
        else:
            report.append((now, float(offsets[best]), float(scores[best])))
    return report


def runs_out_of_time(report, line_times, min_lines=3, spread=0.25, min_shift=0.3):
    """Blocks of at least min_lines lines in a row moved by about the same amount: (first time, shift, lines).
    A real desync moves a whole part; single lines that fit somewhere else are noise (repeated phrases)."""
    rows = [(t, extra) for t, (now, extra, _) in zip(line_times, report) if now is not None]
    runs, i = [], 0
    while i < len(rows):
        j = i
        while j < len(rows) and abs(rows[j][1]) >= min_shift and abs(rows[j][1] - rows[i][1]) <= spread:
            j += 1
        if j - i >= min_lines:
            runs.append((rows[i][0], float(np.median([e for _, e in rows[i:j]])), j - i))
            i = j
        else:
            i += 1
    return runs


def song_verdict(report, line_times, audio_end, lyrics_end):
    """Short diagnosis of a song from its line report."""
    if lyrics_end > audio_end + 1:
        return 'otra_version', f"la letra termina {lyrics_end - audio_end:.1f} s después del audio"
    rows = [(t, now, extra) for t, (now, extra, _) in zip(line_times, report) if now is not None]
    if not rows:
        return 'sin_notas', ''
    mean_now = sum(r[1] for r in rows) / len(rows)
    runs = runs_out_of_time(report, line_times)
    moved = sum(n for _, _, n in runs)
    if moved >= 0.6 * len(rows):
        median = float(np.median([e for _, e, n in runs for _ in range(n)]))
        return 'desfase', f"toda la letra {median * 1000:+.0f} ms"
    if runs:
        parts = ', '.join(f"{int(t // 60)}:{t % 60:04.1f} ({e * 1000:+.0f} ms, {n} líneas)" for t, e, n in runs[:4])
        return 'parcial', f"{moved} de {len(rows)} líneas fuera de tiempo: {parts}"
    # official songs (game timing) match 38-77 %: only far below that is the voice really missing
    return ('ok' if mean_now >= 0.30 else 'dudosa'), f"coincidencia {mean_now:.0%}"


# ---------------------------------------------------------------------------------------------- saving
_NOTE_LINE = re.compile(r'^(\s*[:*FRG]\s+)(-?\d+)(\s.*)?$')
_NOTE_REST = re.compile(r'^(\s+-?\d+\s+)(-?\d+)(.*)$')
_BREAK_LINE = re.compile(r'^(\s*-\s*)(-?\d+)(\s+(-?\d+))?(.*)$')


def rewrite_txt(lines, gap_ms, line_beats=None, expected_notes=None, note_pitches=None, note_texts=None,
                deleted_notes=None):
    """The txt lines with #GAP set and, when line_beats is given, the notes of every lyrics line i moved by
    line_beats[i] beats (page breaks follow the line after them). Same line numbering as load_txt.
    note_pitches: {note index (order of load_txt): new UltraStar pitch} changes only those pitches.
    note_texts: {note index: new syllable text}; deleted_notes: note indices taken out (a line left without notes
    loses its page break too).
    Raises ValueError when the file cannot be changed safely."""
    out = list(lines)
    gap_line = f"#GAP:{int(round(gap_ms))}"
    for i, line in enumerate(out):
        if line.upper().startswith("#GAP:"):
            out[i] = gap_line
            break
    else:
        # no #GAP tag: insert it after the last header line
        insert_at = 0
        for i, line in enumerate(out):
            if line.startswith('#'):
                insert_at = i + 1
            elif line.strip():
                break
        out.insert(insert_at, gap_line)

    if (not line_beats or not any(line_beats)) and not note_pitches and not note_texts and not deleted_notes:
        return out
    line_beats = line_beats or [0]
    note_pitches = note_pitches or {}
    headers = {l.split(':', 1)[0].strip().upper(): l.split(':', 1)[-1].strip().upper() for l in out if l.startswith('#')}
    if headers.get('#RELATIVE') == 'YES' or any(l.strip()[:2] in ('P1', 'P2') for l in out if not l.startswith('#')):
        raise ValueError("relative or duet files: only #GAP can be changed")
    count, line_no, has_notes, last_end = 0, 0, False, None
    previous_end, open_break = None, None   # end of the line before; page break waiting for its next line
    for i, line in enumerate(out):
        if line.startswith('#'):
            continue
        m = _NOTE_LINE.match(line)
        if m:
            delta = line_beats[min(line_no, len(line_beats) - 1)]
            start = int(m.group(2)) + delta
            length = int(m.group(3).split()[0]) if m.group(3) and m.group(3).split() else 0
            if not has_notes and previous_end is not None and start < previous_end:
                raise ValueError(f"line {line_no + 1} would start before the end of line {line_no}")
            if open_break is not None:
                j, prefix, beat, rest = open_break
                out[j] = f"{prefix}{min(beat, start)}{rest}"  # the break stays between the two lines
                open_break = None
            rest = m.group(3) or ''
            if count in note_pitches:  # " <length> <pitch> <text>": only the pitch changes
                p = _NOTE_REST.match(rest)
                if not p:
                    raise ValueError(f"note {count + 1} has no pitch to change")
                rest = f"{p.group(1)}{int(note_pitches[count])}{p.group(3)}"
            out[i] = f"{m.group(1)}{start}{rest}"
            last_end = start + length if last_end is None or not has_notes else max(last_end, start + length)
            count += 1
            has_notes = True
            continue
        m = _BREAK_LINE.match(line)
        if m and has_notes:
            line_no += 1
            has_notes = False
            previous_end = last_end
            delta = line_beats[min(line_no, len(line_beats) - 1)]
            beat = max(int(m.group(2)) + delta, last_end)  # never before the end of the line it closes
            rest = m.group(5) if not m.group(3) else f" {int(m.group(4)) + delta}{m.group(5)}"
            out[i] = f"{m.group(1)}{beat}{rest}"
            open_break = (i, m.group(1), beat, rest)
    if expected_notes is not None and count != expected_notes:
        raise ValueError(f"found {count} notes in the file but {expected_notes} were loaded")
    if note_texts or deleted_notes:
        out = _edit_notes(out, note_texts or {}, set(deleted_notes or ()))
    return out


_NOTE_TEXT = re.compile(r'^(\s*[:*FRG]\s+-?\d+\s+-?\d+\s+-?\d+)(?: (.*))?$')


def _edit_notes(lines, texts, deleted):
    """Changes the text of some notes and takes others out (note indices in file order); page breaks left with no
    line before them go too (a break keeps the beat of the first one, which stays between the lines around it)."""
    out, count = [], 0
    for line in lines:
        if not line.startswith('#') and _NOTE_LINE.match(line):
            index, count = count, count + 1
            if index in deleted:
                continue
            if index in texts:
                m = _NOTE_TEXT.match(line)
                if not m:
                    raise ValueError(f"note {index + 1} has no text to change")
                line = f"{m.group(1)} {texts[index]}"
        out.append(line)
    result, notes_since_break = [], False
    for line in out:
        if not line.startswith('#') and _BREAK_LINE.match(line):
            if not notes_since_break:
                continue  # nothing left before it (a deleted line, or the start)
            notes_since_break = False
        elif not line.startswith('#') and _NOTE_LINE.match(line):
            notes_since_break = True
        result.append(line)
    # a page break with no notes after it (the last lines were deleted)
    for i in range(len(result) - 1, -1, -1):
        line = result[i]
        if not line.startswith('#') and _NOTE_LINE.match(line):
            break
        if not line.startswith('#') and _BREAK_LINE.match(line):
            del result[i]
            break
    return result
