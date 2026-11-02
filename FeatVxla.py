"""Files of the Feat mode of Let's Sing 2026: Songs/vxla_feat/<id>_feat.vxla and Songs/beats/<id>.json.

The game loads them as Singable.AssetType.VxlaFeat and .Beat. Without the feat vxla the game closes when a song is
started in Feat mode. What the 15 official songs of DLC 3 show:
  - the feat vxla is the normal one without golden notes (#g5), without 'practice'/'passages', plus a second voice
    (notes2_full, lyrics2, pages2). That voice is written by hand (harmonies, backing vocals) and is empty in 5 of
    the 15 songs; those 5 have "coopfriendly": "" in songs_xx.json, the other 10 "Coop";
  - 'segments' (FeatSegment: who sings each part) covers the whole song without gaps and every boundary is the
    start of a page: 'feat' = chorus (median 30 s, 4-18 pages), '' = part of a verse (median 13 s, 2-10 pages),
    '1'/'2' = a part forced on one voice (rare, not generated here). In Feat the singers sing the 'feat' parts
    together (each line in their colour) and take turns in the others;
  - beats/<id>.json: beat times, bpm and three spectrum bands, used only by effects that follow the music
    (BeatLinker). A song without it is marked SongBeats.Invalid and plays normally.
"""
import bisect
import json
import re
import subprocess
from xml.sax.saxutils import escape

import numpy as np

import OfficialVxla

CHORUS = 'feat'
VERSE = ''
VERSE_TARGET_S = 13.0      # verse parts of the official files: median 13 s
VERSE_MIN_S = 8.0          # shortest verse part (official: 7.2; 8 s gave the closest cuts on the 15 official songs)
VERSE_MAX_S = 22.0         # longer verse parts are cut at their longest pause (official: 3/4 under 18 s)
MIN_PAGES = 2
SNAP_S = 0.5               # a chorus that starts or ends this close to a page start begins/ends there

LAYER_ORDER = ('segments', 'pages', 'lyrics', 'notes_full', 'notes2_full', 'lyrics2', 'pages2', 'language')


def build_segments(page_starts, choruses, song_end, gap_before=None, sections=()):
    """[(t1, t2, value)] covering 0..song_end: choruses as 'feat', the rest cut into verse parts at page starts.

    A verse region is cut first where a section of the song changes (`sections`: start times of the official
    'structure' layer of DLC songs), then a part longer than VERSE_MAX_S is cut at its longest pause
    (`gap_before`: {page start: seconds of silence before it}); official cuts come after a median pause of 0.9 s,
    other lines after 0.3 s."""
    starts = sorted(set(round(t, 3) for t in page_starts if 0 <= t < song_end))
    if not starts:
        return [(0.0, song_end, VERSE)]
    gap_before = {round(k, 3): v for k, v in (gap_before or {}).items()}

    def pages_in(a, b):
        return sum(a - 1e-3 <= s < b - 1e-3 for s in starts)

    def snap(t):
        return min(starts, key=lambda s: abs(s - t))

    spans = []
    for a, b in sorted(choruses):
        begin = max((s for s in starts if s <= a + SNAP_S), default=starts[0])
        end = min((s for s in starts if s >= b - SNAP_S), default=song_end)
        if spans and begin < spans[-1][1] + VERSE_MIN_S:  # a gap too short to be a verse part: one chorus
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
        elif end > begin:
            spans.append((begin, end))
    spans = [(a, b) for a, b in spans if pages_in(a, b) >= MIN_PAGES]

    def can_cut(a, cut, b):
        return cut - a >= VERSE_MIN_S and b - cut >= VERSE_MIN_S and pages_in(a, cut) >= MIN_PAGES \
            and pages_in(cut, b) >= 1

    def split(a, b):
        """Cuts of a part longer than VERSE_MAX_S, at its longest pause (recursively)."""
        if b - a <= VERSE_MAX_S:
            return []
        options = [c for c in starts if a < c < b and can_cut(a, c, b)]
        if not options:
            return []
        # the longest pause; between equal pauses, the cut that leaves parts nearest VERSE_TARGET_S
        cut = max(options, key=lambda c: (round(gap_before.get(c, 0.0), 1),
                                          -abs(min(c - a, b - c) - VERSE_TARGET_S)))
        return split(a, cut) + [cut] + split(cut, b)

    segments = []

    def fill(a, b):
        if b - a < 1e-3:
            return
        cuts = sorted({snap(t) for t in sections if a + 1e-3 < snap(t) < b - 1e-3})
        kept, last = [], a
        for c in cuts:
            if can_cut(last, c, b):
                kept.append(c)
                last = c
        bounds = [a] + kept + [b]
        for x, y in zip(bounds, bounds[1:]):
            inner = [x] + split(x, y) + [y]
            segments.extend((u, v, VERSE) for u, v in zip(inner, inner[1:]))

    cursor = 0.0
    for a, b in spans:
        fill(cursor, a)
        segments.append((a, b, CHORUS))
        cursor = b
    fill(cursor, song_end)
    return segments


