import logging
import math
import statistics
import sys

from ConfigLoader import plugins_dir

logger = logging.getLogger(__name__)

def _slow_deps_available() -> bool:
    plugins = plugins_dir()
    if plugins.is_dir() and str(plugins) not in sys.path:
        sys.path.insert(0, str(plugins))
    try:
        import numpy, librosa, crepe
        return True
    except ImportError as ie:
        logger.error(f"Slow pitch correction dependencies not available: {ie}")
        return False

_HAS_SLOW_DEPS = _slow_deps_available()

def get_pitch_correction_suggestion_slow(txt_data, audio_file, min_pitch, max_pitch, use_demucs=False):
    if not _HAS_SLOW_DEPS:
        logger.warning("Slow pitch correction unavailable (missing numpy/librosa/crepe). "
                       "Falling back to fast method.")
        return get_pitch_correction_suggestion_fast(txt_data, min_pitch, max_pitch)

    pitch_from_txt = get_txt_pitch_values(txt_data)

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
    logger.info(f"Suggested pitch correction: {pitch_from_audio['median'] - pitch_from_txt['median'] if pitch_from_audio else 0}")

    return pitch_from_audio['median'] - pitch_from_txt['median'] if pitch_from_audio else 0

def get_txt_pitch_values(txt_data):
    total_pitch = 0
    note_count = 0
    all_pitches = []
    for note in txt_data["notes"]:
        if note[0] == ":" or note[0] == "*":
            try:
                pitch = int(note[3])
                total_pitch += pitch
                note_count += 1
                all_pitches.append(pitch)
            except (ValueError, IndexError):
                continue
    average_pitch = int(round(total_pitch / note_count))
    median_pitch = int(round(statistics.median_grouped(all_pitches) if all_pitches else 0))
    min_pitch = min(all_pitches) if all_pitches else 0
    max_pitch = max(all_pitches) if all_pitches else 0
    pitch_from_txt = {
        'average': average_pitch,
        'min': min_pitch,
        'max': max_pitch,
        'median': median_pitch
    }
    return pitch_from_txt

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
    pitch_from_txt = get_txt_pitch_values(txt_data)

    required_corr = 0
    if 40 <= pitch_from_txt['average'] <= 80:
        logger.info("Suggested pitch correction: 0")
        return 0
    elif pitch_from_txt['max'] > 33:
        s_max = max_pitch - pitch_from_txt['max']
        required_corr = max(required_corr, s_max)
    elif pitch_from_txt['min'] < -5:
        s_min = min_pitch - pitch_from_txt['min']
        required_corr = max(required_corr, s_min)
    if required_corr > 0:
        pitch_corr = required_corr
    else:
        pitch_corr = 48

    logger.info(f"Suggested pitch correction: {pitch_corr}")

    return pitch_corr
