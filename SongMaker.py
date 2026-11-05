"""Makes an UltraStar song that USDB does not have: video and audio from YouTube, timed lyrics from LRCLIB, notes from
the singer's voice.

    1. the video (with its own sound, already in sync) is downloaded with yt-dlp; its audio is the song's audio. With
       an official audio upload as well, the video is compared with it (tools/align_video.measure): when it holds the
       whole song without breaks it is kept uncut, intro included (the lyrics start at #GAP; the skip-intro mod jumps
       long intros); when scenes break the song (The One That Got Away), the official audio is used and the video is
       rebuilt from the pieces that follow it (cut_video_to_audio);
    2. LRCLIB (lrclib.net) gives the lyrics with the start time of every line; versions of the same song are timed for
       different cuts (album, video), so every version is tried at every offset against the singer's voice and the one
       that fits best is used;
    3. the voice is isolated with Demucs and followed every 20 ms (SyncModel: energy and pitch);
    4. in every line the voice is cut into notes at silences and pitch jumps, and the syllables of the line go to the
       note starts with the strongest attack (more notes than syllables: the rest are held "~"; fewer: the longest
       notes are split);
    5. the result is a plain UltraStar folder ("Artist - Title/" with .txt, .m4a, .mp4 and cover) that the converter
       and the sync editor use like any other song.

Korean lyrics are romanized (Revised Romanization, one syllable per Hangul block) as Let's Sing shows them.
The notes are a starting point: check the song in the sync editor (notes can be moved in time and in pitch there).
"""
import json
import logging
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np

import SyncModel

logger = logging.getLogger(__name__)

LRCLIB = 'https://lrclib.net/api/search'
USER_AGENT = 'LetsSingUltraStarConverter (personal karaoke; https://github.com/leleletus/ultrastar2singIt)'
BPM = 400                       # UltraStar beat = 60 / BPM / 4 s = 37.5 ms
BEAT_S = 60 / BPM / 4
FRAME = SyncModel.FRAME         # 20 ms
GAP_FRAMES = 3                  # a silence of 60 ms ends a note
JUMP_SEMITONES = 1.2            # a pitch change this big, held 3 frames, starts a new note
MIN_NOTE_FRAMES = 4             # 80 ms
LINE_MAX_S = 12.0


# ---------------------------------------------------------------------------
# Lyrics
# ---------------------------------------------------------------------------

def parse_lrc(text):
    """[(seconds, line)] of an LRC text (tags and empty lines left out)."""
    out = []
    for raw in (text or '').splitlines():
        stamps = re.findall(r'\[(\d+):(\d+(?:\.\d+)?)\]', raw)
        line = re.sub(r'\[[^\]]*\]', '', raw).strip()
        if not stamps or not line:
            continue
        for minutes, seconds in stamps:
            out.append((int(minutes) * 60 + float(seconds), line))
    return sorted(out)


def lrclib_versions(artist, title):
    """[(id, duration, [(seconds, line)])] of the timed lyrics LRCLIB has for the song."""
    import requests
    response = requests.get(LRCLIB, params={'artist_name': artist, 'track_name': title}, timeout=20,
                            headers={'User-Agent': USER_AGENT})
    response.raise_for_status()
    out = []
    for hit in response.json():
        lines = parse_lrc(hit.get('syncedLyrics'))
        if len(lines) >= 4:
            out.append((hit['id'], hit.get('duration'), lines))
    return out


def fit_lyrics(versions, energy, duration, intro=0.0):
    """(version, offset in s, score) whose line starts fall where the singer starts singing. duration: length of the
    song itself; intro: seconds the song starts later in a music video kept uncut (offsets are tried around it)."""
    voiced = (energy > _voice_threshold(energy)).astype(np.float32)
    n = len(voiced)
    cumulative = np.concatenate([[0], np.cumsum(voiced)])

    def share(a, b):  # voiced share of frames [a, b)
        a, b = max(0, min(n, a)), max(0, min(n, b))
        return (cumulative[b] - cumulative[a]) / (b - a) if b > a else 0.0

    best = (None, 0.0, -1.0)
    for version in versions:
        _, length, lines = version
        if length and duration and abs(length - duration) > 25:
            continue
        starts = np.array([t for t, _ in lines])
        for offset in np.arange(intro - 20.0, intro + 20.0, 0.05):
            frames = ((starts + offset) / FRAME).astype(int)
            if frames[0] < 0 or frames[-1] >= n:
                continue
            after = np.mean([share(f, f + int(1.2 / FRAME)) for f in frames])
            before = np.mean([share(f - int(0.5 / FRAME), f - 1) for f in frames])
            score = after - 0.5 * before
            if score > best[2]:
                best = (version, round(float(offset), 2), float(score))
    return best


