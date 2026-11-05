"""Makes an UltraStar song that USDB does not have (SongMaker): video from YouTube, timed lyrics from LRCLIB, notes
from the singer's voice. The folder is written in the songs folder; convert it like any other song afterwards and
check it in the sync editor.

Usage:
    python tools/make_song.py <songs folder> "<artist>" "<title>" <YouTube link of the video> [--language Spanish]
        [--year 2008] [--genre Pop] [--audio <YouTube link of the official audio>] [--fetch-only]
Needs internet, ffmpeg, yt-dlp and Demucs (requirements-slow.txt); the voice takes a few minutes on CPU.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import SongMaker  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('songs')
    parser.add_argument('artist')
    parser.add_argument('title')
    parser.add_argument('url')
    parser.add_argument('--language', default='Spanish', help="Spanish, English, Korean, ... (#LANGUAGE)")
    parser.add_argument('--year')
    parser.add_argument('--genre')
    parser.add_argument('--fetch-only', action='store_true',
                        help="only download what needs internet (video, audio, lyrics, Genius); make it later offline")
    parser.add_argument('--audio', help="YouTube link of the official audio, when the music video has intros or "
                                        "spoken scenes (the video is then cut to this audio)")
    args = parser.parse_args()
    if args.fetch_only:
        SongMaker.fetch_song(args.artist, args.title, args.url, args.songs, audio_url=args.audio,
                             log=lambda m: print(m, flush=True))
        return
    SongMaker.make_song(args.artist, args.title, args.url, args.songs, language=args.language, year=args.year,
                        genre=args.genre, log=lambda m: print(m, flush=True), audio_url=args.audio)


if __name__ == '__main__':
    main()
