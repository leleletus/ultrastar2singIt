import logging
import math
import statistics
import sys

from ConfigLoader import plugins_dir

logger = logging.getLogger(__name__)

# Tag written by the Let's Sing → UltraStar extractors (tools/) with the exact shift that turns the
# txt pitches back into the game's original ones, e.g. "#LETSSINGPITCHOFFSET:36"
PITCH_OFFSET_TAG = 'LETSSINGPITCHOFFSET'

# Usual shift for UltraStar files (0 = C4); used to break ties between equally good octaves
DEFAULT_SHIFT = 48

_HAS_SLOW_DEPS = None


def _slow_deps_available() -> bool:
    """Imported lazily: TensorFlow takes seconds to load and is only needed by the slow method."""
    global _HAS_SLOW_DEPS
    if _HAS_SLOW_DEPS is not None:
        return _HAS_SLOW_DEPS
    plugins = plugins_dir()
    if plugins.is_dir() and str(plugins) not in sys.path:
        sys.path.insert(0, str(plugins))
    try:
        import numpy, librosa, crepe
        _HAS_SLOW_DEPS = True
    except ImportError as ie:
        logger.error(f"Slow pitch correction dependencies not available: {ie}")
        _HAS_SLOW_DEPS = False
    return _HAS_SLOW_DEPS


def get_explicit_pitch_offset(txt_data):
    value = txt_data.get(PITCH_OFFSET_TAG)
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        logger.warning(f"Ignoring invalid #{PITCH_OFFSET_TAG}:{value}")
        return None


def choose_octave_shift(pitches, min_pitch, max_pitch, preferred_shift):
    """Multiple of 12 that leaves the fewest notes outside [min_pitch, max_pitch].

    Shifting by whole octaves keeps every note on its real pitch class, so scoring still matches
    the singer; ties are resolved by the shift closest to preferred_shift.
    """
    best_shift, best_key = 0, None
    for k in range(-4, 9):
        shift = 12 * k
        outside = sum(1 for p in pitches if p + shift < min_pitch or p + shift > max_pitch)
        key = (outside, abs(shift - preferred_shift))
        if best_key is None or key < best_key:
            best_shift, best_key = shift, key
    return best_shift


def get_pitch_correction_suggestion_slow(txt_data, audio_file, min_pitch, max_pitch, use_demucs=False):
    explicit = get_explicit_pitch_offset(txt_data)
    if explicit is not None:
        logger.info(f"Pitch correction from #{PITCH_OFFSET_TAG}: {explicit}")
        return explicit

    if not _slow_deps_available():
        logger.warning("Slow pitch correction unavailable (missing numpy/librosa/crepe). "
                       "Falling back to fast method.")
        return get_pitch_correction_suggestion_fast(txt_data, min_pitch, max_pitch)

    pitch_from_txt = get_txt_pitch_values(txt_data)
    if pitch_from_txt['count'] == 0:
        logger.info("No sung notes found, suggested pitch correction: 0")
        return 0

    if min_pitch < pitch_from_txt['min'] and max_pitch > pitch_from_txt['max']:
        logger.info("Suggested pitch correction: 0")
        return 0
    target_audio = audio_file
    if use_demucs:
        logger.info(f"Isolating vocals with Demucs for {audio_file}...")
        try:
            import subprocess
            import os
            from pathlib import Path

            audio_path = Path(audio_file)
            out_dir = audio_path.parent / "demucs_out"

            # Run demucs with two stems (vocals/no_vocals) on fast model
            cmd = [
                sys.executable, "-m", "demucs",
                "--two-stems", "vocals",
                "-n", "htdemucs_ft",
                "-o", str(out_dir),
                "-d", "cpu",
                str(audio_path)
            ]

            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # The output will be in demucs_out/htdemucs_ft/<songname>/vocals.wav
            vocal_path = out_dir / "htdemucs_ft" / audio_path.stem / "vocals.wav"
            if vocal_path.exists():
                target_audio = str(vocal_path)
                logger.info(f"Successfully isolated vocals: {target_audio}")
            else:
                logger.warning("Demucs finished but vocals.wav not found.")
        except Exception as e:
            logger.error(f"Demucs vocal isolation failed: {e}")
            logger.info("Falling back to full mixed audio.")

    pitch_from_audio = get_audio_pitch_values(target_audio)

    logger.info(f"Expected pitch range (from .txt): {pitch_from_txt}")
    logger.info(f"Actual pitch range (from audio): {pitch_from_audio}")
    if not pitch_from_audio:
        return get_pitch_correction_suggestion_fast(txt_data, min_pitch, max_pitch)

    # the measured difference is rounded to whole octaves, a non-octave shift would transpose the song
    measured = pitch_from_audio['median'] - pitch_from_txt['median']
    preferred = 12 * round(measured / 12)
    pitch_corr = choose_octave_shift(pitch_from_txt['all'], min_pitch, max_pitch, preferred)
    logger.info(f"Suggested pitch correction: {pitch_corr} (measured {measured})")
    return pitch_corr


def get_txt_pitch_values(txt_data):
    all_pitches = []
    for note in txt_data["notes"]:
        if note and (note[0] == ":" or note[0] == "*"):
            try:
                all_pitches.append(int(note[3]))
            except (ValueError, IndexError):
                continue
    if not all_pitches:
        return {'average': 0, 'min': 0, 'max': 0, 'median': 0, 'count': 0, 'all': []}
    return {
        'average': int(round(statistics.mean(all_pitches))),
        'min': min(all_pitches),
        'max': max(all_pitches),
        'median': int(round(statistics.median_grouped(all_pitches))),
        'count': len(all_pitches),
        'all': all_pitches,
    }


def get_audio_pitch_values(audio_file):
    pitch_data = analyze_pitch_from_audio(audio_file)
    valid_notes = [n for n in pitch_data['midi_notes'] if not math.isnan(n)]

    if len(valid_notes) == 0:
        return None

    return {
        'average': int(round(statistics.mean(valid_notes))),
        'min': int(round(min(valid_notes))),
        'max': int(round(max(valid_notes))),
        'median': int(round(statistics.median_grouped(valid_notes)))
    }


def analyze_pitch_from_audio(audio_file):
    import numpy
    import librosa
    import crepe

    y, sr = librosa.load(audio_file, sr=16000)
    time, frequency, confidence, activation = crepe.predict(y, sr, viterbi=False, model_capacity='tiny')
    frequency[confidence < 0.9] = numpy.nan
    midi_notes = librosa.hz_to_midi(frequency)

    return {
        'time': time,
        'frequency': frequency,
        'midi_notes': midi_notes,
        'confidence': confidence
    }


def get_pitch_correction_suggestion_fast(txt_data, min_pitch, max_pitch):
    explicit = get_explicit_pitch_offset(txt_data)
    if explicit is not None:
        logger.info(f"Pitch correction from #{PITCH_OFFSET_TAG}: {explicit}")
        return explicit

    pitch_from_txt = get_txt_pitch_values(txt_data)
    if pitch_from_txt['count'] == 0:
        logger.info("No sung notes found, suggested pitch correction: 0")
        return 0

    # files whose pitches already look like the game's range are left where they are
    preferred = 0 if 40 <= pitch_from_txt['median'] <= 80 else DEFAULT_SHIFT
    pitch_corr = choose_octave_shift(pitch_from_txt['all'], min_pitch, max_pitch, preferred)

    logger.info(f"Suggested pitch correction: {pitch_corr}")
    return pitch_corr