# ---------------------------------------------------------------------------
# Syllables
# ---------------------------------------------------------------------------

_ES_VOWELS = 'aeiouáéíóúü'
_ES_STRONG = 'aeoáéíóú'           # an accented i/u breaks the diphthong (hiatus) like a strong vowel
_ES_CLUSTERS = {'pr', 'pl', 'br', 'bl', 'fr', 'fl', 'tr', 'dr', 'cr', 'cl', 'gr', 'gl', 'kr', 'kl', 'ch', 'll', 'rr'}


def _es_is_vowel(word, i):
    c = word[i]
    if c == 'y':  # "muy", "hoy", "y": a vowel at the end of a word or before a consonant
        return i == len(word) - 1 or (i + 1 < len(word) and word[i + 1] not in _ES_VOWELS)
    if c == 'u' and i > 0 and word[i - 1] in 'qg' and i + 1 < len(word) and word[i + 1] in 'eiéí':
        return False  # "que", "guitarra": the u is not said
    return c in _ES_VOWELS


def syllables_es(word):
    """Spanish syllables of a word, keeping its letters (and accents) as written."""
    low = word.lower()
    letters = [i for i, c in enumerate(low) if c.isalpha()]
    if not letters:
        return [word]
    kinds = ['V' if c.isalpha() and _es_is_vowel(low, i) else ('C' if c.isalpha() else '-') for i, c in enumerate(low)]
    # vowel groups: split two strong vowels (hiatus)
    nuclei = []
    i = 0
    while i < len(low):
        if kinds[i] == 'V':
            j = i + 1
            while j < len(low) and kinds[j] == 'V' and not (low[j - 1] in _ES_STRONG and low[j] in _ES_STRONG):
                j += 1
            nuclei.append((i, j))
            i = j
        else:
            i += 1
    if len(nuclei) <= 1:
        return [word]
    cuts = []
    for (a1, b1), (a2, b2) in zip(nuclei, nuclei[1:]):
        consonants = [k for k in range(b1, a2) if kinds[k] == 'C']
        cluster = ''.join(low[k] for k in consonants)
        if not consonants:
            cuts.append(a2)
        elif len(consonants) == 1:
            cuts.append(consonants[0])
        elif len(consonants) == 2:
            cuts.append(consonants[0] if cluster in _ES_CLUSTERS else consonants[1])
        else:
            cuts.append(consonants[-2] if cluster[-2:] in _ES_CLUSTERS else consonants[-1])
    pieces, last = [], 0
    for cut in cuts:
        pieces.append(word[last:cut])
        last = cut
    pieces.append(word[last:])
    return [p for p in pieces if p]


