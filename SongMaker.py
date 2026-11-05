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
    4. notes written the way the official songs are (measured on 387 of them, tools/note_style.py): the syllables
       of every line go where the voice attacks (dynamic programming over the line), each one a single steady note
       until the next (two only when a long syllable clearly moves), whole semitones in the song's key, wobbles and
       pitch-tracker slips levelled, octaves kept together, and rapped lines written as rap (no pitch);
    5. the result is a plain UltraStar folder ("Artist - Title/" with .txt, .m4a, .mp4 and cover) that the converter
       and the sync editor use like any other song.

Korean lyrics are romanized (Revised Romanization, one syllable per Hangul block) as Let's Sing shows them, and
Japanese lyrics too (Hepburn romaji with pykakasi, one syllable per mora).
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


def wait_for_network(log=print, host='www.youtube.com', every=30, give_up=3 * 3600):
    """Waits until `host` resolves again (internet back), checking every `every` seconds."""
    import socket
    import time
    waited = 0
    while True:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            if waited >= give_up:
                return False
            if waited == 0:
                log(f"    no internet: waiting for it to come back (checking every {every} s)")
            time.sleep(every)
            waited += every


def with_retries(step, log=print, tries=5):
    """Runs a step that needs internet; when it fails, waits for the connection and tries again."""
    for attempt in range(1, tries + 1):
        try:
            return step()
        except Exception as e:  # yt-dlp (CalledProcessError), requests, DNS...
            if attempt == tries:
                raise
            log(f"    attempt {attempt} failed ({str(e)[:120]}); retrying")
            wait_for_network(log)


def lrclib_versions(artist, title, folder=None):
    """[(id, duration, [(seconds, line)])] of the timed lyrics LRCLIB has for the song (kept in
    <folder>/lrclib.json, so a song is made again without internet)."""
    import requests
    cache = Path(folder) / 'lrclib.json' if folder else None
    if cache and cache.exists():
        hits = json.loads(cache.read_text(encoding='utf-8'))
    else:
        main_artist = re.split(r'\s+(?:feat\.?|ft\.?|&|x|×|,)\s+|,\s*', artist, flags=re.IGNORECASE)[0]
        hits = []
        # the artist as given, then the main artist ("LISA feat. Doja Cat & RAYE" -> "LISA"), then a free search
        for params in ({'artist_name': artist, 'track_name': title}, {'artist_name': main_artist, 'track_name': title},
                       {'q': f"{main_artist} {title}"}):
            response = requests.get(LRCLIB, params=params, timeout=20, headers={'User-Agent': USER_AGENT})
            response.raise_for_status()
            hits = [h for h in response.json() if h.get('syncedLyrics')]
            if hits:
                break
        if cache:
            cache.write_text(json.dumps(hits, ensure_ascii=False), encoding='utf-8')
    out = []
    for hit in hits:
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


_KAKASI = None


