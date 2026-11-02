"""Sections of a song (verse, pre-chorus, chorus, bridge...) and who sings each one, from its lyrics on Genius.

Genius heads every part with its kind and, in songs with more than one artist, its singers:
"[Verso 1: Luis Fonsi]", "[Coro: Luis Fonsi, Demi Lovato & Both]". The converter uses it for the Feat mode of
Let's Sing 2026: the lines of the featured singer become the second voice (shown in its own colour, as in the official
duets) and the section changes are where the song is cut between the singers.

The page is cached next to the txt as <txt>_genius_sections.json (also "not found", retried after a while), so only
the first conversion of a song needs internet. The URL found by the chorus lookup (<txt>_genius_cache.json) is reused.
"""
import difflib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path

import UltrastarToSingit

logger = logging.getLogger(__name__)

CACHE_SUFFIX = '_genius_sections.json'
NOT_FOUND_RETRY_DAYS = 30
SECTION_VERSION = 2

_KINDS = (
    ('prechorus', r'pre[- ]?(chorus|coro|estribillo|refrain|refr[aã]o|ritornello)'),
    ('postchorus', r'post[- ]?(chorus|coro|estribillo|refrain)'),
    ('chorus', r'chorus|coro|estribillo|refrain|refr[aã]o|ritornello|refrein|refren|hook|nakarat|припев'),
    ('bridge', r'bridge|puente|pont|ponte|br[uü]cke'),
    ('verse', r'verse|verso|estrofa|couplet|strophe|strofa|vers\b|parte|part\b'),
    ('intro', r'intro'),
    ('outro', r'outro|final'),
    ('break', r'interlude|instrumental|break|drop|solo'),
)
BOTH_WORDS = {'both', 'all', 'todos', 'ambos', 'juntos', 'tous', 'alle', 'tutti', 'together'}
SPLIT_SINGERS = r'\s*(?:,|&|\+|/|\band\b|\by\b|\bet\b|\bund\b|\be\b|\bwith\b|\bcon\b|\bx\b|\bfeat\.?|\bft\.?)\s*'


def _simple(text):
    text = unicodedata.normalize('NFKD', text.lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]+', ' ', text).split()


def section_kind(header):
    name = header.split(':', 1)[0].lower()
    for kind, pattern in _KINDS:
        if re.search(pattern, name):
            return kind
    return 'other'


ITALIC, BOLD = '\x01', '\x02'   # markers of <i>/<b> text: Genius tells the singers of one section apart this way


def _style(text):
    if BOLD in text:
        return 'bold'
    if ITALIC in text:
        return 'italic'
    return 'plain'


def _plain(text):
    return text.replace(ITALIC, '').replace(BOLD, '')


def header_singers(header):
    """[(name, style)] of a header: "Coro: Luis Fonsi, <i>Demi Lovato</i> & <b>Both</b>"."""
    if ':' not in header:
        return []
    names = re.split(SPLIT_SINGERS, header.split(':', 1)[1], flags=re.IGNORECASE)
    out = []
    for name in names:
        clean = _plain(name).strip(' *()')
        if clean:
            out.append((clean, _style(name)))
    return out