def syllables_en(word):
    """Rough English syllables: one per vowel group (a final silent 'e' joins the one before)."""
    low = word.lower()
    groups = [m.span() for m in re.finditer(r'[aeiouy]+', low)]
    if len(groups) > 1 and low.endswith('e') and groups[-1] == (len(low) - 1, len(low)) and not low.endswith('le'):
        groups = groups[:-1]
    if len(groups) <= 1:
        return [word]
    cuts = []
    for (a1, b1), (a2, b2) in zip(groups, groups[1:]):
        gap = a2 - b1
        cuts.append(b1 + (gap + 1) // 2 if gap > 1 else a2 - gap)
    pieces, last = [], 0
    for cut in cuts:
        pieces.append(word[last:cut])
        last = cut
    pieces.append(word[last:])
    return [p for p in pieces if p]


_KO_INITIAL = ['g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp', 's', 'ss', '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h']
_KO_VOWEL = ['a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye', 'o', 'wa', 'wae', 'oe', 'yo', 'u', 'wo', 'we', 'wi', 'yu',
             'eu', 'ui', 'i']
_KO_FINAL = ['', 'k', 'k', 'k', 'n', 'n', 'n', 't', 'l', 'k', 'm', 'l', 'l', 'l', 'p', 'l', 'm', 'p', 'p', 't', 't',
             'ng', 't', 't', 'k', 't', 'p', 't']


def romanize_block(char):
    code = ord(char) - 0xAC00
    if not 0 <= code < 11172:
        return char
    return _KO_INITIAL[code // 588] + _KO_VOWEL[(code % 588) // 28] + _KO_FINAL[code % 28]


def is_hangul(char):
    return 0xAC00 <= ord(char) < 0xAC00 + 11172


def line_syllables(line, language):
    """[syllable text] of a lyrics line; the last syllable of every word ends with a space (UltraStar style)."""
    out = []
    for word in line.split():
        if any(is_hangul(c) for c in word):
            pieces, latin = [], ''
            for c in word:
                if is_hangul(c):
                    if latin:
                        if re.search(r'[A-Za-z]', latin) or not pieces:
                            pieces += syllables_en(latin)
                        else:
                            pieces[-1] += latin
                        latin = ''
                    pieces.append(romanize_block(c))
                else:
                    latin += c
            if latin:
                if re.search(r'[A-Za-z]', latin) or not pieces:
                    pieces += syllables_en(latin)
                else:
                    pieces[-1] += latin  # punctuation after a Hangul block stays with it
            if pieces and not re.search(r'[A-Za-z]', pieces[0]) and len(pieces) > 1:  # leading punctuation
                pieces[1] = pieces[0] + pieces[1]
                pieces = pieces[1:]
            pieces[0] = pieces[0][:1].upper() + pieces[0][1:] if word == line.split()[0] else pieces[0]
        elif language == 'Spanish':
            pieces = syllables_es(word)
        else:
            pieces = syllables_en(word)
        pieces[-1] += ' '
        out += pieces
    if out:
        out[-1] = out[-1].rstrip()
    return out


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def _voice_threshold(energy):
    return 0.12 * float(np.percentile(energy, 95)) if len(energy) else 0.0


def _smooth_pitch(pitch):
    """Median of 5 frames, and octave jumps of the pitch tracker folded back."""
    out = pitch.copy()
    for i in range(len(pitch)):
        window = pitch[max(0, i - 2):i + 3]
        window = window[~np.isnan(window)]
        if len(window):
            out[i] = np.median(window)
    return out


def segment_notes(energy, pitch, a, b, threshold):
    """[(first frame, end frame, midi)] of the voice between frames a and b."""
    notes, start, values, silence, jump = [], None, [], 0, 0

    def close(end):
        heard = [v for v in values if not np.isnan(v)]
        if start is not None and end - start >= MIN_NOTE_FRAMES and heard:
            notes.append((start, end, float(np.median(heard))))

    for i in range(max(a, 0), min(b, len(energy))):
        voiced = energy[i] > threshold and not np.isnan(pitch[i])
        if not voiced:
            silence += 1
            if silence == GAP_FRAMES:
                close(i - GAP_FRAMES + 1)
                start, values = None, []
            continue
        silence = 0
        if start is None:
            start, values, jump = i, [pitch[i]], 0
            continue
        if values and abs(pitch[i] - np.median(values)) > JUMP_SEMITONES:
            jump += 1
            if jump >= 3:
                close(i - 2)
                start, values, jump = i - 2, [v for v in pitch[i - 2:i + 1] if not np.isnan(v)], 0
            continue
        jump = 0
        values.append(pitch[i])
    close(min(b, len(energy)))
    return notes


def _attack(energy, frame):
    before = energy[max(0, frame - 3):frame]
    after = energy[frame:frame + 3]
    return float(after.mean() - (before.mean() if len(before) else 0.0)) if len(after) else 0.0


def assign_syllables(notes, syllables, energy):
    """[(first frame, end frame, midi, text)]: one syllable per note start, '~' for the held rest."""
    notes = list(notes)
    count = len(syllables)
    while len(notes) < count:  # fewer notes than syllables: split the longest
        k = max(range(len(notes)), key=lambda i: notes[i][1] - notes[i][0])
        a, b, m = notes[k]
        if b - a < 2:
            break
        mid = (a + b) // 2
        notes[k:k + 1] = [(a, mid, m), (mid, b, m)]
    if len(notes) < count:  # still short: the rest share the last note
        syllables = syllables[:len(notes) - 1] + [''.join(syllables[len(notes) - 1:])]
        count = len(syllables)
    # choose which notes start a syllable (the first always): dynamic programming on the attack strength
    n = len(notes)
    strength = [_attack(energy, a) + 0.02 * min(10, a - notes[i - 1][1] if i else 10) for i, (a, b, m) in enumerate(notes)]
    best = {(0, 0): (0.0, None)}
    for j in range(1, count):
        for i in range(j, n - (count - 1 - j)):
            options = [(best[(k, j - 1)][0] + strength[i], k) for k in range(j - 1, i) if (k, j - 1) in best]
            if options:
                best[(i, j)] = max(options)
    starts, i = [], max((k for k in range(n) if (k, count - 1) in best), key=lambda k: best[(k, count - 1)][0])
    for j in range(count - 1, -1, -1):
        starts.append(i)
        i = best[(i, j)][1]
    starts = starts[::-1]
    out, syllable = [], -1
    for k, (a, b, m) in enumerate(notes):
        if syllable + 1 < count and k == starts[syllable + 1]:
            syllable += 1
            text = syllables[syllable]
        else:
            text = '~'
        out.append((a, b, m, text))
    return out


def fold_octaves(notes, center):
    """Pitch tracker octave errors: every note to the octave nearest the line's median."""
    out = []
    for a, b, m, text in notes:
        while m - center > 7:
            m -= 12
        while center - m > 7:
            m += 12
        out.append((a, b, m, text))
    return out


def make_notes(lines, offset, energy, pitch, language):
    """[[(start s, end s, midi, syllable)] per line]."""
    threshold = _voice_threshold(energy)
    pitch = _smooth_pitch(pitch)
    heard = pitch[(energy > threshold) & ~np.isnan(pitch)]
    song_median = float(np.median(heard)) if len(heard) else 60.0
    result = []
    for index, (t, text) in enumerate(lines):
        syllables = line_syllables(text, language)
        if not syllables:
            continue
        start = t + offset - 0.25
        end = min((lines[index + 1][0] + offset - 0.05) if index + 1 < len(lines) else start + LINE_MAX_S,
                  start + LINE_MAX_S)
        a, b = int(start / FRAME), int(end / FRAME)
        notes = segment_notes(energy, pitch, a, b, threshold)
        if not notes:  # no voice found: even notes on the line, at the song's usual pitch
            step = max(MIN_NOTE_FRAMES, (b - a) // (len(syllables) + 1))
            notes = [(a + k * step, a + (k + 1) * step - 1, song_median) for k in range(len(syllables))]
        notes = assign_syllables(notes, syllables, energy)
        line_center = float(np.median([m for *_, m, _ in notes]))
        notes = fold_octaves(notes, line_center)
        result.append([(a * FRAME, b * FRAME, m, s) for a, b, m, s in notes])
    return result


# ---------------------------------------------------------------------------
# UltraStar txt
# ---------------------------------------------------------------------------

def ultrastar_text(lines_notes, tags):
    """The txt: notes in beats of BPM, a page break between lines; #GAP is the first note."""
    first = lines_notes[0][0][0]
    gap_ms = int(round(first * 1000))
    rows = [f"#{k}:{v}" for k, v in tags.items() if v not in (None, '')]
    rows += [f"#BPM:{BPM}", f"#GAP:{gap_ms}"]
    last_end = 0
    for index, notes in enumerate(lines_notes):
        if index:
            beat = max(last_end, int(round((notes[0][0] - first) / BEAT_S)) - 1)
            rows.append(f"- {beat}")
        for start, end, midi, text in notes:
            beat = max(last_end, int(round((start - first) / BEAT_S)))
            length = max(1, int(round((end - first) / BEAT_S)) - beat)
            rows.append(f": {beat} {length} {int(round(midi)) - 60} {text}")
            last_end = beat + length
    rows.append('E')
    return '\n'.join(rows) + '\n'


# ---------------------------------------------------------------------------
# The whole song
# ---------------------------------------------------------------------------

def safe_folder(text):
    return re.sub(r'[<>:"/\\|?*]', '', text).strip().rstrip('.')


def download_video(url, folder, base, yt_dlp):
    """<base>.mp4 (720p at most, with sound) and <base>.m4a (its sound) and <base> [CO].jpg (thumbnail)."""
    video = folder / f"{base}.mp4"
    if not video.exists():
        subprocess.run([*yt_dlp, '-q', '--no-playlist', '-f', 'bv*[height<=720]+ba/b[height<=720]/b',
                        '--merge-output-format', 'mp4', '--write-thumbnail', '--convert-thumbnails', 'jpg',
                        '-o', str(folder / f"{base}.%(ext)s"), url], check=True)
    audio = folder / f"{base}.m4a"
    if not audio.exists():
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-vn', '-c:a', 'aac', '-b:a', '192k',
                        str(audio)], check=True)
    thumb = folder / f"{base}.jpg"
    cover = folder / f"{base} [CO].jpg"
    if thumb.exists() and not cover.exists():
        thumb.rename(cover)
    return video, audio, cover if cover.exists() else None


def download_audio(url, folder, base, yt_dlp):
    """<base>.m4a from an audio upload (the album version of the song)."""
    audio = folder / f"{base}.m4a"
    if not audio.exists():
        subprocess.run([*yt_dlp, '-q', '--no-playlist', '-f', 'ba[ext=m4a]/ba', '-x', '--audio-format', 'm4a',
                        '-o', str(folder / f"{base}.%(ext)s"), url], check=True)
    return audio


PIECE_S = 8.0          # the official audio is looked for in the video in pieces this long


def video_pieces(song_env, clip_env, start_lag=None, rate=100):
    """[(song start s, song end s, video start s)]: where every PIECE_S of the song is in the video.

    Scenes added to a music video only push the rest of the song later, so the offset never goes back; a piece keeps
    the offset of the one before while it still fits there reasonably (a repeated chorus elsewhere does not move it).
    start_lag: offset of the whole song in the video (align_video.measure) to begin with."""
    from align_video import correlations
    size = int(PIECE_S * rate)
    pieces, previous = [], (None if start_lag is None else int(round(start_lag * rate)))
    for start in range(0, len(song_env), size):
        piece = song_env[start:start + size]
        if len(piece) < rate:
            break
        corr = correlations(piece, clip_env)[:len(clip_env)]
        floor = 0 if previous is None else max(0, start + previous - rate // 2)
        allowed = corr[floor:]
        if not len(allowed):
            lag = previous or 0
        else:
            best = floor + int(np.argmax(allowed))
            lag = best - start
            if previous is not None:
                at = start + previous
                if 0 <= at < len(corr) and corr[at] >= 0.6 * corr[best]:
                    lag = previous
        pieces.append([start / rate, min(len(song_env), start + size) / rate, lag / rate])
        previous = lag
    merged = []
    for a, b, lag in pieces:  # pieces with (almost) the same offset are one cut
        if merged and abs(merged[-1][2] - lag) < 0.3:
            merged[-1][1] = b
        else:
            merged.append([a, b, lag])
    for k in range(1, len(merged)):  # the exact second of each jump, in steps of 0.5 s
        merged[k - 1][1] = merged[k][0] = _jump_time(song_env, clip_env, merged[k][0], merged[k - 1][2],
                                                     merged[k][2], rate)
    return [(a, b, a + lag) for a, b, lag in merged if b - a > 0.01]


def _jump_time(song_env, clip_env, around, lag1, lag2, rate, window=2.0):
    """Song second, within PIECE_S of `around`, from which offset lag2 fits the video better than lag1."""
    def fit(t, lag):
        a, b = int(t * rate), int((t + window) * rate)
        v = int((t + lag) * rate)
        if a < 0 or v < 0 or v + (b - a) > len(clip_env) or b > len(song_env):
            return -np.inf
        return float(np.dot(song_env[a:b], clip_env[v:v + (b - a)]))
    for t in np.arange(around - PIECE_S, around + PIECE_S, 0.5):
        if t > 0 and fit(t, lag2) > fit(t, lag1):
            return float(t)
    return around


def cut_video_to_audio(audio, clip, target):
    """target: the video of `clip` rebuilt to follow `audio` (scenes that break the song are left out). Returns the
    cuts [(song start, song end, video start)]."""
    from align_video import envelope, measure
    start_lag, _, _ = measure(audio, clip)
    cuts = video_pieces(envelope(audio), envelope(clip), start_lag)
    clip_length = duration_of(clip)
    parts, labels = [], []
    for k, (a, b, v) in enumerate(cuts):
        v = min(max(0.0, v), max(0.0, clip_length - 0.1))
        end = min(clip_length, v + (b - a))
        pad = max(0.0, (b - a) - (end - v))  # the video ends first: its last frame stays
        parts.append(f"[0:v]trim=start={v:.3f}:end={end:.3f},setpts=PTS-STARTPTS"
                     + (f",tpad=stop_duration={pad:.3f}:stop_mode=clone" if pad > 0.01 else '') + f"[v{k}]")
        labels.append(f"[v{k}]")
    graph = ';'.join(parts) + ';' + ''.join(labels) + f"concat=n={len(labels)}:v=1:a=0,fps=25[out]"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(clip), '-filter_complex', graph, '-map', '[out]',
                    '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p', str(target)],
                   check=True)
    return cuts


