"""Regression tests for the converter. Run with:  python -m unittest discover -s tests -v

They don't need ffmpeg, RAD Video Tools nor internet (Genius lookups are disabled)."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import naming  # noqa: E402
import PitchAnalyzer  # noqa: E402
import UltrastarToSingit  # noqa: E402
import ConvertFiles  # noqa: E402
from munch import munchify  # noqa: E402

UltrastarToSingit._genius_offline = True  # never touch the network in tests


def write(path, text, encoding='utf-8'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode(encoding))
    return path


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='lsconv_test_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class NamingTest(unittest.TestCase):
    # IDs already used by converted caches (.bk2!): they must never change
    KNOWN_IDS = {
        'GAYLE - abcdefu': 'Gabcdefu',
        'Simon & Garfunkel - The Sound of Silence': 'SAGthesoundofsilence',
        'Mø - Lean On': 'Mleanon',
        'Beyoncé - Halo': 'Bhalo',
        'Shakira feat. Wyclef Jean - Hips Don’t Lie': 'SFWJhipsdontlie',
        'Anuel AA, Daddy Yankee, Karol G, Ozuna & J Balvin - China': 'AADYKGOAJBchina',
        'Cutting Crew - (I Just) Died In Your Arms': 'CCijustdiedinyourarms',
        'AC/DC - T.N.T.': 'ADtnt',
        'Œdipe - Ça va': 'Ocava',
        'Sabrina Carpenter - Please Please Please': 'SCpleasepleaseplease',
    }

    def test_ids_are_stable(self):
        for folder, expected in self.KNOWN_IDS.items():
            self.assertEqual(naming.construct_name_id_from_directory_name(folder), expected, folder)

    def test_legacy_ids(self):
        self.assertIn('S&Gthesoundofsilence', naming.legacy_name_ids('Simon & Garfunkel - The Sound of Silence'))
        self.assertEqual(naming.legacy_name_ids('GAYLE - abcdefu'), [])

    def test_non_latin_name_gets_an_id(self):
        name_id = naming.construct_name_id_from_directory_name('九 - 歌')
        self.assertTrue(name_id.startswith('Song') and len(name_id) == 12)
        self.assertEqual(name_id, naming.construct_name_id_from_directory_name('九 - 歌'))

    def test_generated_files(self):
        ids = ['Gabcdefu']
        for name in ('Gabcdefu.ogg', 'Gabcdefu_preview.ogg', 'Gabcdefu.bk2', 'Gabcdefu_cover.avi',
                     'Gabcdefu.avi', 'Gabcdefu.vxla', 'Gabcdefu.vxla.meta.json', 'Gabcdefu_meta.xml'):
            self.assertTrue(naming.is_generated_file(name, ids), name)
        for name in ('Abc.bk2', 'Abc.ogg', 'GAYLE - abcdefu.txt', 'cover.jpg'):
            self.assertFalse(naming.is_generated_file(name, ids), name)


class ParserTest(TempDirTest):
    HEADER = "#TITLE:Je veux\n#ARTIST:Zaz\n#BPM:300\n#GAP:1000\n"
    LYRICS = ": 2000 3 5  J’ai\n: 2004 3 5  été\n: 2008 3 5  là\n: 2012 3 5  garçon\nE\n"
    FILLER = "".join(f": {i * 4} 3 5  la\n" for i in range(300))

    def lyrics(self, path):
        data = UltrastarToSingit.parse_file(path)
        return [n[4].strip() for n in data['notes'] if len(n) > 4 and n[4].strip() not in ('la', '')]

    def test_accents_after_first_4kb_are_kept(self):
        # used to be read as ASCII with errors='ignore': été -> t
        p = write(self.tmp / 'a.txt', self.HEADER + self.FILLER + self.LYRICS)
        self.assertEqual(self.lyrics(p), ['J’ai', 'été', 'là', 'garçon'])

    def test_cp1252_and_bom(self):
        p = write(self.tmp / 'b.txt', self.HEADER + self.LYRICS.replace('’', "'"), 'cp1252')
        self.assertEqual(self.lyrics(p), ["J'ai", 'été', 'là', 'garçon'])
        p = write(self.tmp / 'c.txt', '﻿' + self.HEADER + self.LYRICS)
        self.assertEqual(UltrastarToSingit.parse_file(p)['TITLE'], 'Je veux')

    def test_tolerant_lines(self):
        p = write(self.tmp / 'd.txt', "#title: X \n#bpm:200\n: 0 2 5\n:  4  2  5 hola\nE\nbasura\n")
        data = UltrastarToSingit.parse_file(p)
        self.assertEqual(data['TITLE'], 'X')
        self.assertEqual(data['BPM'], '200')
        self.assertEqual(data['notes'], [[':', '0', '2', '5', ''], [':', '4', '2', '5', 'hola'], ['E']])

    def test_relative_and_duet(self):
        p = write(self.tmp / 'r.txt', "#TITLE:R\n#BPM:200\n#RELATIVE:yes\n: 0 2 5 a\n- 4 6\n: 0 2 7 b\nE\n")
        self.assertEqual([n[1] for n in UltrastarToSingit.parse_file(p)['notes'] if n[0] == ':'], ['0', '6'])
        p = write(self.tmp / 'd.txt', "#TITLE:D\n#BPM:300\nP1\n: 0 2 5 uno\nP2\n: 0 2 9 otra\nE\n")
        self.assertEqual([n[4] for n in UltrastarToSingit.parse_file(p)['notes'] if n[0] == ':'], ['uno'])

    def test_lyric_normalization(self):
        self.assertEqual(UltrastarToSingit.normalize_lyric('¿Por qué? canción ñandú'), '¿Por qué? canción ñandú')
        self.assertEqual(UltrastarToSingit.normalize_lyric('J’ai “bien”…'), 'J\'ai "bien"...')
        self.assertEqual(UltrastarToSingit.normalize_lyric('Zażółć'), 'Zazólc')
        self.assertEqual(UltrastarToSingit.normalize_lyric('canción', keep_accents=False), 'cancion')


class PitchTest(unittest.TestCase):
    @staticmethod
    def song(*pitches, **tags):
        return dict(notes=[[':', '0', '1', str(p), 'a'] for p in pitches], **tags)

    def fast(self, data):
        return PitchAnalyzer.get_pitch_correction_suggestion_fast(data, 43, 81)

    def test_only_whole_octaves(self):
        for pitches in ((0, 5, 12), (20, 30, 40), (80, 85, 95), (-10, 0, 20), (45, 50, 60)):
            self.assertEqual(self.fast(self.song(*pitches)) % 12, 0, pitches)

    def test_expected_shifts(self):
        self.assertEqual(self.fast(self.song(0, 5, 12)), 48)      # usual UltraStar file
        self.assertEqual(self.fast(self.song(45, 50, 60)), 0)     # already in the game's range
        self.assertEqual(self.fast(self.song(80, 85, 95)), -24)   # used to get +48
        self.assertEqual(self.fast(self.song(-10, 0, 20)), 60)

    def test_explicit_offset_and_no_notes(self):
        self.assertEqual(self.fast(self.song(27, 32, LETSSINGPITCHOFFSET='36')), 36)
        self.assertEqual(self.fast({'notes': [['R', '0', '1', '0', 'yo']]}), 0)


class SourcesTest(TempDirTest):
    def test_tagged_sources_and_generated_files_ignored(self):
        d = self.tmp / 'A - B'
        for name in ('song.mp3', 'other.ogg', 'AB.ogg', 'AB_preview.ogg', 'cover.jpg', 'AB.png',
                     'AB_long.png', 'clip.mp4', 'AB_cover.avi', 'AB.avi'):
            write(d / name, 'x')
        txt = {'MP3': 'song.mp3', 'COVER': 'cover.jpg', 'VIDEO': 'clip.mp4'}
        audio, video, cover = ConvertFiles.resolve_song_sources(d, txt, ['AB'])
        self.assertEqual((audio.name, video.name, cover.name), ('song.mp3', 'clip.mp4', 'cover.jpg'))
        audio, video, cover = ConvertFiles.resolve_song_sources(d, {}, ['AB'])
        self.assertNotIn(audio.name, ('AB.ogg', 'AB_preview.ogg'))
        self.assertEqual(video.name, 'clip.mp4')
        self.assertEqual(cover.name, 'cover.jpg')

    def test_choose_txt_prefers_single_player(self):
        d = self.tmp / 'A - B'
        write(d / 'A - B [MULTI].txt', '#TITLE:B\n#BPM:300\n')
        write(d / 'A - B.txt', '#TITLE:B\n#BPM:300\n')
        write(d / 'license.txt', 'not a song')
        self.assertEqual(ConvertFiles.choose_txt_file(list(d.iterdir())).name, 'A - B.txt')


class OutputDirTest(TempDirTest):
    def test_safety_shield(self):
        self.assertEqual(ConvertFiles.safe_output_dir(str(self.tmp)), str(self.tmp))  # empty
        (self.tmp / '0100EE4020D19003').mkdir()
        self.assertEqual(ConvertFiles.safe_output_dir(str(self.tmp)), str(self.tmp))  # only TitleIDs
        write(self.tmp / 'personal.doc', 'x')
        self.assertEqual(ConvertFiles.safe_output_dir(str(self.tmp)), str(self.tmp / '_Patch'))
        # never nests _Patch/_Patch
        patch = self.tmp / '_Patch'
        write(patch / 'error.log', 'x')
        self.assertEqual(ConvertFiles.safe_output_dir(str(patch)), str(patch))


class RegistryTest(TempDirTest):
    def config(self, **dlc_songs):
        base = {'include': False, 'name_txt_path': None, 'songs_json_path': None, 'songs_dlc_tsv_path': None}
        base.update(dlc_songs)
        return munchify({'conversion_tweaks': {'dlc_songs': base}})

    def setUp(self):
        super().setUp()
        ConvertFiles._output_dir = str(self.tmp / 'out')

    def test_year_parsing(self):
        self.assertEqual(ConvertFiles.parse_year({'YEAR': '1985-03'}), 1985)
        self.assertEqual(ConvertFiles.parse_year({'YEAR': ''}), 2000)
        self.assertEqual(ConvertFiles.parse_year({}), 2000)

    def test_json_with_bom_and_threads(self):
        base = write(self.tmp / 'base' / 'songs_int.json',
                     '﻿' + json.dumps({'name': 'int', 'songs': [{'id': 'Original'}]}))
        cfg = self.config(songs_json_path=str(base))
        threads = [threading.Thread(target=ConvertFiles.add_song_to_json,
                                    args=('DLC', 'songs_int.json', {'id': f'S{i}'}, cfg)) for i in range(40)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        data = json.loads((self.tmp / 'out' / 'DLC' / 'romfs' / 'songs_int.json').read_text(encoding='utf-8'))
        ids = [s['id'] for s in data['songs']]
        self.assertEqual(len(ids), 41)
        self.assertEqual(len(set(ids)), 41)
        self.assertIn('Original', ids)

    def test_tsv_unique_uids_with_threads(self):
        cfg = self.config()
        threads = [threading.Thread(target=ConvertFiles.add_data_to_songsdlc_tsv,
                                    args=('CORE', 'Artist', f'S{i}', 'Title', 2000, cfg)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        lines = (self.tmp / 'out' / 'CORE' / 'romfs/Data/StreamingAssets/SongsDLC.tsv').read_text().splitlines()[1:]
        uids = [line.split('\t')[1] for line in lines]
        self.assertEqual(len(uids), 30)
        self.assertEqual(len(set(uids)), 30)
        # converting the same song again keeps a single row
        ConvertFiles.add_data_to_songsdlc_tsv('CORE', 'Artist', 'S0', 'Title', 2001, cfg)
        lines = (self.tmp / 'out' / 'CORE' / 'romfs/Data/StreamingAssets/SongsDLC.tsv').read_text().splitlines()[1:]
        self.assertEqual(len(lines), 30)

    def test_name_txt_no_duplicates(self):
        cfg = self.config()
        for _ in range(3):
            ConvertFiles.add_data_to_name_txt('DLC', 'Song1', ConvertFiles.XML_FORMAT, None, cfg)
        text = (self.tmp / 'out' / 'DLC' / 'romfs' / 'name.txt').read_text()
        self.assertEqual(text.split(), ['Song1'])


class AudioWindowTest(unittest.TestCase):
    @staticmethod
    def txt(start=None, end=None, last_beat=4000, bpm='200', gap='10000'):
        data = {'BPM': bpm, 'GAP': gap, 'notes': [[':', '0', '4', '5', 'a'], [':', str(last_beat), '4', '5', 'b']]}
        if start is not None:
            data['START'] = start
        if end is not None:
            data['END'] = end
        return data  # last note ends at last_beat*60/200/4 + 10 = 310 s

    def test_no_tags(self):
        self.assertEqual(ConvertFiles.audio_window(self.txt(), 320), (0.0, 0.0, None))

    def test_full_audio_is_cut(self):
        # the audio contains the whole song in absolute time: cut it and move the lyrics
        self.assertEqual(ConvertFiles.audio_window(self.txt('58.2', '300000'), 320.0), (58.2, 58.2, 300.0))

    def test_audio_already_cut(self):
        # 'Please Please Please' case: the audio is shorter than the lyrics, it already starts at #START
        self.assertEqual(ConvertFiles.audio_window(self.txt('58.2', '300000'), 250.0), (58.2, 0.0, None))

    def test_lyrics_move_with_offset(self):
        data = {'BPM': '240', 'GAP': '77540', 'notes': [[':', '0', '4', '5', 'Hi'], ['E']], 'lyrics_map_list': []}
        sing_it = UltrastarToSingit.map_data(data, 200.0, 48, 'x.txt', ignore_medley=True, time_offset=58.2)
        self.assertAlmostEqual(sing_it['notes'][0]['t1'], 77.54 - 58.2, places=3)


class LyricSpacesTest(unittest.TestCase):
    def test_words_end_with_a_space_like_official_files(self):
        # 'Side To Side': the space is on the held note "~ "; "night" ends a line; " I've" starts with a space
        notes = [[':', '0', '2', '5', 'side'], [':', '2', '2', '5', '~ '], [':', '4', '2', '5', 'to '],
                 [':', '6', '2', '5', 'night'], ['-', '9'], [':', '10', '2', '5', 'I'], [':', '12', '2', '5', ' am'],
                 ['E']]
        data = {'BPM': '240', 'GAP': '0', 'notes': notes, 'lyrics_map_list': []}
        sing_it = UltrastarToSingit.map_data(data, 200.0, 48, 'x.txt', ignore_medley=True)
        self.assertEqual([t['value'] for t in sing_it['text']], ['side ', 'to ', 'night ', 'I ', 'am'])
        self.assertEqual(''.join(t['value'] for t in sing_it['text']), 'side to night I am')


class PassagesTest(unittest.TestCase):
    @staticmethod
    def note(t1, length, pitch=60):
        return {"t1": t1, "t2": t1 + length, "value": f"#p{pitch}#.la"}

    def test_like_official_files(self):
        notes = [self.note(i * 0.5, 0.4) for i in range(40)]            # normal singing
        notes += [self.note(30 + i * 0.19, 0.18) for i in range(6)]     # quick burst -> speed
        notes += [self.note(40, 1.0), self.note(50, 0.9)]               # long held notes -> long
        notes += [self.note(60 + i * 0.4, 0.35, 1) for i in range(5)]   # normal again
        passages = UltrastarToSingit.build_passages(sorted(notes, key=lambda n: n["t1"]))
        self.assertEqual([p["value"] for p in passages], ["speed", "long", "long"])
        self.assertAlmostEqual(passages[0]["t1"], 30)

    def test_chorus_is_not_one_big_passage(self):
        # the old logic marked every chorus/golden note as "long"
        notes = [{"t1": i * 0.5, "t2": i * 0.5 + 0.4, "value": "#p60#.la#g5"} for i in range(100)]
        self.assertEqual(UltrastarToSingit.build_passages(notes), [])


class OfficialVxlaTest(TempDirTest):
    V2 = """<?xml version="1.0" encoding="ISO-8859-1"?>