def is_japanese(text):
    return bool(re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', text))


def romaji_words(text):
    """[(word, is romaji)] of a Japanese line (Hepburn, pykakasi). A small っ doubles the next consonant and joins
    the next piece to its word ("踊って" -> "odotte")."""
    global _KAKASI
    if _KAKASI is None:
        import pykakasi
        _KAKASI = pykakasi.kakasi()
    words, double = [], False
    for item in _KAKASI.convert(text):
        orig, roman = item['orig'], item['hepburn']
        if not is_japanese(orig):
            words += [(w, False) for w in orig.split()]
            double = False
            continue
        pieces = roman.split()
        if not pieces:
            continue
        if double and pieces[0][:1].isalpha() and pieces[0][:1] not in 'aeiou':
            pieces[0] = pieces[0][:1] + pieces[0]
        if double and words and words[-1][1]:
            words[-1] = (words[-1][0] + pieces[0], True)
            pieces = pieces[1:]
        double = orig.endswith(('っ', 'ッ'))
        if double and pieces and pieces[-1].endswith('tsu'):
            pieces[-1] = pieces[-1][:-3]
        words += [(w, True) for w in pieces]
    return [(w, j) for w, j in words if w]


def syllables_romaji(word):
    """Morae of a romaji word: "kokoro" -> ko ko ro, "shinjite" -> shi n ji te, "kitto" -> ki tto."""
    pieces = re.findall(r"n(?![aeiouyAEIOUY])|[^aeiouAEIOU]*?[aeiouAEIOU]|[^aeiouAEIOU]+$", word)
    return [p for p in pieces if p] or [word]


def line_syllables(line, language):
    """[syllable text] of a lyrics line; the last syllable of every word ends with a space (UltraStar style)."""
    out = []
    if is_japanese(line):
        for word, japanese in romaji_words(line):
            pieces = syllables_romaji(word) if japanese else syllables_en(word)
            pieces[-1] += ' '
            out += pieces
        if out:
            out[0] = out[0][:1].upper() + out[0][1:]
            out[-1] = out[-1].rstrip()
        return out
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


# How the official Let's Sing songs are written (tools/note_style.py over 387 of them): about one note per syllable
# (1.07), notes of 0.24 s typically and almost never under 0.12 s, the pitch held steady (a third of the neighbouring
# notes repeat it, two fifths move 1-2 semitones, under a tenth jump 5 or more) and rap written as pitchless notes.
# make_notes writes like that: the syllables go where the voice attacks, each one is a single steady note until
# the next, and only a long syllable whose pitch clearly moves gets a second note.
NOTE_MAKER_VERSION = 2          # 1: notes cut from the voice (2026-11-04); 2: written like the official songs
MIN_SYLLABLE_FRAMES = 3         # 60 ms
SYLLABLE_S = (0.12, 0.35)       # expected length of a syllable (the line's voice shared out, kept in this range)
ONSET_DURATION_WEIGHT = 4.0     # how much a syllable far from its expected length costs, against attack strength
MIN_NOTE_S = 0.12               # shorter notes are made this long when the next one leaves room
NOTE_GAP_FRAMES = 2             # a silence this long (40 ms) ends a note before the next syllable
MELISMA_MIN_S = 0.45            # a syllable this long may hold two notes...
MELISMA_SEMITONES = 2.0         # ...when its pitch moves this much and stays
FIRST_SYLLABLE_SLACK_S = 0.6    # the line's time from LRCLIB is approximate


def _novelty(energy, pitch):
    """How much a syllable seems to start at every frame: the loudness rising after a dip, the pitch changing, the
    voice starting after a silence."""
    loud = np.log(np.maximum(energy, 1e-5))
    smooth = np.convolve(loud, np.ones(3) / 3, mode='same')
    n = len(smooth)
    dip = np.array([smooth[max(0, i - 4):i + 1].min() for i in range(n)])
    ahead = np.concatenate([smooth[2:], [smooth[-1]] * 2]) if n > 2 else smooth
    rise = np.clip(ahead - dip, 0, 3)
    change = np.zeros(n)
    for i in range(4, n - 4):
        before, after = pitch[i - 4:i], pitch[i:i + 4]
        before, after = before[~np.isnan(before)], after[~np.isnan(after)]
        if len(before) >= 2 and len(after) >= 2:
            change[i] = min(4.0, abs(float(np.median(after) - np.median(before)))) / 4
    return rise + change


def _line_onsets(novelty, voiced, a, b, weights, first_time):
    """Start frame of each syllable (len(weights) of them) between frames a and b: dynamic programming that takes
    strong onsets and gives each syllable voice in proportion to its length (weights)."""
    count = len(weights)
    span = np.flatnonzero(voiced[a:b]) + a
    if len(span) < count * MIN_SYLLABLE_FRAMES:
        return None
    region_start = [i for i in span if i == a or not voiced[i - 1]]
    peaks = [i for i in span if (i == a or novelty[i] >= novelty[i - 1]) and (i + 1 >= b or novelty[i] >= novelty[i + 1])]
    candidates = sorted(set(region_start) | set(peaks))
    if len(candidates) < count:
        candidates = list(span)
    cand = np.array(candidates)
    voiced_before = np.cumsum(np.concatenate([[0], voiced[a:b].astype(int)]))  # voiced frames in a..i

    def voiced_between(i, j):
        return voiced_before[j - a] - voiced_before[i - a]

    # a syllable is expected to last about as long as the line's voice shared out, but within what is sung
    # (official syllables: 0.24 s typically); the last one holds what is left, a long final note is common
    mean_weight = sum(weights) / count
    each = min(max(len(span) / count, SYLLABLE_S[0] / FRAME), SYLLABLE_S[1] / FRAME)
    expected = [each * w / mean_weight for w in weights]
    bonus = novelty[cand] + np.isin(cand, region_start) * 0.5
    first_cost = 0.6 * np.maximum(0, np.abs((cand - first_time) * FRAME) - 0.15) / FIRST_SYLLABLE_SLACK_S
    m = len(cand)
    score = np.full((count, m), -np.inf)
    back = np.zeros((count, m), dtype=int)
    score[0] = bonus - first_cost
    for j in range(1, count):
        for k in range(j, m - (count - 1 - j)):
            best, arg = -np.inf, -1
            for q in range(k - 1, j - 2, -1):
                if score[j - 1, q] == -np.inf:
                    continue
                held = voiced_between(cand[q], cand[k])
                if held < MIN_SYLLABLE_FRAMES:
                    continue
                if (cand[k] - cand[q]) * FRAME > 4.0:
                    break
                ratio = np.log((held + 1) / (expected[j - 1] + 1))
                value = score[j - 1, q] - ONSET_DURATION_WEIGHT * ratio * ratio
                if value > best:
                    best, arg = value, q
            if arg >= 0:
                score[j, k] = best + bonus[k]
                back[j, k] = arg
    last = score[count - 1]
    if not np.isfinite(last).any():
        return None
    # the last syllable holds the rest of its voice: a gentle cost if that is far longer than expected
    tail = np.array([voiced_between(c, b) for c in cand])
    last = last - 0.3 * np.maximum(0, np.log((tail + 1) / (expected[-1] + 1)))
    k = int(np.argmax(last))
    out = []
    for j in range(count - 1, -1, -1):
        out.append(int(cand[k]))
        k = back[j, k]
    return out[::-1]


def _note_end(voiced, start, limit):
    """The end frame of a note starting at `start`: at the next syllable (limit) or where the voice stops."""
    silence = 0
    for i in range(start, limit):
        silence = silence + 1 if not voiced[i] else 0
        if silence >= NOTE_GAP_FRAMES:
            return i - silence + 1
    return limit


def _steady_pitch(pitch, a, b):
    """(midi of the steady part of the note, frames with pitch / frames, spread in semitones)."""
    length = b - a
    core = pitch[a + length // 4:b - length // 10] if length >= 5 else pitch[a:b]
    heard = core[~np.isnan(core)]
    if len(heard) < 2:
        heard = pitch[a:b][~np.isnan(pitch[a:b])]
    if not len(heard):
        return None, 0.0, 0.0
    m = float(np.median(heard))
    if len(heard) >= 4:  # the semitone heard the longest, not the median of a slide
        rounded = np.round(heard)
        values, counts = np.unique(rounded, return_counts=True)
        m = float(np.median(heard[np.abs(heard - values[np.argmax(counts)]) <= 0.5]))
    return m, len(heard) / max(1, len(core)), float(np.percentile(np.abs(heard - m), 75))


def _melisma(pitch, a, b):
    """[(a, b)] pieces of a long syllable whose pitch moves (two or three steady notes), or [(a, b)]."""
    if (b - a) * FRAME < MELISMA_MIN_S:
        return [(a, b)]
    least = int(0.15 / FRAME)
    best, where = 0.0, None
    for k in range(a + least, b - least):
        left, right = pitch[a:k], pitch[k:b]
        left, right = left[~np.isnan(left)], right[~np.isnan(right)]
        if len(left) < least // 2 or len(right) < least // 2:
            continue
        ml, mr = np.median(left), np.median(right)
        if np.percentile(np.abs(left - ml), 75) > 0.8 or np.percentile(np.abs(right - mr), 75) > 0.8:
            continue
        if abs(mr - ml) > best:
            best, where = abs(mr - ml), k
    if where is None or best < MELISMA_SEMITONES:
        return [(a, b)]
    return _melisma(pitch, a, where) + _melisma(pitch, where, b)


_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])