def duration_of(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def make_song(artist, title, url, songs_dir, language='Spanish', year=None, genre=None, yt_dlp=None, log=print,
              audio_url=None):
    """Makes "<songs_dir>/<artist> - <title>/" and returns the path of its txt. audio_url: take the audio from
    that upload and cut the video of `url` to it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools'))
    if yt_dlp is None:
        from align_video import yt_dlp_command
        yt_dlp = yt_dlp_command()
    base = safe_folder(f"{artist} - {title}")
    folder = Path(songs_dir) / base
    folder.mkdir(parents=True, exist_ok=True)
    log(f"1/4 Downloading {url}" + (f" (official audio: {audio_url})" if audio_url else ''))
    intro, song_length = 0.0, None
    if audio_url:
        work = folder.parent / '_songmaker_downloads' / base
        work.mkdir(parents=True, exist_ok=True)
        official = download_audio(audio_url, work, base, yt_dlp)
        clip, _, cover = download_video(url, work, base, yt_dlp)
        from align_video import measure
        offset, fits, sure = measure(official, clip)
        whole = min(fits) >= 0.8 and sure >= 0.2 and offset >= 0
        log(f"    the song starts at {offset:+.1f} s of the video; fit of each quarter "
            f"{', '.join(f'{f:.0%}' for f in fits)} -> " + ("kept uncut" if whole else "cut to the official audio"))
        if cover and not (folder / cover.name).exists():
            cover = Path(cover).replace(folder / cover.name)
        if whole:
            video = Path(clip).replace(folder / clip.name)
            audio = folder / f"{base}.m4a"
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-vn', '-c:a', 'aac', '-b:a', '192k',
                            str(audio)], check=True)
            intro, song_length = offset, duration_of(official)
        else:
            audio = Path(official).replace(folder / official.name)
            video = folder / f"{base}.mp4"
            cuts = cut_video_to_audio(audio, clip, video)
            log(f"    video rebuilt from {len(cuts)} piece(s): " + ', '.join(
                f"song {a:.0f}-{b:.0f} s = video {v:.0f} s" for a, b, v in cuts))
    else:
        video, audio, cover = download_video(url, folder, base, yt_dlp)
    duration = duration_of(audio)

    log("2/4 Isolating the voice (Demucs, a few minutes)")
    cache = SyncModel.voice_cache_path(str(folder))
    voice = SyncModel.load_voice(cache, str(audio))
    if voice is None:
        SyncModel.analyze_voice(str(audio), cache)
        voice = SyncModel.load_voice(cache, str(audio))
    energy, pitch = voice['energy'], voice['pitch']

    log("3/4 Timed lyrics (LRCLIB)")
    versions = lrclib_versions(artist, title)
    if not versions:
        raise RuntimeError(f"LRCLIB has no timed lyrics for {artist} - {title}")
    version, offset, score = fit_lyrics(versions, energy, song_length or duration, intro)
    if version is None:
        raise RuntimeError("no LRCLIB version fits this audio")
    log(f"    LRCLIB #{version[0]} ({version[1]} s), offset {offset:+.2f} s, fit {score:.2f}, {len(version[2])} lines")

    log("4/4 Notes")
    lines_notes = [notes for notes in make_notes(version[2], offset, energy, pitch, language) if notes]
    tags = {'TITLE': title, 'ARTIST': artist, 'LANGUAGE': language, 'YEAR': year, 'GENRE': genre,
            'MP3': audio.name, 'AUDIO': audio.name, 'VIDEO': video.name if video else None,
            'COVER': cover.name if cover else None,
            'CREATOR': 'SongMaker (automatic, check it in the sync editor)', 'VERSION': '1.0.0'}
    txt = folder / f"{base}.txt"
    txt.write_text(ultrastar_text(lines_notes, tags), encoding='utf-8')
    (folder / 'songmaker.json').write_text(json.dumps({
        'url': url, 'lrclib_id': version[0], 'offset': offset, 'fit': round(score, 3),
        'notes': sum(len(n) for n in lines_notes), 'lines': len(lines_notes)}, indent=1), encoding='utf-8')
    log(f"Done: {txt} ({sum(len(n) for n in lines_notes)} notes in {len(lines_notes)} lines)")
    return txt