<AnnotationFile version="2.0">
  <IntervalLayer datatype="STRING" name="structure"><Interval t1="0.0" t2="5.0" value="couplet1"/><Interval t1="5.0" t2="9.0" value="refrain"/></IntervalLayer>
  <IntervalLayer datatype="STRING" name="lyrics"><Interval t1="1.000" t2="1.400" value="Été "/><Interval t1="1.400" t2="1.900" value="là "/></IntervalLayer>
  <IntervalLayer datatype="STRING" name="lyrics_cut"><Interval t1="1.020" t2="1.380" value="Été "/><Interval t1="1.400" t2="1.880" value="là "/><Interval t1="1.900" t2="2.900" value="-"/></IntervalLayer>
  <IntervalLayer datatype="UINT8" name="notes"><Interval t1="1.020" t2="1.380" value="67"/><Interval t1="1.400" t2="1.880" value="65"/><Interval t1="1.900" t2="2.900" value="65"/></IntervalLayer>
  <IntervalLayer datatype="UINT8" name="notes_golden"><Interval t1="1.400" t2="1.880" value="5"/></IntervalLayer>
  <IntervalLayer datatype="STRING" name="pages"><Interval t1="0.000" t2="3.000" value=""/></IntervalLayer>
</AnnotationFile>
"""

    def test_wrong_encoding_declaration(self):
        import OfficialVxla
        src = write(self.tmp / 'bad.vxla', self.V2.replace('ISO-8859-1', 'utf-16'), 'utf-8')
        layers, version = OfficialVxla.read_layers(src)
        self.assertEqual(version, '2.0')
        self.assertEqual(layers['lyrics_cut'][0][2], 'Été ')

    def test_v2_to_v3_keeps_timing_pitch_and_syllables(self):
        import OfficialVxla
        src = write(self.tmp / 'old.vxla', self.V2, 'latin-1')
        OfficialVxla.convert(src, 'new.vxla', self.tmp, 10.0, UltrastarToSingit.JSON)
        layers, version = OfficialVxla.read_layers(self.tmp / 'new.vxla')
        self.assertEqual(version, '3.0')
        self.assertEqual([v for *_, v in layers['notes_full']], ['#p67#.Été', '#p65#.là#g5', '#p65#.-'])
        self.assertEqual([round(t1, 3) for t1, *_ in layers['notes_full']], [1.02, 1.4, 1.9])
        self.assertEqual([v for *_, v in layers['lyrics']], ['Été ', 'là '])  # '-' is not shown
        self.assertEqual([v for *_, v in layers['segments']], ['feat'])


class VxlaRoundTripTest(TempDirTest):
    def test_extracted_song_keeps_pitch_and_accents(self):
        from tools import LetSing_ExtractorPro as extractor
        song = self.tmp / 'in' / 'Zaz - Je veux'
        notes = ''.join(f": {i * 8} 6 {i % 7} la\n" for i in range(50))
        txt = write(song / 'Zaz - Je veux.txt', "#TITLE:Je veux\n#ARTIST:Zaz\n#BPM:300\n#GAP:0\n"
                    + notes + ": 500 4 5  été\n: 506 4 5  là\nE\n")
        data = UltrastarToSingit.parse_file(txt)
        corr = PitchAnalyzer.get_pitch_correction_suggestion_fast(data, 43, 81)
        UltrastarToSingit.main(txt, 60.0, corr, s='Zjeveux', directory=song)
        vxla = song / 'Zjeveux.vxla'
        content = vxla.read_bytes().decode('utf-8')  # Let's Sing 2024+ files are UTF-8, like the official ones
        self.assertIn('encoding="UTF-8"', content)
        self.assertIn('été', content)

        out = self.tmp / 'extracted' / 'Zaz - Je veux'
        meta = {'artist': 'Zaz', 'title': 'Je veux'}
        self.assertTrue(extractor.convert_vxla_to_txt(str(vxla), 'Zjeveux', meta, str(out), str(self.tmp)))
        back = UltrastarToSingit.parse_file(out / 'Zaz - Je veux.txt')
        back_corr = PitchAnalyzer.get_pitch_correction_suggestion_fast(back, 43, 81)
        original = [int(n[3]) + corr for n in data['notes'] if n[0] == ':']
        restored = [int(n[3]) + back_corr for n in back['notes'] if n[0] in ':F']
        self.assertEqual(original, restored)
        self.assertIn('été', [n[4].strip() for n in back['notes'] if len(n) > 4])


if __name__ == '__main__':
    unittest.main()