def song_scale(midis, durations):
    """The 7 pitch classes of the song's key (Krumhansl), from its notes weighted by length."""
    hist = np.zeros(12)
    for m, d in zip(midis, durations):
        hist[int(round(m)) % 12] += d
    best = max(range(12), key=lambda k: np.corrcoef(hist, np.roll(_MAJOR, k))[0, 1])
    return {(best + step) % 12 for step in (0, 2, 4, 5, 7, 9, 11)}


def level_pitches(midis, durations, scale):
    """Whole semitones the way the official songs write them: a pitch between two semitones goes to the one in the
    key; a short note one semitone away from two equal neighbours takes theirs (a wobble, not a melody), and so does
    a short note 5 or more away from two close neighbours (the pitch tracker failing)."""
    out = []
    for m in midis:
        if m is None:
            out.append(None)
            continue
        r = int(round(m))
        if r % 12 not in scale:
            other = r + 1 if m > r else r - 1
            if other % 12 in scale and abs(m - other) < 0.75:
                r = other
        out.append(r)
    for i in range(1, len(out) - 1):
        a, x, c = out[i - 1], out[i], out[i + 1]
        if None in (a, x, c) or durations[i] >= 0.3:
            continue
        if a == c and abs(x - a) == 1:
            out[i] = a
        elif abs(x - a) >= 5 and abs(x - c) >= 5 and abs(a - c) <= 3:  # a short note far from both: a tracker error
            out[i] = a if abs(x - a) < abs(x - c) else c
    return out