def pauses_before_pages(pages, notes):
    """{page start: seconds between the last note before the page and the first note of the page}."""
    ends = sorted(t2 for t1, t2, v in notes)
    starts_n = sorted(t1 for t1, t2, v in notes)
    out = {}
    for p0, p1, _ in pages:
        i = bisect.bisect_right(ends, p0 + 1e-3)
        j = bisect.bisect_left(starts_n, p0 - 1e-3)
        if i and j < len(starts_n):
            out[p0] = max(0.0, starts_n[j] - ends[i - 1])
    return out


def _layer(name, intervals):
    rows = [f'\t<IntervalLayer datatype="STRING" name="{name}">']
    for t1, t2, value in intervals:
        rows.append(f'\t\t<Interval t1="{t1:.3f}" t2="{t2:.3f}" value="{escape(value, {chr(34): "&quot;"})}" />')
    rows.append('\t</IntervalLayer>')
    return '\r\n'.join(rows)


CHORUS_KINDS = ('chorus', 'postchorus')   # Genius sections sung together in Feat (official 'feat' parts: ~30 s)
MERGE_CHORUS_GAP_S = 4.0                  # detected chorus fragments this close together are one chorus
MIN_MATCHED_PAGES = 0.5                   # share of pages matched with Genius lines to trust its sections
COOP_MIN_NOTES = 20                       # official GoodNews (6 notes in voice 2) is not "Coop", the rest are


def _merge(spans, gap):
    out = []
    for a, b in sorted(spans):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(b, out[-1][1]))
        else:
            out.append((a, b))
    return out


def repeated_lines(pages, texts, min_words=3, similarity=0.85):
    """Choruses when nothing else knows them: runs of at least MIN_PAGES lines whose text comes back later in the
    song (a chorus is the part that repeats)."""
    import difflib
    simple = [' '.join(re.sub(r'[^\w ]+', ' ', t.lower()).split()) for t in texts]
    repeated = [False] * len(simple)
    for i, a in enumerate(simple):
        if len(a.split()) < min_words:
            continue
        for j in range(len(simple)):
            if j != i and abs(j - i) > 1 and difflib.SequenceMatcher(None, a, simple[j]).ratio() >= similarity:
                repeated[i] = True
                break
    spans, run = [], []
    ends = [p[0] for p in pages[1:]] + [pages[-1][1]] if pages else []
    for k, rep in enumerate(repeated + [False]):
        if rep:
            run.append(k)
        else:
            if len(run) >= MIN_PAGES:
                spans.append((pages[run[0]][0], ends[run[-1]]))
            run = []
    return spans


def _page_texts(pages, lyrics):
    starts = [p[0] for p in pages]
    texts = [''] * len(pages)
    for t1, t2, v in lyrics:
        i = bisect.bisect_right(starts, t1 + 1e-3) - 1
        if 0 <= i < len(texts):
            texts[i] += v
    return texts


def _in_pages(intervals, spans):
    return [x for x in intervals if any(a - 1e-3 <= x[0] < b - 1e-3 for a, b in spans)]


