"""Lyrics aligned to the sung voice with a speech model (MMS forced aligner, wav2vec2 CTC, 1130 languages written in
Latin letters): where each syllable of a line really starts, also in legato lines where loudness and pitch show no
border between syllables.

SongMaker's syllables are already in Latin letters (Korean and Japanese are romanized as Let's Sing shows them), and
that is what the model reads, so the same code works for every language.

Files next to each song (made once, then reused):
    <id>.vocals.flac   the isolated voice, 16 kHz mono (Demucs; a few MB)
    <id>.ctc.npz       the model's letter probabilities every 20 ms (a few hundred kB)

Needs torch and transformers (requirements-slow.txt); the model (~1.2 GB) is downloaded the first time.
"""
import json
import os
import unicodedata

import numpy as np

MODEL = 'MahmoudAshraf/mms-300m-1130-forced-aligner'
RATE = 16000
FRAME = 0.02            # s, one model frame (320 samples), the same step as the voice analysis
VOCALS_SUFFIX = '.vocals.flac'
CTC_SUFFIX = '.ctc.npz'
CTC_VERSION = 1
CHUNK_S, CONTEXT_S = 30.0, 1.0  # the song goes through the model in pieces (memory), with context on each side

_MODEL = None
_SPECIAL = {'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'ø': 'o', 'đ': 'd', 'ł': 'l', 'ı': 'i', 'þ': 'th'}


def save_vocals(vocals_wav, out_path):
    """The Demucs vocals.wav as 16 kHz mono FLAC."""
    import soundfile as sf
    from math import gcd
    from scipy.signal import resample_poly
    audio, rate = sf.read(vocals_wav, dtype='float32', always_2d=True)
    audio = audio.mean(axis=1)
    if rate != RATE:
        g = gcd(RATE, rate)
        audio = resample_poly(audio, RATE // g, rate // g).astype(np.float32)
    tmp = out_path + '.tmp.flac'
    sf.write(tmp, np.clip(audio, -1, 1), RATE, subtype='PCM_16')
    os.replace(tmp, out_path)


def _load():
    global _MODEL
    if _MODEL is None:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import Wav2Vec2ForCTC
        torch.set_num_threads(max(1, os.cpu_count() or 1))
        model = Wav2Vec2ForCTC.from_pretrained(MODEL)
        model.eval()
        vocab = json.load(open(hf_hub_download(MODEL, 'vocab.json'), encoding='utf-8'))
        _MODEL = (model, vocab)
    return _MODEL


def vocabulary():
    """{letter: index} of the model (from the cache next to the songs it is not needed)."""
    return _load()[1]


def emissions(vocals_path):
    """Log-probabilities (frames x letters, float16) of the model every FRAME seconds."""
    import soundfile as sf
    import torch
    model, _ = _load()
    audio, rate = sf.read(vocals_path, dtype='float32')
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    assert rate == RATE, rate
    chunk, context, hop = int(CHUNK_S * RATE), int(CONTEXT_S * RATE), int(FRAME * RATE)
    frames = len(audio) // hop
    out = []
    for start in range(0, len(audio), chunk):
        a, b = max(0, start - context), min(len(audio), start + chunk + context)
        piece = audio[a:b]
        piece = (piece - piece.mean()) / (piece.std() + 1e-7)  # what the model's feature extractor does
        with torch.inference_mode():
            logits = model(torch.from_numpy(piece)[None]).logits[0]
            logp = torch.log_softmax(logits.float(), dim=-1).numpy()
        first = (start - a) // hop
        count = min(chunk, len(audio) - start) // hop
        out.append(logp[first:first + count])
    em = np.concatenate(out)[:frames]
    if len(em) < frames:  # the last frames of the song, if the model gave fewer
        em = np.concatenate([em, np.repeat(em[-1:], frames - len(em), axis=0)])
    return em.astype(np.float16)


def save_emissions(vocals_path, out_path):
    em = emissions(vocals_path)
    tmp = out_path + '.tmp.npz'
    np.savez_compressed(tmp, logp=em, vocab=json.dumps(vocabulary()), version=CTC_VERSION,
                        vocals_size=os.path.getsize(vocals_path))
    os.replace(tmp, out_path)


def load_emissions(path):
    """(logp float32 frames x letters, {letter: index}) or None."""
    try:
        data = np.load(path)
        if int(data['version']) != CTC_VERSION:
            return None
        return data['logp'].astype(np.float32), json.loads(str(data['vocab']))
    except (OSError, KeyError, ValueError):
        return None


def letters(text, vocab):
    """Model indices of the letters of a syllable (accents taken off, signs left out)."""
    out = []
    for c in unicodedata.normalize('NFKD', text.lower()):
        if unicodedata.combining(c):
            continue
        for d in _SPECIAL.get(c, c):
            if d in vocab and d not in ('<pad>', '<s>', '</s>', '<unk>', '|', '<star>'):
                out.append(vocab[d])
    return out


def _viterbi(logp, tokens, blank):
    """CTC forced alignment of tokens on logp (frames x letters): (first frame, last frame) of each token, and
    the mean log-probability of the path; None if the window is too short."""
    T, L = len(logp), len(tokens)
    S = 2 * L + 1
    labels = np.full(S, blank)
    labels[1::2] = tokens
    skip = np.zeros(S, bool)  # a letter can follow the one before without a blank when they differ
    skip[3::2] = np.array(tokens[1:]) != np.array(tokens[:-1]) if L > 1 else []
    need = L + int(np.sum(np.array(tokens[1:]) == np.array(tokens[:-1]))) if L > 1 else L
    if T < need:
        return None
    score = np.full(S, -np.inf)
    score[0] = logp[0, blank]
    score[1] = logp[0, labels[1]]
    back = np.zeros((T, S), np.int8)
    for t in range(1, T):
        stay = score
        step = np.concatenate([[-np.inf], score[:-1]])
        jump = np.where(skip, np.concatenate([[-np.inf, -np.inf], score[:-2]]), -np.inf)
        best = np.maximum(stay, np.maximum(step, jump))
        back[t] = np.where(best == stay, 0, np.where(best == step, 1, 2))
        score = best + logp[t, labels]
    end = S - 1 if score[S - 1] >= score[S - 2] else S - 2
    total = score[end]
    path = np.zeros(T, int)
    s = end
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= int(back[t, s])
    spans = [[None, None] for _ in range(L)]
    for t, s in enumerate(path):
        if s % 2:
            k = s // 2
            if spans[k][0] is None:
                spans[k][0] = t
            spans[k][1] = t
    if any(a is None for a, _ in spans):
        return None
    return spans, float(total) / T


def align_line(logp, vocab, a, b, syllables):
    """Start and end frame of each syllable of a line looked for between frames a and b (absolute frames), and the
    mean log-probability of the letters (how sure the model is); syllables without letters ("~", "!") get the time
    of the one before. None when it cannot be aligned."""
    blank = vocab.get('<blank>', vocab.get('<pad>', 0))
    groups = [letters(s, vocab) for s in syllables]
    tokens = [x for g in groups for x in g]
    a, b = max(0, a), min(len(logp), b)
    if not tokens or b - a < 2:
        return None
    found = _viterbi(logp[a:b], tokens, blank)
    if found is None:
        return None
    spans, mean = found
    out, k = [], 0
    for g in groups:
        if g:
            out.append((a + spans[k][0], a + spans[k + len(g) - 1][1]))
            k += len(g)
        else:
            out.append(out[-1] if out else None)
    if out and out[0] is None:
        first = next(x for x in out if x is not None)
        out = [x if x is not None else first for x in out]
    letter_logp = float(np.mean([logp[a + t0, tok] for (t0, _), tok in zip(spans, tokens)]))
    return out, letter_logp, mean


def file_id(song_dir):
    import naming
    folder = os.path.basename(os.path.normpath(song_dir)).rstrip('.')
    return naming.construct_name_id_from_directory_name(folder)


def paths(song_dir):
    nid = file_id(song_dir)
    return os.path.join(song_dir, nid + VOCALS_SUFFIX), os.path.join(song_dir, nid + CTC_SUFFIX)


def prepare(song_dir, audio_path, log=print):
    """Makes the vocals and the model output of a song if they are missing. Returns (logp, vocab)."""
    vocals, ctc = paths(song_dir)
    data = load_emissions(ctc) if os.path.exists(ctc) else None
    if data is not None:
        return data
    if not os.path.exists(vocals):
        import tempfile
        import SyncModel
        work_root = os.path.join(os.path.expanduser('~'), '.cache', 'letssing_converter')  # on disk, not tmpfs
        os.makedirs(work_root, exist_ok=True)
        log(f"{os.path.basename(song_dir)}: isolating the voice (Demucs)")
        with tempfile.TemporaryDirectory(dir=work_root) as tmp:
            save_vocals(SyncModel.isolate_voice(audio_path, tmp), vocals)
    log(f"{os.path.basename(song_dir)}: aligning model")
    save_emissions(vocals, ctc)
    return load_emissions(ctc)