# Rap: measured on the official rap lines (tools/note_calibrate.py) the raw pitch inside a rapped syllable slides
# (25 semitones a second against 7 when sung), less of the voice has a pitch (61 % against 80 %), more of the notes
# wobble over a semitone (73 % against 33 %) and the syllables go faster. The score adds those, is smoothed with the
# neighbouring lines (rap comes in verses) and a line is rap above RAP_SCORE when a neighbour is too.
RAP_SCORE = 3.0


def rap_features(pitch, notes, rate):
    """(median slide of the pitch inside the notes in semitones/s, share of frames with pitch, share of notes that
    wobble over a semitone, syllables a second) of a line; pitch is the raw track, notes are (first, end frame)."""
    slides, shares, wobbly = [], [], []
    for a, b in notes:
        q = pitch[a:b]
        ok = ~np.isnan(q)
        shares.append(float(ok.mean()) if len(q) else 0.0)
        if ok.sum() >= 3:
            y = q[ok]
            slides.append(abs(float(np.polyfit(np.flatnonzero(ok) * FRAME, y, 1)[0])))
            wobbly.append(float(np.percentile(np.abs(y - np.median(y)), 75)) > 1)
    return (float(np.median(slides)) if slides else 30.0, float(np.mean(shares)) if shares else 0.0,
            float(np.mean(wobbly)) if wobbly else 1.0, rate)


def rap_lines(features):
    """[True for the rapped lines] from rap_features of every line."""
    if not features:
        return []
    score = np.array([np.log(max(slide, 0.5)) - 3 * share + 0.3 * rate + wobble
                      for slide, share, wobble, rate in features])
    padded = np.concatenate([[score[0]], score, [score[-1]]])
    smooth = 0.25 * padded[:-2] + 0.5 * padded[1:-1] + 0.25 * padded[2:]
    over = smooth > RAP_SCORE
    return [bool(over[i] and ((i > 0 and over[i - 1]) or (i + 1 < len(over) and over[i + 1])))
            for i in range(len(over))]


def smooth_octaves(midis, center):
    """Octave of every note (the pitch tracker jumps octaves): the path closest to the neighbours and to the line."""
    if not midis:
        return []
    options = [[m + 12 * k for k in (-1, 0, 1)] for m in midis]
    cost = [abs(o - center) * 0.1 + (0 if k == 1 else 1.0) for k, o in enumerate(options[0])]
    back = []
    for i in range(1, len(midis)):
        new, arg = [], []
        for k, o in enumerate(options[i]):
            steps = [cost[q] + max(0.0, abs(o - options[i - 1][q]) - 2) for q in range(3)]
            q = int(np.argmin(steps))
            new.append(steps[q] + abs(o - center) * 0.1 + (0 if k == 1 else 1.0))
            arg.append(q)
        cost, back = new, back + [arg]
    k = int(np.argmin(cost))
    out = [options[-1][k]]
    for i in range(len(midis) - 1, 0, -1):
        k = back[i - 1][k]
        out.append(options[i - 1][k])
    return out[::-1]