def feat_layers(layers, song_duration, sections=(), genius=None, singers=None, voice2=None):
    """Layers of the feat vxla from the layers of the song's normal vxla.

    sections: start times of the song's official 'structure' sections (DLC songs).
    genius: SongSections.get_sections() of the song, singers: SongSections.song_singers(); with them the choruses
    and section changes come from the lyrics page and the lines of the second singer form the second voice.
    voice2: (notes, lyrics, pages) of the second singer of an UltraStar duet (P2), used as it is."""
    import SongSections
    notes = layers.get('notes_full', [])
    pages = layers.get('pages', [])
    lyrics = layers.get('lyrics', [])
    song_end = max([song_duration] + [t2 for t1, t2, v in pages + notes + layers.get('language', [])])
    page_starts = [t1 for t1, t2, v in pages]
    page_ends = page_starts[1:] + [song_end]
    segments = layers.get('segments', [])
    covers_all = segments and segments[0][0] < 1e-3 and abs(segments[-1][1] - song_end) < 0.05 \
        and all(abs(x[1] - y[0]) < 1e-3 for x, y in zip(segments, segments[1:]))
    v2_notes, v2_lyrics, v2_pages = voice2 or ([], [], [])
    if not covers_all:  # our vxla only marks the choruses
        choruses = _merge([(t1, t2) for t1, t2, v in segments if v == CHORUS], MERGE_CHORUS_GAP_S)
        cuts = list(sections)
        info = SongSections.align_pages(_page_texts(pages, lyrics), genius, *singers) if genius and singers else []
        if info and sum(x is not None for x in info) >= MIN_MATCHED_PAGES * len(info):
            # the official structure of a DLC song is better than the lyrics page, unless it marks less than two
            # choruses (One Kiss: one)
            if not sections or len(choruses) < 2:
                from_genius = [(a, b) for a, b, x in zip(page_starts, page_ends, info) if x and x[1] in CHORUS_KINDS]
                if from_genius:
                    choruses = _merge(from_genius, 0.05)
                last = None
                for start, x in zip(page_starts, info):
                    if x and x[0] != last:
                        cuts.append(start)
                        last = x[0]
            if voice2 is None and singers[1]:
                spans = [(a, b) for a, b, x in zip(page_starts, page_ends, info) if x and 2 in x[2]]
                v2_notes, v2_lyrics = _in_pages(notes, spans), _in_pages(lyrics, spans)
                v2_pages = [(a, b, '') for a, b, v in pages if any(a - 1e-3 <= s < b for s, _ in spans)]
        if not choruses:
            choruses = repeated_lines(pages, _page_texts(pages, lyrics))
        segments = build_segments(page_starts, choruses, song_end, pauses_before_pages(pages, notes), cuts)
    language = layers.get('language') or [(0.0, song_end, 'english')]
    strip = lambda rows: [(t1, t2, re.sub(r'#g\d+', '', v)) for t1, t2, v in rows]
    return {
        'segments': segments,
        'pages': pages,
        'lyrics': lyrics,
        'notes_full': strip(notes),
        'notes2_full': strip(v2_notes), 'lyrics2': list(v2_lyrics), 'pages2': list(v2_pages),
        'language': language,
    }


def write_feat_vxla(vxla_path, out_path, song_duration=0.0, **sources):
    """Writes the feat vxla of a song from its normal vxla, formatted like the official ones (UTF-8, CRLF).
    `sources`: see feat_layers. Returns (segments, notes of the second voice)."""
    layers, _ = OfficialVxla.read_layers(vxla_path)
    if not layers.get('notes_full'):
        raise ValueError(f"{vxla_path} has no notes_full layer")
    feat = feat_layers(layers, song_duration, **sources)
    body = '\r\n\r\n'.join(_layer(name, feat[name]) for name in LAYER_ORDER)
    text = f'<?xml version="1.0" encoding="UTF-8"?>\r\n\r\n<AnnotationFile version="3.0">\r\n{body}\r\n\r\n</AnnotationFile>\r\n'
    with open(out_path, 'wb') as f:
        f.write(text.encode('utf-8'))
    return feat['segments'], len(feat['notes2_full'])


# ---------------------------------------------------------------------------
# beats/<id>.json
# ---------------------------------------------------------------------------

SR = 22050
N_FFT = 2048
HOP = 512
FPS = SR / HOP
SPECTRUM_BINS = 512
# a frame's onset is measured from the window that starts at it: its time is the window centre plus the frame
# compared with (measured against the official beats: our beats came 65 ms early)
ONSET_DELAY_S = (N_FFT / 2 + HOP) / SR