def parse_lyrics(html):
    """[{'header', 'kind', 'singers': [[name, style]], 'lines': [[text, style]]}] of a Genius lyrics page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    text = ''
    for div in soup.find_all('div', class_=lambda x: x and x.startswith('Lyrics__Container')):
        for junk in div.find_all(['script', 'style', 'button']):
            junk.decompose()
        for junk in div.find_all(class_=lambda x: x and re.match(r'(LyricsHeader|SongBioPreview|Contributor)', x)):
            junk.decompose()
        for tag, mark in (('i', ITALIC), ('em', ITALIC), ('b', BOLD), ('strong', BOLD)):
            for el in div.find_all(tag):
                el.insert(0, mark)
                el.append(mark)
        for br in div.find_all('br'):
            br.replace_with('\n')
        text += div.get_text(separator='') + '\n'
    sections, current = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not _plain(line).strip():
            continue
        header = re.fullmatch(r'\[([^\]]+)\]', _plain(line))
        if header:
            label = header.group(1)
            if re.match(r'(letra|lyrics|paroles|testo|songtext)\b', label, re.IGNORECASE):
                continue
            marked = re.fullmatch(r'\[(.+)\]', line.replace(ITALIC + '[', '[').replace(BOLD + '[', '['))
            current = {'header': label, 'kind': section_kind(label),
                       'singers': [list(x) for x in header_singers(marked.group(1) if marked else label)], 'lines': []}
            sections.append(current)
        elif current is not None:
            current['lines'].append([_plain(line), _style(line)])
    return [s for s in sections if s['lines']]


def _page_url(txt_path, artist, title):
    chorus_cache = Path(txt_path).with_name(Path(txt_path).stem + '_genius_cache.json')
    try:
        url = json.loads(chorus_cache.read_text(encoding='utf-8')).get('url')
        if url:
            return url
    except (OSError, ValueError):
        pass
    return UltrastarToSingit.genius_search_for_correct_path(artist, title)


def get_sections(txt_path, artist, title, online=True):
    """Sections of the song (cached), or None when Genius has no page for it or is not reachable."""
    import requests
    txt_path = Path(txt_path)
    cache = txt_path.with_name(txt_path.stem + CACHE_SUFFIX)
    try:
        data = json.loads(cache.read_text(encoding='utf-8'))
        if data.get('version') == SECTION_VERSION:
            if not data.get('not_found'):
                return data['sections']
            if time.time() - data.get('checked', 0) < NOT_FOUND_RETRY_DAYS * 86400:
                return None
    except (OSError, ValueError):
        pass
    if not online or UltrastarToSingit._genius_offline:
        return None
    url = _page_url(txt_path, artist, title)
    sections = None
    if url:
        try:
            response = requests.get(url, headers=UltrastarToSingit.GENIUS_HEADERS, timeout=10)
            if response.status_code == 200:
                sections = parse_lyrics(response.content)
        except requests.exceptions.ConnectionError as e:
            UltrastarToSingit._set_genius_offline(e)
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Genius page of {artist} - {title} not read: {e}")
            return None
    payload = {'version': SECTION_VERSION, 'url': url, 'sections': sections} if sections else \
        {'version': SECTION_VERSION, 'not_found': True, 'checked': time.time()}
    try:
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    except OSError as e:
        logger.warning(f"Could not write {cache.name}: {e}")
    return sections


# ---------------------------------------------------------------------------
# Who is voice 1 and who is voice 2
# ---------------------------------------------------------------------------

def song_singers(artist, title=''):
    """(voice 1 singers, voice 2 singers) from the artist and title: "A & B" -> ([A], [B]);
    "A feat. B, C" or "Title (feat. B)" -> ([A], [B, C])."""
    featured = []
    found = re.search(r'[\(\[]\s*(?:feat\.?|ft\.?|featuring|with|con)\s+([^\)\]]+)[\)\]]', title, re.IGNORECASE)
    if found:
        featured += re.split(SPLIT_SINGERS, found.group(1), flags=re.IGNORECASE)
    parts = re.split(r'\s+(?:feat\.?|ft\.?|featuring)\s+', artist, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        featured = re.split(SPLIT_SINGERS, parts[1], flags=re.IGNORECASE) + featured
    main = re.split(r'\s*(?:,|&|\+|\s+x\s+|\s+and\s+|\s+y\s+|\s+with\s+|\s+vs\.?\s+)\s*', parts[0], flags=re.IGNORECASE)
    main = [m.strip() for m in main if m.strip()]
    featured = [f.strip() for f in featured if f.strip()]
    return main[:1], main[1:] + featured


def _same_person(a, b):
    sa, sb = ' '.join(_simple(a)), ' '.join(_simple(b))
    return bool(sa and sb) and (sa == sb or sa in sb or sb in sa
                                or difflib.SequenceMatcher(None, sa, sb).ratio() >= 0.8)


def _voices_of(name, voice1, voice2):
    if name.lower() in BOTH_WORDS:
        return {1, 2}
    if any(_same_person(name, v) for v in voice1):
        return {1}
    if any(_same_person(name, v) for v in voice2):
        return {2}
    return set()


def section_voices(section, voice1, voice2):
    """{style: voices} of a section (its singers by the formatting of their names) and the voices of the whole
    section ({1}, {2} or {1, 2}; None when its singers are not named)."""
    by_style, all_voices = {}, set()
    for name, style in section['singers']:
        voices = _voices_of(name, voice1, voice2)
        if voices:
            by_style.setdefault(style, set()).update(voices)
            all_voices |= voices
    return by_style, (all_voices or None)


def align_pages(page_texts, sections, voice1, voice2):
    """For every page (line of the song): (section index, section kind, voices) or None when no line matched.

    Lines are matched in order (the song and the page follow the same order), each page with the most similar line
    a little ahead of the last match. A line takes the singers of its formatting (plain/italic/bold) when the header
    names them that way, else the singers of its section; a section without named singers keeps the previous
    singers (the first one is voice 1)."""
    lines = []
    last_voices = {1}
    for index, section in enumerate(sections):
        by_style, voices = section_voices(section, voice1, voice2)
        voices = voices or last_voices
        last_voices = voices
        single = len(by_style) == 1
        for text, style in section['lines']:
            line_voices = voices if single else by_style.get(style, voices)
            lines.append((' '.join(_simple(text)), index, section['kind'], frozenset(line_voices)))
    def score(page, line):
        if not page or not line:
            return 0.0
        whole = difflib.SequenceMatcher(None, page, line).ratio()
        page_words, line_words = page.split(), set(line.split())
        # a page can be half of a Genius line (official DLC pages are short phrases)
        part = sum(w in line_words for w in page_words) / len(page_words) if len(page_words) >= 2 else 0.0
        return max(whole, part * 0.9)

    out, cursor = [], 0
    for text in page_texts:
        words = ' '.join(_simple(text))
        best, best_j = 0.0, None
        for j in range(cursor, min(len(lines), cursor + 12)):
            value = score(words, lines[j][0])
            if value > best:
                best, best_j = value, j
        if best_j is not None and best >= 0.55:
            out.append(lines[best_j][1:])
            cursor = best_j  # the next page may be the rest of the same line
        else:
            out.append(None)
    return out