def make_notes(lines, offset, energy, pitch, language):
    """[[(start s, end s, midi or None for rap, syllable)] per line]."""
    threshold = _voice_threshold(energy)
    smooth = _smooth_pitch(pitch)
    voiced = energy > threshold
    novelty = _novelty(energy, smooth)
    heard = smooth[voiced & ~np.isnan(smooth)]
    song_median = float(np.median(heard)) if len(heard) else 60.0
    result, features, rows = [], [], []  # rows: the lines with notes from the voice (rap is looked for in them)
    for index, (t, text) in enumerate(lines):
        syllables = line_syllables(text, language)
        if not syllables:
            continue
        start = t + offset - 0.25
        end = min((lines[index + 1][0] + offset - 0.05) if index + 1 < len(lines) else start + LINE_MAX_S,
                  start + LINE_MAX_S)
        a, b = max(0, int(start / FRAME)), min(len(energy), int(end / FRAME))
        weights = [1 + 0.2 * len(re.sub(r'\W', '', s)) for s in syllables]
        onsets = _line_onsets(novelty, voiced, a, b, weights, int((t + offset) / FRAME)) if b > a else None
        if onsets is None:  # no voice found: even notes on the line, at the song's usual pitch
            step = max(MIN_SYLLABLE_FRAMES + 1, (b - a) // (len(syllables) + 1))
            result.append([((a + k * step) * FRAME, (a + (k + 1) * step - 1) * FRAME, song_median, s)
                           for k, s in enumerate(syllables)])
            continue
        notes = []
        for k, (on, syllable) in enumerate(zip(onsets, syllables)):
            limit = onsets[k + 1] - 1 if k + 1 < len(onsets) else b
            stop = max(on + MIN_SYLLABLE_FRAMES, _note_end(voiced, on, max(limit, on + MIN_SYLLABLE_FRAMES)))
            for piece, (p, q) in enumerate(_melisma(smooth, on, stop)):
                midi, _, _ = _steady_pitch(smooth, p, q)
                notes.append([p, q, midi, syllable if piece == 0 else '~'])
        known = [n[2] for n in notes if n[2] is not None]
        center = float(np.median(known)) if known else song_median
        for n in notes:
            if n[2] is None:
                n[2] = center
            while n[2] - center > 7:
                n[2] -= 12
            while center - n[2] > 7:
                n[2] += 12
        for n, m in zip(notes, smooth_octaves([n[2] for n in notes], center)):
            n[2] = m
        span = (notes[-1][1] - notes[0][0]) * FRAME
        features.append(rap_features(pitch, [(p, q) for p, q, _, _ in notes], len(syllables) / max(0.2, span)))
        result.append([(p * FRAME, q * FRAME, m, s) for p, q, m, s in notes])
        rows.append(len(result) - 1)
    for i, rap in zip(rows, rap_lines(features)):
        if rap:
            result[i] = [(a, b, None, s) for a, b, m, s in result[i]]
    sung = [(n[2], n[1] - n[0]) for line in result for n in line if n[2] is not None]
    scale = song_scale(*zip(*sung)) if len(sung) >= 8 else set(range(12))
    song_center = float(np.median([m for m, _ in sung])) if sung else song_median
    out = []
    for line in result:
        levelled = level_pitches([n[2] for n in line], [n[1] - n[0] for n in line], scale)
        known = [m for m in levelled if m is not None]
        shift = 0
        if known:  # a whole line an octave away from the rest of the song: the tracker, not the singer
            center = float(np.median(known))
            while center + shift - song_center > 7:
                shift -= 12
            while song_center - (center + shift) > 7:
                shift += 12
        notes = []
        for k, ((a, b, _, s), m) in enumerate(zip(line, levelled)):
            if b - a < MIN_NOTE_S:  # official notes are hardly ever shorter
                b = max(b, min(a + MIN_NOTE_S, line[k + 1][0] - NOTE_GAP_FRAMES * FRAME if k + 1 < len(line)
                               else a + MIN_NOTE_S))
            notes.append((a, b, None if m is None else m + shift, s))
        out.append(notes)
    return out


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
            if midi is None:  # rap: no pitch (Let's Sing #p1)
                rows.append(f"R {beat} {length} 0 {text}")
            else:
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
        full = correlations(piece, clip_env)
        # position in the video of every correlation value: negative ones (the piece begins before the video
        # starts, as when the video begins after the song) wrap to the end of the array
        where = np.arange(len(full))
        where = np.where(where < len(clip_env), where, where - len(full))
        lags = where - start
        allowed = np.ones(len(full), dtype=bool) if previous is None else lags >= previous - rate // 2
        if not allowed.any():
            lag = previous or 0
        else:
            best = int(np.argmax(np.where(allowed, full, -np.inf)))
            lag = int(lags[best])
            if previous is not None:
                at = np.nonzero(lags == previous)[0]
                # the first piece only overlaps part of the video when it starts later: keep the global offset
                keep = 0.3 if not pieces else 0.6
                if len(at) and full[at[0]] >= keep * full[best]:
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


def cut_video_to_audio(audio, clip, target, cuts=None):
    """target: the video of `clip` rebuilt to follow `audio` (scenes that break the song are left out). Returns the
    cuts [(song start, song end, video start)]; `cuts` given: those, as they are."""
    from align_video import envelope, measure
    if cuts is None:
        start_lag, _, _ = measure(audio, clip)
        cuts = video_pieces(envelope(audio), envelope(clip), start_lag)
    clip_length = duration_of(clip)
    parts, labels = [], []
    for k, (a, b, v) in enumerate(cuts):
        before = max(0.0, -v)  # the video starts after the song: its first frame stays
        v = min(max(0.0, v), max(0.0, clip_length - 0.1))
        end = min(clip_length, v + (b - a) - before)
        after = max(0.0, (b - a) - before - (end - v))  # the video ends first: its last frame stays
        pads = [f"start_duration={before:.3f}:start_mode=clone"] if before > 0.01 else []
        pads += [f"stop_duration={after:.3f}:stop_mode=clone"] if after > 0.01 else []
        parts.append(f"[0:v]trim=start={v:.3f}:end={end:.3f},setpts=PTS-STARTPTS"
                     + (f",tpad={':'.join(pads)}" if pads else '') + f"[v{k}]")
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


def fetch_song(artist, title, url, songs_dir, audio_url=None, yt_dlp=None, log=print, lyrics_artist=None):
    """Everything that needs internet, kept in the song folder: the video, the official audio, the LRCLIB lyrics and
    the Genius pages (choruses and sections, used by the conversion). make_song then works without internet."""
    import SongSections
    import UltrastarToSingit
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools'))
    if yt_dlp is None:
        from align_video import yt_dlp_command
        yt_dlp = yt_dlp_command()
    base = safe_folder(f"{artist} - {title}")
    folder = Path(songs_dir) / base
    folder.mkdir(parents=True, exist_ok=True)
    if audio_url:
        work = folder.parent / '_songmaker_downloads' / base
        work.mkdir(parents=True, exist_ok=True)
        if not (folder / f"{base}.m4a").exists():
            with_retries(lambda: download_audio(audio_url, work, base, yt_dlp), log)
        if not (folder / f"{base}.mp4").exists():
            with_retries(lambda: download_video(url, work, base, yt_dlp), log)
    else:
        with_retries(lambda: download_video(url, folder, base, yt_dlp), log)
    lyrics_artist = lyrics_artist or artist
    with_retries(lambda: lrclib_versions(lyrics_artist, title, folder), log)
    txt = folder / f"{base}.txt"  # the Genius caches are named after the txt the song will have
    UltrastarToSingit._genius_offline = False
    with_retries(lambda: UltrastarToSingit.genius_get_choruses(txt, artist=lyrics_artist, title=title), log)
    with_retries(lambda: SongSections.get_sections(txt, lyrics_artist, title), log)
    (folder / 'songmaker_fetched.json').write_text(json.dumps({'url': url, 'audio_url': audio_url}), encoding='utf-8')
    log(f"Fetched: {base}")
    return folder


def make_song(artist, title, url, songs_dir, language='Spanish', year=None, genre=None, yt_dlp=None, log=print,
              audio_url=None, lyrics_artist=None):
    """Makes "<songs_dir>/<artist> - <title>/" and returns the path of its txt. audio_url: take the audio from
    that upload and cut the video of `url` to it. What fetch_song already downloaded is used as it is."""
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
        official = with_retries(lambda: download_audio(audio_url, work, base, yt_dlp), log)
        clip, _, cover = with_retries(lambda: download_video(url, work, base, yt_dlp), log)
        from align_video import measure
        offset, fits, sure = measure(official, clip)
        follows = min(fits) >= 0.8 and sure >= 0.2
        whole = follows and offset >= 0
        decision = 'kept uncut' if whole else 'shifted to the official audio' if follows else 'cut to the official audio'
        log(f"    the song starts at {offset:+.1f} s of the video; fit of each quarter "
            f"{', '.join(f'{f:.0%}' for f in fits)} -> {decision}")
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
            # the video follows the whole song but starts after it: one cut, its first frame held at the start
            cuts = cut_video_to_audio(audio, clip, video,
                                      [(0.0, duration_of(audio), offset)] if follows else None)
            log(f"    video rebuilt from {len(cuts)} piece(s): " + ', '.join(
                f"song {a:.0f}-{b:.0f} s = video {v:.0f} s" for a, b, v in cuts))
    else:
        video, audio, cover = with_retries(lambda: download_video(url, folder, base, yt_dlp), log)
    duration = duration_of(audio)

    log("2/4 Isolating the voice (Demucs, a few minutes)")
    cache = SyncModel.voice_cache_path(str(folder))
    voice = SyncModel.load_voice(cache, str(audio))
    if voice is None:
        SyncModel.analyze_voice(str(audio), cache)
        voice = SyncModel.load_voice(cache, str(audio))
    energy, pitch = voice['energy'], voice['pitch']

    log("3/4 Timed lyrics (LRCLIB)")
    versions = with_retries(lambda: lrclib_versions(lyrics_artist or artist, title, folder), log)
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
        'notes': sum(len(n) for n in lines_notes), 'lines': len(lines_notes),
        'note_maker': NOTE_MAKER_VERSION}, indent=1), encoding='utf-8')
    log(f"Done: {txt} ({sum(len(n) for n in lines_notes)} notes in {len(lines_notes)} lines)")
    return txt


