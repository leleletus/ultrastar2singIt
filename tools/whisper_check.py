"""Second opinion on the lyrics timing of SongMaker songs: Whisper (faster-whisper, large-v3-turbo, on the isolated
voice) writes down what is sung, with the time of every word; each lyrics line is looked for among those words near
where the txt puts it. Lines that Whisper hears more than 0.6 s away (3 words or more matched) are added to the song's revisar.json (the sync
editor jumps to them with N). Whisper's words are kept next to the song (<id>.whisper.json), made once.
Whisper is right about the words and usually about the time; in heavily processed choruses its times can be off
(Tarantino: 1.5 s), so these are points to check by ear, not changes.

Usage:
    python tools/whisper_check.py "<song folder>" [...]
"""
import difflib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import VoiceAlign  # noqa: E402
import songmaker_report as R  # noqa: E402

SKIP = {'LISA - Dream'}   # the user's own work
LANGS = {'spanish': 'es', 'english': 'en', 'french': 'fr', 'korean': 'ko', 'japanese': 'ja', 'portuguese': 'pt'}
_MODEL = None


def words_of(folder, language):
    vocals, _ = VoiceAlign.paths(str(folder))
    cache = vocals.replace(VoiceAlign.VOCALS_SUFFIX, '.whisper.json')
    if os.path.exists(cache):
        return json.load(open(cache, encoding='utf-8'))
    global _MODEL
    import soundfile as sf
    from faster_whisper import WhisperModel
    if _MODEL is None:
        _MODEL = WhisperModel('large-v3-turbo', device='cpu', compute_type='int8', cpu_threads=os.cpu_count() or 4)
    audio, rate = sf.read(vocals, dtype='float32')
    audio = audio.mean(axis=1) if audio.ndim > 1 else audio
    segments, _ = _MODEL.transcribe(audio, language=LANGS.get(language.lower().split()[0]), word_timestamps=True,
                                    vad_filter=False, condition_on_previous_text=False, beam_size=5)
    words = [[round(w.start, 2), round(w.end, 2), w.word.strip(), round(w.probability, 2)]
             for seg in segments for w in seg.words]
    json.dump(words, open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return words


def norm(text):
    text = unicodedata.normalize('NFKD', text.lower())
    return re.sub(r"[^a-z0-9ㄱ-힣ぁ-んァ-ン一-龯 ]", '', ''.join(c for c in text if not unicodedata.combining(c)))


def line_words(song, idx, shift):
    """[(word, start s)] of a lyrics line: a word starts with its first syllable."""
    out, current = [], None
    for k in idx:
        t, _, text, _ = song.syllables[k]
        if current is None:
            current = [text, t + shift]
        else:
            current[0] += text
        if text.endswith(' '):
            out.append((norm(current[0]).strip(), current[1]))
            current = None
    if current is not None:
        out.append((norm(current[0]).strip(), current[1]))
    return [(w, t) for w, t in out if w]


def offsets(folder):
    """[(line start, text, Whisper - lyrics in s, words matched)] for the lines Whisper heard: its words are matched
    to the line's words one by one (ad-libs it does not write, like "Uuuh", just do not match), among the stretches
    of words near the line the one closest in time."""
    txt = R.current_txt(folder)
    words = words_of(folder, R.language_of(txt))
    song, shift = R.load(txt, folder)
    heard = [(norm(w[2]).strip(), w[0]) for w in words]
    out = []
    for i, idx in enumerate(song.lines):
        mine = line_words(song, idx, shift)
        if len(mine) < 2:
            continue
        t = mine[0][1]
        best = None
        for k in range(len(heard)):
            if abs(heard[k][1] - t) > 6:
                continue
            got = heard[k:k + len(mine) + 2]
            sm = difflib.SequenceMatcher(None, [w for w, _ in mine], [w for w, _ in got])
            pairs = [(mine[b.a + j][1], got[b.b + j][1]) for b in sm.get_matching_blocks() for j in range(b.size)]
            if len(pairs) < max(2, len(mine) // 2):
                continue
            diff = sorted(g - m for m, g in pairs)[len(pairs) // 2]
            key = (-len(pairs), abs(diff))
            if best is None or key < best[0]:
                best = (key, diff, len(pairs))
        if best:
            text = ''.join(song.syllables[k][2] for k in idx).replace('~', '').strip()
            out.append((t, text, best[1], best[2]))
    return out


BIAS_S = -0.08   # Whisper's words start this much before the syllables (measured on songs checked by ear)
LIMIT_S = 0.6


def check(folder, bias=BIAS_S, limit=LIMIT_S):
    out = []
    for t, text, diff, matched in offsets(folder):
        if abs(diff - bias) > limit and matched >= 3:
            out.append({'t': round(min(t, t + diff), 1),
                        'why': f"Whisper oye «{text}» {diff - bias:+.1f} s respecto a la letra "
                               f"({int((t + diff) // 60)}:{(t + diff) % 60:04.1f} frente a {int(t // 60)}:{t % 60:04.1f}) "
                               "→ escuchar cuál es"})
    return out


def main():
    folders = [Path(a) for a in sys.argv[1:]]
    if len(folders) == 1 and not (folders[0] / 'songmaker.json').exists():  # a songs folder: every SongMaker song
        folders = [d for d in sorted(folders[0].iterdir()) if (d / 'songmaker.json').exists()]
    for folder in folders:
        meta = json.loads((folder / 'songmaker.json').read_text(encoding='utf-8'))
        if meta.get('user_checked') or folder.name in SKIP:
            continue
        found = check(folder)
        review = folder / 'revisar.json'
        points = json.loads(review.read_text(encoding='utf-8')) if review.exists() else []
        points = [p for p in points if not p['why'].startswith('Whisper oye')] + found
        points.sort(key=lambda p: p['t'])
        review.write_text(json.dumps(points, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f"{folder.name}: {len(found)} líneas donde Whisper no coincide", flush=True)
        for p in found:
            print('   ', p['why'], flush=True)


if __name__ == '__main__':
    main()