def _decode(path, ffmpeg='ffmpeg'):
    out = subprocess.run([ffmpeg, '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def _mel_filters(n_mels=64):
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    inv = lambda m: 700 * (10 ** (m / 2595) - 1)
    edges = inv(np.linspace(mel(30), mel(SR / 2), n_mels + 2))
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    fb = np.zeros((n_mels, len(freqs)), dtype=np.float32)
    for m in range(n_mels):
        lo, mid, hi = edges[m], edges[m + 1], edges[m + 2]
        fb[m] = np.clip(np.minimum((freqs - lo) / (mid - lo), (hi - freqs) / (hi - mid)), 0, None)
    return fb


def _analyze(y):
    """(onset strength per frame, mean magnitude spectrum in SPECTRUM_BINS bins)."""
    frames = 1 + (len(y) - N_FFT) // HOP
    window = np.hanning(N_FFT).astype(np.float32)
    fb = _mel_filters()
    mels = np.empty((frames, fb.shape[0]), dtype=np.float32)
    spectrum = np.zeros(N_FFT // 2 + 1)
    for start in range(0, frames, 512):
        idx = np.arange(start, min(frames, start + 512))
        block = np.stack([y[i * HOP:i * HOP + N_FFT] for i in idx]) * window
        mag = np.abs(np.fft.rfft(block, axis=1))
        spectrum += mag.sum(axis=0)
        mels[idx] = 10 * np.log10(np.maximum((mag ** 2) @ fb.T, 1e-10))
    mels = np.maximum(mels, mels.max() - 80)
    env = np.concatenate([[0], np.maximum(0, np.diff(mels, axis=0)).mean(axis=1)])
    spectrum = spectrum[:2 * SPECTRUM_BINS].reshape(SPECTRUM_BINS, 2).sum(axis=1)
    return env / (env.std() or 1), spectrum / max(frames, 1)


def _tempo_period(env, center=100.0, lo=60.0, hi=145.0):
    """Beat period in frames: autocorrelation of the onsets, preferring tempos near `center` (official: 65-120)."""
    centered = env - env.mean()
    ac = np.correlate(centered, centered, mode='full')[len(env) - 1:]
    lags = np.arange(int(60 * FPS / hi), int(60 * FPS / lo) + 1)
    bpm = 60 * FPS / lags
    return int(lags[np.argmax(ac[lags] * np.exp(-0.5 * np.log2(bpm / center) ** 2))])


def _track(env, period, tightness=100.0):
    """Beat frames by dynamic programming (Ellis 2007, the method of librosa.beat.beat_track)."""
    n = len(env)
    gauss = np.exp(-0.5 * (np.arange(-period, period + 1) * 32 / period) ** 2)
    local = np.convolve(env, gauss, mode='same')
    score = np.zeros(n)
    back = np.full(n, -1)
    window = np.arange(-2 * period, -(period // 2) + 1)
    cost = -tightness * np.log(-window / period) ** 2
    for i in range(n):
        prev = i + window
        ok = prev >= 0
        if ok.any():
            cand = score[prev[ok]] + cost[ok]
            k = int(np.argmax(cand))
            score[i] = local[i] + cand[k]
            back[i] = prev[ok][k]
        else:
            score[i] = local[i]
    peaks = [i for i in range(1, n - 1) if score[i] >= score[i - 1] and score[i] >= score[i + 1]]
    if not peaks:
        return np.zeros(0, dtype=int)
    threshold = 0.5 * np.median(score[peaks])
    i = max(p for p in peaks if score[p] >= threshold)
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    beats = np.array(beats[::-1])
    strong = local[beats] >= 0.5 * np.sqrt(np.mean(local[beats] ** 2))  # no beats in the silence of start and end
    if strong.any():
        beats = beats[int(np.argmax(strong)):len(strong) - int(np.argmax(strong[::-1]))]
    return beats


def _spectrum_bands(spectrum):
    """Three bands (low, mid, high) of the mean spectrum, each with its loudest bin, and the five loudest peaks."""
    energy = np.cumsum(spectrum ** 2)
    energy /= energy[-1] or 1
    low_end = int(np.clip(np.searchsorted(energy, 0.80), 10, 120))
    mid_end = int(np.clip(np.searchsorted(energy, 0.97), low_end + 20, SPECTRUM_BINS - 40))
    bands = []
    for start, end in ((0, low_end), (low_end + 1, mid_end), (mid_end + 1, SPECTRUM_BINS - 1)):
        bands.append({"startIndex": start, "endIndex": end,
                      "mainIndex": start + int(np.argmax(spectrum[start:end + 1]))})
    peaks = [i for i in range(1, SPECTRUM_BINS - 1) if spectrum[i] >= spectrum[i - 1] and spectrum[i] >= spectrum[i + 1]]
    selection = sorted(sorted(peaks, key=lambda i: spectrum[i], reverse=True)[:5])
    return bands, selection


def song_beats(audio_path, song_id, ffmpeg='ffmpeg'):
    """Contents of beats/<song_id>.json for the song's converted audio."""
    env, spectrum = _analyze(_decode(audio_path, ffmpeg))
    period = _tempo_period(env)
    beats = _track(env, period) / FPS + ONSET_DELAY_S
    gaps = np.diff(beats)
    bpm = int(round(60 / float(np.median(gaps)))) if len(gaps) else int(round(60 * FPS / period))
    bands, selection = _spectrum_bands(spectrum)
    return {"song": song_id, "spectrumBands": bands, "spectrumIndexSelection": selection,
            "bpm": [{"startTime": 0, "value": bpm}], "beats": [round(float(t), 3) for t in beats]}


def write_beats(audio_path, song_id, out_path, ffmpeg='ffmpeg'):
    data = song_beats(audio_path, song_id, ffmpeg)
    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=0)
    return data