def remake_notes(folder, keep_dir=None, log=print, force=False):
    """Writes the notes of a song made by SongMaker again with the current note maker, from what its folder already
    has (voice analysis, LRCLIB version and offset in songmaker.json): no video or Demucs work. The header tags of the
    txt are kept; the old txt is copied to keep_dir first. A song fixed by hand in the sync editor (it has a .bak of
    its txt) is left alone unless force. Returns the txt, or None when skipped."""
    import requests
    folder = Path(folder)
    meta = json.loads((folder / 'songmaker.json').read_text(encoding='utf-8'))
    if meta.get('note_maker', 1) >= NOTE_MAKER_VERSION and not force:
        log(f"{folder.name}: notes already made with version {NOTE_MAKER_VERSION}")
        return None
    txts = sorted(folder.glob('*.txt'))
    txt = folder / f"{folder.name}.txt" if (folder / f"{folder.name}.txt").exists() else (txts[0] if txts else None)
    if txt is None:
        raise RuntimeError(f"{folder.name}: no txt")
    if Path(str(txt) + '.bak').exists() and not force:
        log(f"{folder.name}: SKIPPED, fixed by hand in the sync editor ({txt.name}.bak exists)")
        return None
    old = txt.read_text(encoding='utf-8')
    tags = {}
    for row in old.splitlines():
        if row.startswith('#') and ':' in row:
            key, value = row[1:].split(':', 1)
            if key.upper() not in ('BPM', 'GAP'):
                tags[key] = value
    cache = folder / 'lrclib.json'
    if not cache.exists():  # songs made before the cache: the chosen version by its id
        response = requests.get(f"https://lrclib.net/api/get/{meta['lrclib_id']}", timeout=20,
                                headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        cache.write_text(json.dumps([response.json()], ensure_ascii=False), encoding='utf-8')
    versions = {v[0]: v for v in lrclib_versions(None, None, folder)}
    if meta['lrclib_id'] not in versions:
        raise RuntimeError(f"{folder.name}: LRCLIB version {meta['lrclib_id']} is not in lrclib.json")
    voice = np.load(SyncModel.voice_cache_path(str(folder)))
    energy, pitch = voice['energy'].astype(np.float32), voice['pitch'].astype(np.float32)
    language = tags.get('LANGUAGE', 'Spanish').strip()
    lines_notes = [n for n in make_notes(versions[meta['lrclib_id']][2], meta['offset'], energy, pitch, language) if n]
    if keep_dir:
        keep = Path(keep_dir) / folder.name
        keep.mkdir(parents=True, exist_ok=True)
        (keep / txt.name).write_text(old, encoding='utf-8')
    txt.write_text(ultrastar_text(lines_notes, tags), encoding='utf-8')
    meta.update({'notes': sum(len(n) for n in lines_notes), 'lines': len(lines_notes),
                 'note_maker': NOTE_MAKER_VERSION})
    (folder / 'songmaker.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    rap = sum(1 for line in lines_notes if line and line[0][2] is None)
    log(f"{folder.name}: {meta['notes']} notes in {meta['lines']} lines" + (f", {rap} rapped" if rap else ''))
    return txt
