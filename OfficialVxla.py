"""Official Let's Sing lyric/note files (.vxla) reused directly instead of rebuilding them from a txt.

Songs taken from Let's Sing DLCs keep their exact timing, pitch and syllables this way. Two formats exist:
  version 2.0 (Let's Sing 2018-2023): 'notes' (MIDI pitch per interval), 'lyrics_cut' (syllables with the same
                                      timing as the notes), 'lyrics', 'pages', 'notes_golden', 'structure'
  version 3.0 (Let's Sing 2024+):     'notes_full' ("#p<pitch>#.<syllable>"), 'lyrics', 'pages', 'passages', ...
"""
import os
import re
import xml.etree.ElementTree as ET

import UltrastarToSingit
import naming

OFFICIAL_VXLA_NAME = naming.OFFICIAL_VXLA_NAME

_STRUCTURE_NAMES = {'couplet1': 'couplet', 'couplet2': 'couplet', 'couplet3': 'couplet', 'refrain': 'refrain',
                    'bridge': 'pont', 'intro': 'intro', 'outro': 'outro'}


def read_layers(path):
    """{layer name: [(t1, t2, value), ...]} and the file version."""
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # some extracted files declare an encoding they are not written in (e.g. "utf-16" for UTF-8 text)
        text = None
        for encoding in ('utf-8-sig', 'utf-16', 'cp1252', 'latin-1'):
            try:
                text = raw.decode(encoding)
                if '<AnnotationFile' in text:
                    break
            except UnicodeDecodeError:
                continue
        root = ET.fromstring(re.sub(r'^<\?xml[^>]*\?>', '', text.lstrip('\ufeff').lstrip()))
    layers = {}
    for layer in root.findall('IntervalLayer'):
        layers[layer.get('name')] = [(float(i.get('t1')), float(i.get('t2')), i.get('value', ''))
                                     for i in layer.findall('Interval')]
    return layers, root.get('version', '')


def _overlap(a1, a2, b1, b2):
    return min(a2, b2) - max(a1, b1)


def _syllable_for(t1, t2, syllables):
    """Syllable whose interval overlaps the note the most (timings of the two layers can differ slightly)."""
    best, best_overlap = None, 0.0
    for s1, s2, value in syllables:
        if s1 > t2:
            break
        ov = _overlap(t1, t2, s1, s2)
        if ov > best_overlap:
            best, best_overlap = value, ov
    return best


def to_sing_it(layers, song_duration):
    """Converts official layers (v2 or v3) into the structure UltrastarToSingit.write_vxla_file writes."""
    sing_it = {"text": [], "notes": [], "pages": [], "passages": [], "structure": []}

    if 'notes_full' in layers:
        for t1, t2, value in layers['notes_full']:
            sing_it["notes"].append({"t1": t1, "t2": t2, "value": value})
        for t1, t2, value in layers.get('lyrics', []):
            sing_it["text"].append({"t1": t1, "t2": t2, "value": value})
    else:
        syllables = sorted(layers.get('lyrics_cut') or layers.get('lyrics', []))
        golden = layers.get('notes_golden', [])
        for t1, t2, pitch in sorted(layers.get('notes', [])):
            syllable = _syllable_for(t1, t2, syllables)
            if syllable is None:
                syllable = '~'
            value = f"#p{int(pitch)}#.{syllable.strip()}"
            if any(_overlap(t1, t2, g1, g2) > 0 for g1, g2, _ in golden):
                value += "#g5"
            sing_it["notes"].append({"t1": t1, "t2": t2, "value": value})
            if syllable.strip() not in ('', '~', '-'):  # '-' marks a held note, it is not shown
                sing_it["text"].append({"t1": t1, "t2": t2, "value": syllable})
        if layers.get('lyrics'):
            # the shown text is the 'lyrics' layer, as in v3: half of the 'lyrics_cut' layers have no spaces at all
            # ("We're" "tal" "king" "a" "way" -> "We'retalkingaway")
            sing_it["text"] = [{"t1": t1, "t2": t2, "value": value} for t1, t2, value in sorted(layers['lyrics'])
                               if value.strip() not in ('', '~', '-')]

    for t1, t2, value in layers.get('pages', []):
        sing_it["pages"].append({"t1": t1, "t2": t2, "value": value})
    if not sing_it["pages"] and sing_it["notes"]:
        sing_it["pages"].append({"t1": 0.0, "t2": song_duration, "value": ""})

    # choruses -> "segments" (as generated for UltraStar songs)
    for t1, t2, value in layers.get('structure', []):
        if _STRUCTURE_NAMES.get(value, value) == 'refrain':
            sing_it["structure"].append({"t1": t1, "t2": t2, "value": "feat"})

    sing_it["passages"] = [{"t1": t1, "t2": t2, "value": v} for t1, t2, v in layers['passages']] \
        if layers.get('passages') else UltrastarToSingit.build_passages(sing_it["notes"])
    return sing_it


def convert(official_path, output_name, directory, song_duration, output_type):
    """Writes <directory>/<output_name> from an official vxla. Returns the number of notes written."""
    layers, version = read_layers(official_path)
    if not layers.get('notes_full') and not layers.get('notes'):
        raise ValueError(f"{os.path.basename(official_path)} has no notes")
    sing_it = to_sing_it(layers, song_duration)
    UltrastarToSingit.write_vxla_file(sing_it, output_name, directory=directory, song_duration=song_duration,
                                      output_type=output_type)
    return len(sing_it["notes"])


def song_id_from_name(file_name):
    return re.sub(r'(_duet|_feat)?\.vxla$', '', file_name)
