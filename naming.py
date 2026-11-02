"""Song IDs and names of the files the converter generates inside each song folder.

The current name_id algorithm must never change silently: every cached file (and the
very slow to encode .bk2 videos) is named after it. Older algorithms are kept in
legacy_name_ids() so caches created by previous versions can still be reused.
"""
import hashlib
import re
import unicodedata


def strip_accents(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = s.replace('ø', 'o').replace('Ø', 'O')
    s = s.replace('œ', 'oe').replace('Œ', 'OE')
    s = s.replace('æ', 'ae').replace('Æ', 'AE')
    s = s.replace('ß', 'ss')
    s = s.replace('&', 'and')
    return s


def _remove_punctuation(s):
    return s.replace("?", "").replace("!", "").replace(":", "").replace('"', "").replace("/", " ")


def construct_name_id_from_directory_name(dir_long_name) -> str:
    parts = dir_long_name.split(' - ')
    if len(parts) < 2:
        s = strip_accents(dir_long_name).replace(" ", "")
        name_id = ''.join(e for e in s if e.isalnum() and e.isascii())
    else:
        artist_dir_name = _remove_punctuation(strip_accents(parts[0]))
        title_dir_name = _remove_punctuation(strip_accents(parts[1]))

        artist_cap = ''.join(word[0].upper() for word in artist_dir_name.split())
        artist_cap = ''.join(e for e in artist_cap if e.isalnum() and e.isascii())

        title_lower = ''.join(e.lower() for e in title_dir_name if e.isalnum() and e.isascii())
        name_id = artist_cap + title_lower

    if not name_id:
        # Non-latin names (e.g. Japanese, Cyrillic) leave nothing ASCII: use a stable hash instead
        name_id = 'Song' + hashlib.md5(dir_long_name.encode('utf-8')).hexdigest()[:8]
    return name_id


def game_song_id(dir_long_name) -> str:
    """ID the game sees, title first like the official IDs ("2 Be Loved (Am I Ready)" -> "2BeLoved"), followed by
    the artist initials so it never matches an official song ("Zoe Wees - Control" -> "ControlZW").

    Let's Sing 2026 sorts its "Title" list by this ID, not by the title: with the cache ID (artist initials first)
    the custom songs were listed by artist. The cache files keep construct_name_id_from_directory_name."""
    parts = dir_long_name.split(' - ')
    title = ' - '.join(parts[1:]) if len(parts) > 1 else dir_long_name
    title = re.sub(r'\(.*?\)|\[.*?\]', ' ', title)  # "(feat. ...)", "[DUET]" like the official IDs
    words = re.findall(r'[A-Za-z0-9]+', strip_accents(title).replace("'", '').replace('’', ''))
    camel = ''.join(c for c in ''.join(w[0].upper() + w[1:] for w in words) if c.isascii() and c.isalnum())
    if not camel:  # non-latin title: the cache ID is already unique
        return construct_name_id_from_directory_name(dir_long_name)
    artist = _remove_punctuation(strip_accents(parts[0])) if len(parts) > 1 else ''
    initials = ''.join(c for c in (w[0].upper() for w in artist.split()) if c.isascii() and c.isalnum())
    return camel + initials


def _strip_marks(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def legacy_name_ids(dir_long_name) -> list:
    """IDs produced by older versions of construct_name_id_from_directory_name (newest first)."""
    parts = dir_long_name.split(' - ')
    if len(parts) < 2:
        return []
    ids = []
    # 2026-10-03 (362d058): punctuation removed, no ASCII filter, '&' kept
    artist = _remove_punctuation(_strip_marks(parts[0]))
    title = _remove_punctuation(_strip_marks(parts[1]))
    ids.append(''.join(w[0].upper() for w in artist.split()) + ''.join(e.lower() for e in title if e.isalnum()))
    # upstream v1.0.x: accents stripped only
    artist = _strip_marks(parts[0])
    title = _strip_marks(parts[1])
    ids.append(''.join(w[0].upper() for w in artist.split()) + ''.join(e.lower() for e in title if e.isalnum()))

    current = construct_name_id_from_directory_name(dir_long_name)
    result = []
    for i in ids:
        if i and i != current and i not in result:
            result.append(i)
    return result


# Suffixes of every file the converter writes into a song folder (name_id + suffix)
AUDIO_SUFFIX = '.ogg'
AUDIO_PREVIEW_SUFFIX = '_preview.ogg'
COVER_SUFFIX = '.png'
COVER_LONG_SUFFIX = '_long.png'
IN_GAME_LOADING_SUFFIX = '_InGameLoading.png'
RESULT_SUFFIX = '_Result.png'
VXLA_SUFFIX = '.vxla'
VXLA_META_SUFFIX = '.vxla.meta.json'
AUDIO_META_SUFFIX = '.ogg.meta.json'      # how the audio was cut (#START/#END, VIDEOGAP)
PREVIEW_META_SUFFIX = '_preview.ogg.meta.json'  # where the preview was cut from (first chorus)
VIDEO_MP4_SUFFIX = '.mp4'               # final video for XML games, legacy intermediate for JSON games
VIDEO_BK2_SUFFIX = '.bk2'               # final video for JSON games (very slow to encode!)
VIDEO_INTERMEDIATE_SUFFIX = '.avi'      # x264 intermediate fed to binkc
STILL_VIDEO_SUFFIX = '_cover.avi'       # still video made from the cover (bink input)
STILL_VIDEO_MP4_SUFFIX = '_cover.mp4'   # still video made from the cover (XML games / legacy)
META_XML_SUFFIX = '_meta.xml'           # song metadata for XML games
AUTO_COVER_SUFFIX = '_autocover.png'     # placeholder cover (artist + title) for songs without any image
VOICE_SUFFIX = '.voice.npz'              # isolated voice analysis of the sync editor (loudness and pitch)
SYNC_REPORT_SUFFIX = '.sync.json'        # result of tools/sync_scan.py for the GUI (verdict and detail)
VXLA_FEAT_SUFFIX = '_feat.vxla'          # lyrics/notes of the Feat mode (Let's Sing 2026, Songs/vxla_feat)
BEATS_SUFFIX = '.beats.json'             # beat times for the effects of Let's Sing 2026 (Songs/beats/<id>.json)

GENERATED_SUFFIXES = (
    AUDIO_PREVIEW_SUFFIX, AUDIO_SUFFIX,
    COVER_LONG_SUFFIX, IN_GAME_LOADING_SUFFIX, RESULT_SUFFIX, COVER_SUFFIX,
    VXLA_META_SUFFIX, VXLA_SUFFIX, PREVIEW_META_SUFFIX, AUDIO_META_SUFFIX,
    STILL_VIDEO_SUFFIX, STILL_VIDEO_MP4_SUFFIX, AUTO_COVER_SUFFIX, META_XML_SUFFIX,
    VIDEO_MP4_SUFFIX, VIDEO_BK2_SUFFIX, VIDEO_INTERMEDIATE_SUFFIX, VOICE_SUFFIX, SYNC_REPORT_SUFFIX,
    VXLA_FEAT_SUFFIX, BEATS_SUFFIX,
)

# Official Let's Sing lyrics/notes copied into a song folder (tools/attach_official_vxla.py). It is a source
# file, not a generated one: it is never deleted by "Clear cache".
OFFICIAL_VXLA_NAME = 'letssing_original.vxla'

# Never deleted by "Clear cache" unless the user explicitly asks for it
PROTECTED_SUFFIXES = (VIDEO_BK2_SUFFIX,)


def generated_file_names(name_id) -> list:
    return [name_id + suffix for suffix in GENERATED_SUFFIXES]


def is_generated_file(file_name, name_ids) -> bool:
    """True if file_name was written by the converter for any of the given name_ids."""
    for nid in name_ids:
        if not nid:
            continue
        if file_name in (nid + s for s in GENERATED_SUFFIXES):
            return True
        if file_name.startswith(nid + '.mp4_passlog') or file_name.startswith(nid + '.avi_passlog'):
            return True
    return False


def all_name_ids(dir_long_name) -> list:
    return [construct_name_id_from_directory_name(dir_long_name)] + legacy_name_ids(dir_long_name)
