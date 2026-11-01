from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import xml.etree.cElementTree as Et
from pathlib import Path
from xml.dom import minidom

import naming
import OfficialVxla
import PitchAnalyzer
import SupportedFormats
import UltrastarToSingit
import data.repository.DlcRepository as repository
from ConfigLoader import app_dir, load_config, load_default_config

XML_FORMAT = 'xml'
JSON_FORMAT = 'json'

SLOW = "slow"
FAST = "fast"

PITCH_MIN = 43
PITCH_MAX = 81

SONG_DLC_FILE = 'SongsDLC.tsv'
NAME_TXT_FILE = 'name.txt'

MUSIC_GENRE_LIST = ['Pop', 'Rap', 'Rock', 'Ballad', 'Electro']

# Bump whenever the generated vxla changes, so cached vxla files are regenerated (videos are never touched)
VXLA_GENERATOR_VERSION = 6
STILL_BK2_BYTES_PER_S = 20 * 1024  # a .bk2 below this is a still image (a real clip is 100+ KB/s)

# binkc under Wine sometimes "succeeds" with an empty file of a few hundred bytes
MIN_VALID_BK2_BYTES = 16 * 1024

# name.txt, SongsDLC.tsv and songs_xx.json are shared by all songs: one writer at a time
registry_lock = threading.Lock()

logger = logging.getLogger(__name__)


def _setup_error_log() -> None:
    """File handler — always active, captures ERROR+ to error.log next to the program."""
    root = logging.getLogger()
    if any(getattr(h, '_converter_error_log', False) for h in root.handlers):
        return
    try:
        handler = logging.FileHandler(os.path.join(app_dir(), 'error.log'), mode='a', encoding='utf-8')
    except OSError:
        return
    handler._converter_error_log = True
    handler.setLevel(logging.ERROR)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    # third party libraries are far too chatty at DEBUG level
    for noisy in ('urllib3', 'PIL', 'chardet', 'numba', 'requests', 'charset_normalizer'):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_setup_error_log()

_ffmpeg_path = 'ffmpeg'
_ffprobe_path = 'ffprobe'
_rad_path = None
_wine_path = 'wine'
_output_dir = ''
_input_dir = ''

# processes started by the conversion, so Stop can terminate them
_active_processes = set()
_active_processes_lock = threading.Lock()
_stop_event = None


class ConversionStopped(Exception):
    pass


class SongError(Exception):
    """A problem with one song that is reported to the user without a traceback."""


def _check_stop() -> None:
    if _stop_event is not None and _stop_event.is_set():
        raise ConversionStopped()


def _run(cmd, timeout=None, capture=False):
    """subprocess.run that can be cancelled by stop_running_processes()."""
    _check_stop()
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
                            text=capture, encoding='utf-8' if capture else None,
                            errors='replace' if capture else None)
    with _active_processes_lock:
        _active_processes.add(proc)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        logger.error(f"Process timed out after {timeout}s: {os.path.basename(str(cmd[0]))}")
    finally:
        with _active_processes_lock:
            _active_processes.discard(proc)
    _check_stop()
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def stop_running_processes() -> None:
    with _active_processes_lock:
        processes = list(_active_processes)
    for proc in processes:
        try:
            proc.terminate()
        except OSError:
            pass


def _ffmpeg(args, output_path) -> bool:
    """Run ffmpeg writing to a temporary name first: an interrupted run never leaves a
    truncated file that would later be mistaken for a valid cached conversion."""
    output_path = Path(output_path)
    tmp_path = output_path.with_name(output_path.stem + '.tmp' + output_path.suffix)
    result = _run([_ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error'] + list(args) + [os.fspath(tmp_path)],
                  capture=True)
    if result.returncode == 0 and tmp_path.is_file() and tmp_path.stat().st_size > 0:
        os.replace(tmp_path, output_path)
        return True
    if tmp_path.exists():
        tmp_path.unlink()
    error = (result.stderr or '').strip().splitlines()
    logger.error(f"ffmpeg failed creating {output_path.name}: {error[-1] if error else 'exit code ' + str(result.returncode)}")
    return False


def _find_ffprobe(ffmpeg_path: str) -> str:
    folder = Path(ffmpeg_path).parent
    for name in ('ffprobe', 'ffprobe.exe'):
        candidate = folder / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which('ffprobe') or 'ffprobe'


def safe_output_dir(path: str) -> str:
    """The output folder is wiped before converting. If it holds anything other than TitleID folders,
    a _Patch subfolder is used instead so personal files (Desktop, Downloads...) are never deleted."""
    if os.path.basename(os.path.normpath(path)) == '_Patch':
        return path
    if os.path.isdir(path):
        for name in os.listdir(path):
            full_path = os.path.join(path, name)
            if not (os.path.isdir(full_path) and re.fullmatch(r'[0-9A-Fa-f]{16}', name)):
                return os.path.join(path, '_Patch')
    return path


def _init_paths(cfg) -> None:
    """Set module-level tool / folder paths from the resolved config."""
    global _ffmpeg_path, _ffprobe_path, _rad_path, _wine_path, _output_dir, _input_dir

    # ffmpeg / ffprobe
    if cfg.tools.ffmpeg_path:
        _ffmpeg_path = str(cfg.tools.ffmpeg_path)
        _ffprobe_path = _find_ffprobe(_ffmpeg_path)
    else:
        _ffmpeg_path = 'ffmpeg'
        _ffprobe_path = 'ffprobe'

    # RAD Video Tools (through Wine outside Windows)
    _rad_path = str(cfg.tools.rad_path) if cfg.tools.rad_path else None
    _wine_path = str(getattr(cfg.tools, 'wine_path', None) or 'wine')

    # Folders
    _input_dir = str(cfg.folders.input) if cfg.folders.input else os.getcwd()
    _output_dir = str(cfg.folders.output) if cfg.folders.output else os.path.join(os.getcwd(), '_Patch')
    _output_dir = safe_output_dir(_output_dir)


def resolve_config(cfg):
    """Fill in missing values from the DLC database where possible."""
    dlc_id = str(cfg.dlc.id) if cfg.dlc.id else None
    if dlc_id:
        dlc_entity = repository.get_by_dlc_id(dlc_id)
        if dlc_entity:
            cfg.core.id = dlc_entity.core_id
            cfg.dlc.json_name = dlc_entity.dlc_json_name
            cfg.core.edition = dlc_entity.core_edition
    return cfg


def get_output_format(cfg) -> str:
    """JSON_FORMAT when dlc.json_name is set, else XML_FORMAT."""
    return JSON_FORMAT if cfg.dlc.json_name else XML_FORMAT


def _is_blank(value) -> bool:
    return not (value and not str(value).isspace())


# kept for scripts importing them from here
strip_accents = naming.strip_accents
construct_name_id_from_directory_name = naming.construct_name_id_from_directory_name


def find_folders_to_convert():
    input_path = Path(_input_dir)
    dir_to_convert = [x.name for x in input_path.iterdir() if x.is_dir()]
    dir_to_convert = [x for x in dir_to_convert if not x.startswith(('_', '.')) and ' - ' in x]
    return sorted(dir_to_convert, key=str.lower)


def _rescue_unbacked_videos(dirs_to_convert, cfg) -> bool:
    """Before wiping the output folder, make sure every .bk2 in it also exists somewhere else.

    A .bk2 can take hours to encode: copies missing from the song's cache folder are copied back
    there (or to <input>/_rescued_bk2) first. Returns False if anything could not be saved.
    """
    song_dirs = {}
    game_ids = game_ids_for(dirs_to_convert, cfg)
    for dir_name in dirs_to_convert:
        for nid in naming.all_name_ids(dir_name) + [game_ids[dir_name], naming.game_song_id(dir_name.rstrip('.'))]:
            song_dirs.setdefault(nid, Path(_input_dir) / dir_name)

    base_videos = None
    source_json = cfg.conversion_tweaks.dlc_songs.songs_json_path
    if not _is_blank(source_json):
        base_videos = Path(str(source_json)).parent / 'Songs' / 'videos'

    ok = True
    for video in Path(_output_dir).rglob('*' + naming.VIDEO_BK2_SUFFIX):
        size = video.stat().st_size
        song_dir = song_dirs.get(video.stem)
        candidates = []
        if song_dir is not None:
            candidates.append(song_dir / video.name)
            # the cache keeps the cache ID: a patch video named with the game ID is the same file
            candidates += [song_dir / (nid + video.suffix) for nid in naming.all_name_ids(song_dir.name.rstrip('.'))]
        if base_videos is not None:
            candidates.append(base_videos / video.name)
        if any(c.is_file() and c.stat().st_size == size for c in candidates):
            continue

        cache_name = naming.construct_name_id_from_directory_name(song_dir.name.rstrip('.')) + video.suffix \
            if song_dir is not None else video.name
        if song_dir is not None and not (song_dir / cache_name).exists():
            destination = song_dir / cache_name
        else:
            destination = Path(_input_dir) / '_rescued_bk2' / video.name
            if destination.exists():
                destination = destination.with_name(f"{video.stem}_{size}{video.suffix}")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(video, destination)
            logger.warning(f"Saved {video.name} (only copy was in the output folder) to {destination}")
        except OSError as e:
            logger.error(f"Could not save {video} before clearing the output folder: {e}")
            ok = False
    return ok


def delete_output_folder(cfg, dirs_to_convert):
    if getattr(cfg.conversion_tweaks, "clear_output", True) is False:
        logger.info("Skipping output directory deletion (Clear output unchecked).")
        return
    if not os.path.exists(_output_dir):
        return
    if not _rescue_unbacked_videos(dirs_to_convert, cfg):
        logger.error("Output folder NOT cleared: some .bk2 videos could not be saved elsewhere first.")
        return
    try:
        logger.info(f"Removing existing output directory: {_output_dir}")
        shutil.rmtree(_output_dir)
        logger.info("Output directory successfully removed")
    except PermissionError:
        logger.error("Error: Could not delete output folder - permission denied")
    except Exception as e:
        logger.error(f"Error deleting output folder: {e}")


def get_duration(path_to_song):
    result = _run([_ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of',
                   'default=noprint_wrappers=1:nokey=1', os.fspath(path_to_song)], capture=True)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        raise SongError(f"could not read the duration of {os.path.basename(str(path_to_song))} (ffprobe)")


def get_container_format(path) -> str:
    result = _run([_ffprobe_path, '-v', 'error', '-show_entries', 'format=format_name', '-of',
                   'default=noprint_wrappers=1:nokey=1', os.fspath(path)], capture=True)
    return (result.stdout or '').strip()


def is_video_still_image(file):
    duration = get_duration(file)
    if duration <= 0:
        return False
    result = _run([_ffmpeg_path, '-i', os.fspath(file), '-vf', 'freezedetect=n=0.01:d=0.1',
                   '-map', '0:v:0', '-f', 'null', '-'], capture=True)
    stderr = result.stderr or ''

    freeze_starts = [float(m.group(1)) for m in re.finditer(r'freeze_start: ([\d.]+)', stderr)]
    freeze_ends = [float(m.group(1)) for m in re.finditer(r'freeze_end: ([\d.]+)', stderr)]

    if freeze_starts and (len(freeze_ends) < len(freeze_starts)):
        freeze_ends.append(duration)

    # Calculate total freeze duration
    total_freeze = sum(e - s for s, e in zip(freeze_starts, freeze_ends))
    # If freeze covers >95% of the video, treat as still image
    return total_freeze / duration > 0.95


class CleanImage:
    """Cover converted to a plain RGB JPG (no alpha, no broken EXIF) in a temporary file of its own.

    Each song gets its own file: a shared temporary name mixed up covers between threads."""

    def __init__(self, file_path):
        self.source = Path(file_path)
        self.path = self.source
        self._tmp = None

    def __enter__(self):
        try:
            from PIL import Image
            fd, tmp = tempfile.mkstemp(prefix='cover_', suffix='.jpg')
            os.close(fd)
            self._tmp = tmp
            with Image.open(self.source) as img:
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img = img.convert('RGBA')
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert('RGB')
                img.save(tmp, 'JPEG', quality=95)
            self.path = Path(tmp)
        except Exception as e:
            logger.warning(f"Could not convert cover to safe JPG: {e}")
            self.path = self.source
        return self.path

    def __exit__(self, *exc):
        if self._tmp and os.path.exists(self._tmp):
            os.remove(self._tmp)
        return False


def create_still_video_from_cover_image(cover_file, list_in_dir, output_file_name, song_duration):
    logger.info('creating static video: ' + output_file_name)
    if cover_file is None:
        raise SongError("no cover image to build a static video from")
    if song_duration <= 0:
        raise SongError("audio duration is 0, cannot build a static video")
    target_size_mb = 10
    target_bitrate_kbps = int((target_size_mb * 8192) / song_duration)
    complex_filter = (
        "split[bg][fg];"
        "[bg]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,gblur=sigma=10[bg_blurred];"
        "[fg]scale='if(gt(iw/ih,1280/720),min(iw,1280),-1)':'if(gt(iw/ih,1280/720),-1,min(ih,720))':force_original_aspect_ratio=decrease[fg_scaled];"
        "[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2,fps=25"
    )
    with CleanImage(cover_file) as image:
        return _ffmpeg(['-loop', '1', '-i', os.fspath(image), '-c:v', 'libx264', '-t', str(song_duration),
                        '-preset', 'medium', '-tune', 'stillimage', '-b:v', f'{target_bitrate_kbps}k',
                        '-vf', complex_filter, '-pix_fmt', 'yuv420p', '-an'],
                       list_in_dir / output_file_name)


def _create_image(source, list_in_dir, file_name, width, height, from_video=False):
    scale = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}'
    if from_video:
        for seek in ('15', '0'):
            if _ffmpeg(['-ss', seek, '-i', os.fspath(source), '-vframes', '1', '-vf', scale], list_in_dir / file_name):
                logger.info('created from video: ' + file_name)
                return True
        return False
    with CleanImage(source) as image:
        created = _ffmpeg(['-i', os.fspath(image), '-vf', scale], list_in_dir / file_name)
    if created:
        logger.info('created : ' + file_name)
    return created


def create_placeholder_cover(list_in_dir, file_name, artist, title):
    """Cover for songs that have no image at all (and a video ffmpeg can't read, like .bk2)."""
    from PIL import Image, ImageDraw, ImageFont
    size = 512
    img = Image.new('RGB', (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        shade = int(40 + 60 * y / size)
        draw.line([(0, y), (size, y)], fill=(shade // 2, shade // 3, shade))
    try:
        font_big = ImageFont.load_default(size=44)
        font_small = ImageFont.load_default(size=30)
    except TypeError:  # Pillow < 10.1
        font_big = font_small = ImageFont.load_default()

    def wrap(text, font, width):
        lines, line = [], ''
        for word in text.split():
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=font) <= width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        return lines + ([line] if line else [])

    y = 150
    for line in wrap(title, font_big, size - 60)[:4]:
        draw.text((size / 2, y), line, font=font_big, fill=(255, 255, 255), anchor='mm')
        y += 54
    y += 20
    for line in wrap(artist, font_small, size - 60)[:3]:
        draw.text((size / 2, y), line, font=font_small, fill=(210, 210, 230), anchor='mm')
        y += 38
    img.save(list_in_dir / file_name, 'PNG')
    logger.warning(f"No cover image found, created a placeholder cover: {file_name}")
    return list_in_dir / file_name


def _image_is_current(path, width, height, source):
    """The cached image exists, has the size the game expects and is newer than its source image."""
    if not _image_has_size(path, width, height):
        return False
    try:
        if source is not None and os.path.getmtime(source) > os.path.getmtime(path):
            logger.info(f"{path.name}: its source image changed, rebuilding it")
            return False
    except OSError:
        pass
    return True


def _image_has_size(path, width, height):
    """True if the image exists and has the size the game expects."""
    if not path.exists():
        return False
    try:
        from PIL import Image
        with Image.open(path) as img:
            if img.size == (width, height):
                return True
        logger.info(f"{path.name} is {img.size[0]}x{img.size[1]}, the game uses {width}x{height}: rebuilding it")
        return False
    except Exception:
        return False


def create_cover(cover_file, list_in_dir, png_file_name, from_video=False):
    return _create_image(cover_file, list_in_dir, png_file_name, 256, 256, from_video)


def create_cover_long(cover_file, list_in_dir, png_long_file_name, from_video=False):
    return _create_image(cover_file, list_in_dir, png_long_file_name, 191, 396, from_video)


def create_in_game_loading_picture(cover_file, list_in_dir, png_in_game_file_name, from_video=False):
    return _create_image(cover_file, list_in_dir, png_in_game_file_name, 512, 512, from_video)


def create_audio_preview(audio_file, list_in_dir, ogg_preview_file_name, txt_data, time_offset=0.0):
    """time_offset: seconds the txt timing is ahead of audio_file (see audio_window)."""
    preview_start_time = 60
    preview_duration_time = 30
    try:
        if 'MEDLEYSTARTBEAT' in txt_data and 'MEDLEYENDBEAT' in txt_data:
            preview_start_beat = int(txt_data['MEDLEYSTARTBEAT'])
            preview_end_beat = int(txt_data['MEDLEYENDBEAT'])
            bpm = float(txt_data["BPM"].replace(',', '.'))
            gap = float(txt_data.get("GAP", "0").replace(',', '.') or 0) / 1000
            preview_start_time = (preview_start_beat * 60 / bpm / 4) + gap
            preview_duration_time = ((preview_end_beat - preview_start_beat) * 60 / bpm / 4)
        elif 'PREVIEWSTART' in txt_data:
            preview_start_time = float(txt_data['PREVIEWSTART'].replace(',', '.'))
    except (ValueError, ZeroDivisionError):
        logger.warning("Invalid medley/preview tags, using the default preview position")
    if preview_duration_time <= 0:
        preview_duration_time = 30
    if 'MEDLEYSTARTBEAT' in txt_data or 'PREVIEWSTART' in txt_data:
        preview_start_time = max(0.0, preview_start_time - time_offset)

    # prevent preview from exceeding actual song duration
    try:
        total_duration = get_duration(audio_file)
        if preview_start_time + preview_duration_time > total_duration:
            preview_start_time = max(0.0, total_duration - preview_duration_time)
            if preview_start_time == 0.0:
                preview_duration_time = total_duration
    except SongError as e:
        logger.warning(f"Could not verify duration for preview: {e}")

    created = _ffmpeg(['-ss', str(preview_start_time), '-i', os.fspath(audio_file), '-vn',
                       '-t', str(preview_duration_time), '-ar', '48000', '-af', 'dynaudnorm,volume=-2.5dB'],
                      list_in_dir / ogg_preview_file_name)
    if created:
        logger.info('created : ' + ogg_preview_file_name)
    return created


def create_audio(audio_file, list_in_dir, ogg_file_name, video_gap, trim_start=0.0, trim_end=None):
    filter_cmd = ''
    if trim_start > 0 or trim_end:
        # #START / #END of the txt: play only that part of the audio
        window = f'start={trim_start}' + (f':end={trim_end}' if trim_end else '')
        filter_cmd = f'atrim={window},asetpts=PTS-STARTPTS,'
    if video_gap < 0:
        # Negative gap: trim the beginning of the audio
        # Remove the first |video_gap| seconds
        filter_cmd += f'atrim=start={abs(video_gap)},asetpts=PTS-STARTPTS,'
    elif video_gap > 0:
        # Positive gap: add silence to the beginning
        # Insert video_gap seconds of silence before the audio
        filter_cmd += f'adelay={int(video_gap * 1000)}|{int(video_gap * 1000)},'

    # Dynamic normalizer that preserves sync + volume reduction
    filter_cmd += 'dynaudnorm,volume=-2.5dB'

    created = _ffmpeg(['-i', os.fspath(audio_file), '-vn', '-ar', '48000', '-af', filter_cmd],
                      list_in_dir / ogg_file_name)
    if created:
        logger.info('created : ' + ogg_file_name)
    return created


def create_video(file, list_in_dir, output_video_file_name, target_bitrate_kbps, trim_start=0.0):
    seek = ['-ss', str(trim_start)] if trim_start > 0 else []
    passlog_prefix = os.fspath(list_in_dir / (output_video_file_name + "_passlog"))
    video_filter = 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=25'
    try:
        # First pass to analyze video
        _run([_ffmpeg_path, '-y'] + seek + ['-i', os.fspath(file),
              '-c:v', 'libx264', '-preset', 'medium', '-bf', '0', '-b:v', f'{target_bitrate_kbps}k',
              '-pass', '1', '-passlogfile', passlog_prefix, '-an', '-vf', video_filter,
              '-f', 'null', os.devnull])
        # Second pass to create final file
        created = _ffmpeg(seek + ['-i', os.fspath(file), '-c:v', 'libx264', '-preset', 'medium', '-bf', '0',
                           '-b:v', f'{target_bitrate_kbps}k', '-pass', '2', '-passlogfile', passlog_prefix,
                           '-an', '-vf', video_filter],
                          list_in_dir / output_video_file_name)
    finally:
        # Clean up FFmpeg passlog files
        for log_file in list_in_dir.glob(output_video_file_name + "_passlog*"):
            os.remove(log_file)
    if created:
        logger.info('created : ' + output_video_file_name)
    return created


def _big_temp_dir():
    """Folder for the temporary copies of whole videos: on disk, not /tmp, which is often in RAM on Linux."""
    if sys.platform == 'win32':
        return None
    path = os.path.join(os.path.expanduser('~'), '.cache', 'letssing_converter')
    os.makedirs(path, exist_ok=True)
    return path


def create_video_bink(file, list_in_dir, output_video_file_name, quality=None, duration=None,
                      compression_percentage=None):
    """Encode a .bk2 with RAD Video Tools. The result is written to the song folder only when binkc
    produced a valid file, an existing .bk2 is never replaced by a failed encode."""
    if not _rad_path:
        logger.error("RAD Video Tools path not configured - cannot create .bk2 video")
        return False

    file_format = '/V' + str(200)
    remove_sound = '/L-1'
    # generous timeout: a hung binkc must not block a worker thread forever
    timeout = max(1800, int((duration or 300) * 30))

    with tempfile.TemporaryDirectory(dir=_big_temp_dir()) as temp_dir:  # one folder per encode (parallel workers)
        temp_dir_path = Path(temp_dir)
        temp_in = temp_dir_path / ("input" + Path(file).suffix.lower())
        temp_out = temp_dir_path / "output.bk2"

        # Copy input to safe temp location (binkc chokes on special characters in paths)
        shutil.copy2(file, temp_in)

        bink_in = str(temp_in)
        bink_out = str(temp_out)

        if sys.platform != "win32":
            bink_in = "Z:" + bink_in.replace("/", "\\")
            bink_out = "Z:" + bink_out.replace("/", "\\")
            bink_args = [_wine_path, _rad_path, 'binkc', bink_in, bink_out, file_format,
                         '/(1280', '/)720', remove_sound]
        else:
            bink_args = [_rad_path, 'binkc', bink_in, bink_out, file_format,
                         '/(1280', '/)720', remove_sound]

        if compression_percentage:
            # data rate as a percentage of the input (from the original converter): keeps "Max video size"
            bink_args.append('/D' + str(compression_percentage))
        if quality:
            bink_args.append('/Q' + str(quality))
        bink_args.append('/#')

        logger.info(f"Converting video {os.path.basename(str(file))} to {output_video_file_name} with binkc...")
        result = _run(bink_args, timeout=timeout, capture=True)

        final_out = list_in_dir / output_video_file_name
        size = temp_out.stat().st_size if temp_out.exists() else 0
        if size >= MIN_VALID_BK2_BYTES:
            shutil.copy2(temp_out, final_out)
            logger.info(f"Successfully created {output_video_file_name}")
            return True

        details = ' | '.join(line.strip() for line in ((result.stdout or '') + (result.stderr or '')).splitlines()
                             if line.strip())[-500:]
        logger.error(f"Failed to generate {output_video_file_name} from binkc "
                     f"(exit code {result.returncode}, {size} bytes){': ' + details if details else ''}")
        return False


# Genres of Let's Sing 2026 (GameSong.Genre in the game code) and the #GENRE words that lead to them, checked in
# this order ("Hip-Hop, Rap" -> HipHop, "Contemporary R&B, Pop" -> RnB, "Electro Pop" -> Electro)
GENRES_2026 = (
    ('HipHop', ('hip-hop', 'hip hop', 'hiphop', 'rap', 'trap', 'urban', 'glitch hop', 'electro hop')),
    ('RnB', ('r&b', 'rnb', 'soul')),
    ('Latin', ('reggaeton', 'reguetón', 'reggaetón', 'latin', 'bachata', 'vallenato', 'salsa', 'cumbia', 'mambo',
               'flamenco', 'merengue', 'dembow')),
    ('Country', ('country',)),
    ('Rock', ('rock', 'alternative', 'punk', 'metal', 'grunge')),
    ('Electro', ('electro', 'electronic', 'dance', 'house', 'edm', 'techno', 'trance', 'disco', 'synth')),
    ('Ballad', ('ballad', 'balada')),
    ('Pop', ('pop',)),
)


def match_genre(txt_data, edition=None):
    genre_raw = txt_data.get('GENRE', '').lower()
    if str(edition) in GAME_ID_EDITIONS:
        for genre, words in GENRES_2026:
            if any(w in genre_raw for w in words):
                return genre
        return 'Pop'
    for g in MUSIC_GENRE_LIST:
        if g.lower() in genre_raw:
            return g
    return 'Pop'


def parse_year(txt_data) -> int:
    match = re.search(r'(\d{4})', str(txt_data.get('YEAR', '')))
    return int(match.group(1)) if match else 2000


# Languages of songs_xx.json: the KaraokeLanguage.Languages of Let's Sing 2026 (read from the game code). A song in
# any other known language (Japanese, Italian...) is "Other", like the game groups them; no language found: English.
# Only the editions below get the real language (their official files use it); every other edition keeps "English",
# as it always had, so patches for older games do not change.
REAL_LANGUAGE_EDITIONS = ('2026',)
# Editions whose "Title" list is sorted by the song ID: the patch uses naming.game_song_id (title first) there.
GAME_ID_EDITIONS = ('2026',)


# Difficulty and singer of a song (Let's Sing 2026 filters by them; before every song said "VeryEasy" and "Both").
# Difficulty: fitted on the 59 official songs whose real values are known (2024/2026 DLCs), within one level for 53 of
# 59 in cross-validation; its features do not depend on the octave of the notes. Singer: from
# <songs>/_artist_genders.json (tools/artist_genders.py, MusicBrainz); pitch was not enough (Queen sings as high as
# many women), and a wrong value would hide the song from a filter, so anything unsure stays "Both".
DIFFICULTY_LEVELS = ('VeryEasy', 'Easy', 'Medium', 'Hard', 'VeryHard')
DIFFICULTY_WEIGHTS = (0.05301, 0.48165, -6.62458, 0.99983, -2.04069, -0.21842)  # range, notes/s, note s, jump, rap, 1
ARTIST_GENDERS_FILE = '_artist_genders.json'
_artist_genders = {}


GENDER_PITCH_MEN_MAX, GENDER_PITCH_WOMEN_MIN = 63.0, 59.0  # sung median pitch (MIDI) that contradicts a gender


def singer_gender(artist, title='', median_pitch=None):
    """Men / Women / Both from _artist_genders.json: the artist and the singers featured in the title must agree,
    and the pitch of the voice must not contradict it (a DJ credited alone while a woman sings); else Both."""
    if not _artist_genders and _input_dir:
        try:
            with open(os.path.join(_input_dir, ARTIST_GENDERS_FILE), encoding='utf-8') as f:
                _artist_genders.update(json.load(f))
        except (OSError, ValueError):
            _artist_genders[''] = 'Both'  # no file: do not try again
    names = [artist.strip()]
    m = re.search(r'[(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+([^)\]]+)[)\]]', title or '', re.I)
    if m:
        names += [p.strip() for p in re.split(r'\s*(?:,|&|\+| and | x )\s*', m.group(1)) if p.strip()]
    genders = {_artist_genders.get(n) for n in names}
    if len(genders) != 1 or not genders <= {'Men', 'Women'}:
        return 'Both'
    gender = genders.pop()
    if median_pitch is not None and ((gender == 'Men' and median_pitch > GENDER_PITCH_MEN_MAX) or
                                     (gender == 'Women' and median_pitch < GENDER_PITCH_WOMEN_MIN)):
        return 'Both'
    return gender


def sung_median_pitch(vxla_path, voice_path, official):
    """Median sung pitch (MIDI): the official notes, or the analyzed voice (the octave of UltraStar notes is not
    reliable). None when unknown."""
    import numpy as np
    try:
        if official:
            layers, _ = OfficialVxla.read_layers(vxla_path)
            pitches = [int(re.match(r'#p(\d+)', n['value']).group(1))
                       for n in OfficialVxla.to_sing_it(layers, 3600.0)['notes']]
            pitches = [p for p in pitches if p > 1]
            return float(np.median(pitches)) if pitches else None
        if voice_path and os.path.isfile(voice_path):
            voice = np.load(voice_path)['pitch'].astype(float)
            voice = voice[~np.isnan(voice)]
            return float(np.median(voice)) if len(voice) > 500 else None
    except Exception:
        return None
    return None


def song_difficulty(vxla_path):
    """Difficulty for songs_xx.json from the notes of the converted vxla."""
    import numpy as np
    try:
        layers, _ = OfficialVxla.read_layers(vxla_path)
        notes = OfficialVxla.to_sing_it(layers, 3600.0)['notes']
        pitches = [int(re.match(r'#p(\d+)', n['value']).group(1)) for n in notes]
        sung = [(n['t1'], n['t2'], q) for n, q in zip(notes, pitches) if q > 1]
        if len(sung) < 10:
            return 'Medium'
        values = np.array([q for _, _, q in sung], dtype=float)
        span = max(notes[-1]['t2'] - notes[0]['t1'], 1.0)
        features = (float(np.percentile(values, 95) - np.percentile(values, 5)), len(notes) / span,
                    float(np.median([b - a for a, b, _ in sung])), float(np.mean(np.abs(np.diff(values)))),
                    (len(pitches) - len(sung)) / len(pitches), 1.0)
        level = int(round(sum(w * f for w, f in zip(DIFFICULTY_WEIGHTS, features))))
        return DIFFICULTY_LEVELS[min(max(level, 0), len(DIFFICULTY_LEVELS) - 1)]
    except Exception as e:
        logger.warning(f"{os.path.basename(str(vxla_path))}: difficulty not estimated ({e})")
        return 'Medium'


def uses_game_ids(cfg) -> bool:
    return str(getattr(getattr(cfg, 'core', None), 'edition', '')) in GAME_ID_EDITIONS


def game_ids_for(dir_names, cfg) -> dict:
    """{folder: ID used inside the patch}. The cache ID for older editions; for GAME_ID_EDITIONS the title-first
    game ID, made unique with a number when two folders give the same one (stable: sorted by folder name)."""
    if not uses_game_ids(cfg):
        return {d: naming.construct_name_id_from_directory_name(d.rstrip('.')) for d in dir_names}
    result, used = {}, set()
    for d in sorted(dir_names, key=str.lower):
        base = naming.game_song_id(d.rstrip('.'))
        game_id, n = base, 2
        while game_id.lower() in used:
            game_id, n = f"{base}{n}", n + 1
        used.add(game_id.lower())
        result[d] = game_id
    return result
GAME_LANGUAGES = ('English', 'French', 'Spanish', 'German', 'Korean')
GAME_LANGUAGE_OTHER = 'Other'
GAME_LANGUAGE_FALLBACK = 'English'
_LANGUAGE_ALIASES = {
    'english': 'English', 'ingles': 'English', 'inglés': 'English', 'anglais': 'English', 'englisch': 'English',
    'spanish': 'Spanish', 'espanol': 'Spanish', 'español': 'Spanish', 'castellano': 'Spanish', 'espagnol': 'Spanish',
    'spanisch': 'Spanish',
    'french': 'French', 'francais': 'French', 'français': 'French', 'frances': 'French', 'francés': 'French',
    'franzosisch': 'French', 'französisch': 'French',
    'german': 'German', 'deutsch': 'German', 'aleman': 'German', 'alemán': 'German', 'allemand': 'German',
    'italian': 'Italian', 'italiano': 'Italian', 'italien': 'Italian', 'italienisch': 'Italian',
    'portuguese': 'Portuguese', 'portugues': 'Portuguese', 'português': 'Portuguese', 'portugués': 'Portuguese',
    'dutch': 'Dutch', 'nederlands': 'Dutch', 'holandes': 'Dutch', 'holandés': 'Dutch', 'flemish': 'Dutch',
    'korean': 'Korean', 'japanese': 'Japanese', 'russian': 'Russian', 'polish': 'Polish', 'swedish': 'Swedish',
    'turkish': 'Turkish', 'greek': 'Greek', 'chinese': 'Chinese', 'catalan': 'Catalan', 'latin': 'Latin',
    'romanian': 'Romanian', 'coreano': 'Korean', 'japones': 'Japanese', 'japonés': 'Japanese',
}
# frequent short words of each language, to tell the language of lyrics without a #LANGUAGE tag
_STOPWORDS = {
    'English': set("the and you i me my to a it is in that of your we be don't i'm on for all love what this "
                   "with so but just know oh baby can no like get".split()),
    'Spanish': set("que de la el y en no me te mi tu yo lo se por un una es con para pero como más mas amor "
                   "quiero qué cuando esta está todo".split()),
    'French': set("je tu il et le la les de des que qui pas ne un une est mon ma mes moi toi c'est j'ai "
                  "dans pour sur avec plus vous nous".split()),
    'German': set("ich du und der die das nicht ist ein eine mich dich mein dein wir es zu mit auf sie "
                  "wie so noch auch".split()),
    'Italian': set("che di il la e non io tu mi ti un una per con sei sono come ma più amore della".split()),
    'Portuguese': set("que de não eu você o a e um uma meu minha com para em do da te amor é tão".split()),
    'Dutch': set("ik je de het een en niet is van dat mijn jij wij zijn op met maar".split()),
}


def detect_language(words):
    """Most likely language of a list of lyric words (by their most frequent short words), or None."""
    words = [w.lower().strip(".,!?¡¿\"()") for w in words if w.strip()]
    if len(words) < 20:
        return None
    scores = {lang: sum(1 for w in words if w in stop) for lang, stop in _STOPWORDS.items()}
    best = max(scores, key=scores.get)
    second = sorted(scores.values())[-2]
    # a clear winner only: songs mixing languages keep the first one of their tag or the fallback
    return best if scores[best] >= 8 and scores[best] >= 1.5 * max(second, 1) else None


def song_language(txt_data, song_dir=None):
    """Language for the game: the first one of #LANGUAGE ("Korean (romanized), English" -> Korean), else the
    one of the lyrics (those of the official vxla when there is one: rebuilt txt files lost their spaces).
    Known languages the game does not list become "Other"; no language found: English."""
    tag = txt_data.get('LANGUAGE', '').strip()
    language = None
    if tag:
        first = re.split(r'[,;/&+]| and | y ', tag)[0]
        first = re.sub(r'\(.*?\)', '', first).strip().lower()
        language = _LANGUAGE_ALIASES.get(first)
    if language is None:
        text = ''
        official = os.path.join(song_dir, naming.OFFICIAL_VXLA_NAME) if song_dir else None
        if official and os.path.isfile(official):
            try:
                layers, _ = OfficialVxla.read_layers(official)
                text = ''.join(v for _, _, v in layers.get('lyrics', []))
            except Exception:
                text = ''
        if not text:
            text = ''.join(n[4] for n in txt_data.get('notes', [])
                           if len(n) > 4 and n[0] in (':', '*', 'F', 'R', 'G'))
        language = detect_language(text.replace('~', '').split())
    if language is None:
        return GAME_LANGUAGE_FALLBACK
    return language if language in GAME_LANGUAGES else GAME_LANGUAGE_OTHER


def build_song_metadata(txt_data, edition=None):
    title = txt_data.get('TITLE', 'title')
    artist = txt_data.get('ARTIST', 'artist')
    try:
        bpm = int(float(txt_data.get('BPM', '120').replace(',', '.')))
    except ValueError:
        bpm = 120
    return title, artist, parse_year(txt_data), match_genre(txt_data, edition), bpm


def _remove_old_patch_copies(songs_dir, old_ids, song_dir, current_ids):
    """Copies of a song left in the patch under its cache ID after the patch moved to game IDs. Only copies are
    removed, never a file named with the game ID of any song, and a video only when the song folder has the same
    file (the cache is never touched)."""
    places = (('audio', naming.AUDIO_SUFFIX), ('audio_preview', naming.AUDIO_PREVIEW_SUFFIX),
              ('covers', naming.COVER_SUFFIX), ('vxla', naming.VXLA_SUFFIX),
              ('videos', naming.VIDEO_BK2_SUFFIX), ('videos', naming.VIDEO_MP4_SUFFIX))
    for old_id in old_ids:
        if old_id.lower() in current_ids:
            continue
        for sub, suffix in places:
            path = os.path.join(songs_dir, sub, old_id + suffix)
            if not os.path.isfile(path):
                continue
            if suffix in (naming.VIDEO_BK2_SUFFIX, naming.VIDEO_MP4_SUFFIX):
                cached = Path(song_dir) / (old_id + suffix)
                if not (cached.is_file() and cached.stat().st_size == os.path.getsize(path)):
                    logger.warning(f"Kept {path}: no identical copy in the song folder")
                    continue
            try:
                os.remove(path)
            except OSError as e:
                logger.warning(f"Could not remove the old copy {path}: {e}")


def handle_xml_or_json(dlc_id, core_id, json_file_name, list_in_dir, txt_data,
                       name_id, output_format, xml_file_name, cfg, old_ids=(), profile=None):
    """Creates <id>_meta.xml (XML games); registers the song in SongsDLC.tsv or songs_xx.json."""
    title, artist, year, genre, bpm = build_song_metadata(
        txt_data, getattr(getattr(cfg, 'core', None), 'edition', None))

    if output_format == XML_FORMAT:
        uid = add_data_to_songsdlc_tsv(core_id, artist, name_id, title, year, cfg)
        create_meta_xml(uid, artist, genre, list_in_dir, name_id, title, xml_file_name, year)
    elif output_format == JSON_FORMAT:
        song_data = {
            "id": name_id,
            "artist": artist,
            "title": title,
            "gender": profile[1] if profile else "Both",
            "year": year,
            "timeless": "",
            "genre": genre,
            "theme": "Love, Deep, Party",
            "difficulty": profile[0] if profile else "VeryEasy",
            "coopfriendly": "Coop",
            "language": song_language(txt_data, os.fspath(list_in_dir))
            if str(getattr(getattr(cfg, 'core', None), 'edition', '')) in REAL_LANGUAGE_EDITIONS
            else GAME_LANGUAGE_FALLBACK,
            "bpm": bpm
        }
        add_song_to_json(dlc_id, json_file_name, song_data, cfg, old_ids)


def create_meta_xml(uid, artist, genre, list_in_dir, name_id, title, xml_file_name, year):
    root = Et.Element("DLCSong")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    Et.SubElement(root, "Genre").text = genre
    Et.SubElement(root, "Id").text = name_id
    Et.SubElement(root, "Uid").text = str(uid)
    Et.SubElement(root, "Artist").text = artist
    Et.SubElement(root, "Title").text = title
    Et.SubElement(root, "Year").text = str(year)
    Et.SubElement(root, "Ratio").text = "Ratio_16_9"
    Et.SubElement(root, "Difficulty").text = "Difficulty0"
    Et.SubElement(root, "Feat")
    Et.SubElement(root, "Line1").text = artist
    Et.SubElement(root, "Line2")
    xmlstr = minidom.parseString(Et.tostring(root)).toprettyxml(
        encoding="utf-8", indent="   ").decode('utf-8')
    xmlbin = xmlstr.replace('\n', '\r\n').encode('utf-8-sig')
    with open(os.fspath(list_in_dir / xml_file_name), "wb") as f:
        f.write(xmlbin)


def _atomic_write_text(path, text, encoding='utf-8'):
    """Write to a temporary file and rename it over the target: a crash never leaves half a file."""
    tmp = str(path) + '.tmp'
    with open(tmp, 'w', encoding=encoding, newline='') as f:
        f.write(text)
    os.replace(tmp, path)


def _read_text(path):
    """Text of a file plus the encoding to write it back with (a BOM is kept only if it had one)."""
    with open(path, 'rb') as f:
        raw = f.read()
    encoding = UltrastarToSingit._detect_encoding_bytes(raw)
    if encoding == 'utf-8-sig' and not raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8'
    return raw.decode(encoding), encoding


def add_song_to_json(dlc_id, json_file_name, song_data, cfg, old_ids=()):
    with registry_lock:
        source_json = str(cfg.conversion_tweaks.dlc_songs.songs_json_path) if not _is_blank(cfg.conversion_tweaks.dlc_songs.songs_json_path) else None

        dlc_romfs_dir = os.path.join(_output_dir, dlc_id, 'romfs')
        os.makedirs(dlc_romfs_dir, exist_ok=True)
        dest_json_file = os.path.join(dlc_romfs_dir, json_file_name)

        # the base JSON is merged even when the "copy DLC media" checkbox is off
        read_from = dest_json_file if os.path.exists(dest_json_file) else (
            source_json if source_json and os.path.exists(source_json) else None)
        if read_from:
            try:
                data = json.loads(_read_text(read_from)[0])
            except json.JSONDecodeError as e:
                raise SongError(f"{os.path.basename(read_from)} is not valid JSON ({e}); "
                                f"fix or delete it before converting")
        else:
            data = {"name": json_file_name.split('_')[1].split('.')[0], "songs": []}

        # Remove any existing song with the same ID to replace it (and the entry it had under an older ID)
        drop = {str(song_data.get('id'))} | {str(i) for i in old_ids}
        data['songs'] = [s for s in data.get('songs', []) if str(s.get('id')) not in drop]
        data['songs'].append(song_data)
        _atomic_write_text(dest_json_file, json.dumps(data, ensure_ascii=False, indent=4))


TSV_HEADER = ("ENABLED\tUID\tID\tARTIST\tTITLE\tYEAR\tDIFFICULTY\tSKU_INT\tSKU_FR\tSKU_SPA\tSKU_GER"
              "\tDLC_INDEX\tVIDEO_RATIO\tGENRE_POP_UNLOCKED\tGENRE_RAP\tGENRE_BALLAD\tGENRE_ROCK"
              "\tGENRE_HAPPY_UNLOCKED\tGENRE_FIESTA\tGENRE_LOVE\tGENRE_SAD\tGENRE_OLD_UNLOCKED"
              "\tGENRE_2000\tGENRE_RECENT\tGENRE_RANDOM_UNLOCKED"
              "\tGENRE_VO\tGENRE_WOMEN\tGENRE_ENGLISH\tGENRE_MEN\n")


def add_data_to_songsdlc_tsv(core_id, artist, name_id, title, year, cfg):
    with registry_lock:
        core_assets_dir = os.path.join(_output_dir, core_id, 'romfs/Data/StreamingAssets')
        os.makedirs(core_assets_dir, exist_ok=True)
        dest_songs_dlc = os.path.join(core_assets_dir, SONG_DLC_FILE)

        if not os.path.exists(dest_songs_dlc):
            source_tsv = str(cfg.conversion_tweaks.dlc_songs.songs_dlc_tsv_path) if not _is_blank(
                cfg.conversion_tweaks.dlc_songs.songs_dlc_tsv_path) else None
            if source_tsv and os.path.exists(source_tsv):
                shutil.copy2(source_tsv, dest_songs_dlc)
            else:
                _atomic_write_text(dest_songs_dlc, TSV_HEADER)

        text, encoding = _read_text(dest_songs_dlc)
        reader = csv.DictReader(io.StringIO(text), delimiter='\t')
        columns = list(reader.fieldnames)
        rows = list(reader)

        existing = next((r for r in rows if r.get('ID') == name_id), None)
        if existing is not None:
            # converting the same song again: update its row, keep its UID
            new_row = existing
            uid = int(existing['UID'])
        elif not rows:
            uid = 200
            new_row = {col: '' for col in columns}  # fill all columns with ''
            new_row['DIFFICULTY'] = '0'
            new_row['SKU_INT'] = 'x'
            new_row['SKU_FR'] = 'x'
            new_row['SKU_SPA'] = 'x'
            new_row['SKU_GER'] = 'x'
            new_row['DLC_INDEX'] = '1'
            new_row['VIDEO_RATIO'] = 'RATIO_16_9'
            new_row['GENRE_RANDOM_UNLOCKED'] = 'x'
            new_row['GENRE_ENGLISH'] = 'x'
            rows.append(new_row)
        else:
            uids = [int(r['UID']) for r in rows if str(r.get('UID', '')).strip().isdigit()]
            highest_uid = max(uids, default=0)
            uid = 200 if highest_uid < 200 else highest_uid + 1
            new_row = dict(rows[-1])
            rows.append(new_row)

        new_row['ENABLED'] = 'x'
        new_row['UID'] = str(uid)
        new_row['ID'] = name_id
        new_row['ARTIST'] = artist
        new_row['TITLE'] = title
        new_row['YEAR'] = str(year)

        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=columns, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        _atomic_write_text(dest_songs_dlc, out.getvalue(), encoding)
        return uid


def add_data_to_name_txt(dlc_id, name_id, output_format, dlc_json_name, cfg):
    with registry_lock:
        source_name_txt = str(cfg.conversion_tweaks.dlc_songs.name_txt_path) if not _is_blank(cfg.conversion_tweaks.dlc_songs.name_txt_path) else None

        dlc_romfs_dir = os.path.join(_output_dir, dlc_id, 'romfs')
        os.makedirs(dlc_romfs_dir, exist_ok=True)
        dest_name_txt = os.path.join(dlc_romfs_dir, NAME_TXT_FILE)

        if not os.path.exists(dest_name_txt):
            if source_name_txt and os.path.exists(source_name_txt):
                shutil.copy2(source_name_txt, dest_name_txt)
            elif output_format == XML_FORMAT:
                _atomic_write_text(dest_name_txt, '')
            elif output_format == JSON_FORMAT:
                _atomic_write_text(dest_name_txt, dlc_json_name + '\n')
        # Append song ID for XML format (once)
        if output_format == XML_FORMAT:
            text, encoding = _read_text(dest_name_txt)
            lines = text.splitlines()
            if name_id not in (line.strip() for line in lines):
                lines.append(name_id)
                _atomic_write_text(dest_name_txt, '\n'.join(lines) + '\n', encoding)


def last_note_time(txt_data):
    """Absolute end time (seconds, from the start of the txt's audio) of the last sung note."""
    try:
        bpm = float(txt_data['BPM'].replace(',', '.'))
        gap = float((txt_data.get('GAP') or '0').replace(',', '.')) / 1000
    except (KeyError, ValueError):
        return None
    notes = [n for n in txt_data['notes'] if n and n[0] in ':*FRG']
    if not notes or bpm <= 0:
        return None
    last = notes[-1]
    return (int(last[1]) + int(last[2])) * 60 / bpm / 4 + gap


def audio_window(txt_data, source_duration):
    """How to apply #START (seconds) / #END (milliseconds): returns (lyrics_offset, trim_start, trim_end).

    UltraStar plays the audio from #START. Two cases exist in real libraries:
      - the audio file is the full one the txt was made for: cut it to [START, END] and move the lyrics by START;
      - the audio was already replaced by a shorter version starting at START (the lyrics run past its end):
        only the lyrics are moved."""
    try:
        start = float((txt_data.get('START') or '0').replace(',', '.'))
    except ValueError:
        start = 0.0
    try:
        end = float((txt_data.get('END') or '0').replace(',', '.')) / 1000 or None
    except ValueError:
        end = None
    if start <= 0 and not end:
        return 0.0, 0.0, None
    if end is not None and end <= start:
        end = None
    last = last_note_time(txt_data)
    if start > 0 and source_duration and last and last > source_duration + 1.0:
        return start, 0.0, None
    return start, start, end


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def get_required_files(name_id: str, output_format: str, song_dir: Path) -> list:
    files = [
        song_dir / (name_id + '.ogg'),
        song_dir / (name_id + '_preview.ogg'),
        song_dir / (name_id + '.png'),
        song_dir / (name_id + '.vxla')
    ]
    if output_format == XML_FORMAT:
        files.append(song_dir / (name_id + '.mp4'))
        files.append(song_dir / (name_id + '_InGameLoading.png'))
        files.append(song_dir / (name_id + '_long.png'))
    elif output_format == JSON_FORMAT:
        files.append(song_dir / (name_id + '.bk2'))
    return files


def validate_converted_files(required: list) -> list:
    missing = []
    for file_path in required:
        if not file_path.exists():
            missing.append(f"{file_path.name}")
    return missing


# ---------------------------------------------------------------------------
# Source files of a song folder
# ---------------------------------------------------------------------------

def _is_converter_file(file_name, name_ids):
    if '.tmp.' in file_name or file_name.endswith('.tmp'):
        return True
    return naming.is_generated_file(file_name, name_ids)


def _find_tagged_file(song_dir: Path, tag_value, files):
    if not tag_value:
        return None
    candidate = song_dir / tag_value
    if candidate.is_file():
        return candidate
    wanted = tag_value.strip().lower()
    for f in files:
        if f.name.lower() == wanted:
            return f
    return None


def _looks_like_ultrastar(path: Path) -> bool:
    try:
        with open(path, 'rb') as f:
            head = f.read(8192).upper()
    except OSError:
        return False
    return b'#BPM' in head and (b'#TITLE' in head or b'#ARTIST' in head)


def choose_txt_file(txt_files):
    """The UltraStar txt of the song: skips non-UltraStar txt files and prefers the
    single-player version over '[MULTI]'/'[DUET]' files."""
    candidates = sorted((f for f in txt_files if _looks_like_ultrastar(f)), key=lambda f: f.name.lower())
    if not candidates:
        return None
    single = [f for f in candidates if not re.search(r'\[(multi|duet)\]|\bduet\b', f.name, re.IGNORECASE)]
    return (single or candidates)[-1]


def resolve_song_sources(song_dir: Path, txt_data, name_ids):
    """Original audio/video/cover of the song: the txt tags first, then the remaining files.
    Files generated by the converter itself are never treated as sources."""
    files = sorted((x for x in song_dir.iterdir() if x.is_file() and not _is_converter_file(x.name, name_ids)),
                   key=lambda f: f.name.lower())
    videos = [f for f in files if f.suffix.lower() in SupportedFormats.VIDEO_EXTENSIONS]
    audios = [f for f in files if f.suffix.lower() in SupportedFormats.AUDIO_EXTENSIONS]
    images = [f for f in files if f.suffix.lower() in SupportedFormats.IMAGE_EXTENSIONS]

    audio = _find_tagged_file(song_dir, txt_data.get('AUDIO'), audios) or \
        _find_tagged_file(song_dir, txt_data.get('MP3'), audios + videos)
    if audio is None and audios:
        preferred = [f for f in audios if not re.search(r'instrumental|karaoke|vocals|voz', f.name, re.IGNORECASE)]
        audio = (preferred or audios)[0]

    video = _find_tagged_file(song_dir, txt_data.get('VIDEO'), videos)
    if video is None and videos:
        video = max(videos, key=lambda f: f.stat().st_size)

    cover = _find_tagged_file(song_dir, txt_data.get('COVER'), images)
    if cover is None and images:
        preferred = [f for f in images if re.search(r'cover|\[co\]', f.name, re.IGNORECASE)]
        background = _find_tagged_file(song_dir, txt_data.get('BACKGROUND'), images)
        others = [f for f in images if f != background]
        cover = (preferred or others or images)[0]

    if audio is None and video is not None:
        audio = video
    return audio, video, cover


def adopt_legacy_cache(song_dir: Path, name_id: str, legacy_ids) -> None:
    """Older versions named cached files with a different name_id (e.g. '&' kept). Reuse them
    instead of converting again: they are copied (never moved) to the current name."""
    for legacy_id in legacy_ids:
        for suffix in naming.GENERATED_SUFFIXES:
            if suffix in (naming.VXLA_SUFFIX, naming.VXLA_META_SUFFIX):
                continue
            old = song_dir / (legacy_id + suffix)
            new = song_dir / (name_id + suffix)
            if old.is_file() and not new.exists():
                shutil.copy2(old, new)
                logger.info(f"Reusing cached {old.name} as {new.name}")
    # a folder renamed outside the converter (usdb_syncer moves a song to its "Artist - Title" folder when it
    # downloads it again) keeps its video under the old ID: encoding it again would take hours
    bk2 = song_dir / (name_id + naming.VIDEO_BK2_SUFFIX)
    if not bk2.exists():
        others = [p for p in song_dir.glob('*' + naming.VIDEO_BK2_SUFFIX) if p.is_file()]
        if len(others) == 1:
            try:
                os.link(others[0], bk2)
            except OSError:
                shutil.copy2(others[0], bk2)
            logger.info(f"Reusing the converted video {others[0].name} as {bk2.name}")


def _vxla_cache_params(txt_path: Path, output_format, pitch_method, ignore_medley, keep_accents, song_duration,
                       vocal_isolation, genius_lookup=True, lyrics_offset=0.0):
    stat = txt_path.stat()
    return {
        'version': VXLA_GENERATOR_VERSION,
        'format': output_format,
        'pitch_correction': pitch_method,
        'vocal_isolation': bool(vocal_isolation) if pitch_method == SLOW else False,
        'no_medley': bool(ignore_medley),
        'keep_accents': bool(keep_accents),
        'genius': bool(genius_lookup),
        'txt': txt_path.name,
        'txt_size': stat.st_size,
        'txt_mtime': int(stat.st_mtime),
        'duration': round(song_duration, 1),
        'lyrics_offset': round(lyrics_offset, 3),
    }


def _vxla_is_current(vxla_path: Path, meta_path: Path, params) -> bool:
    if not vxla_path.exists() or not meta_path.exists():
        return False
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f) == params
    except (OSError, json.JSONDecodeError):
        return False


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _copy_dlc_base_media(cfg, dlc_id):
    include_dlc = bool(cfg.conversion_tweaks.dlc_songs.include)
    source_json = str(cfg.conversion_tweaks.dlc_songs.songs_json_path) if not _is_blank(cfg.conversion_tweaks.dlc_songs.songs_json_path) else None
    if not (include_dlc and source_json and os.path.exists(source_json)):
        return
    source_songs_dir = os.path.join(os.path.dirname(source_json), 'Songs')
    if not os.path.exists(source_songs_dir):
        return
    dest_songs_dir = os.path.join(_output_dir, dlc_id, 'romfs', 'Songs')
    logger.info(f"Copying DLC media files from {source_songs_dir} to {dest_songs_dir}...")
    try:
        os.makedirs(dest_songs_dir, exist_ok=True)
        copied = 0
        total_dirs = sum(1 for _ in os.scandir(source_songs_dir) if _.is_dir())
        logger.info(f"Found {total_dirs} song folders in Base JSON directory. Starting copy (this may take a while)...")

        for item in os.listdir(source_songs_dir):
            _check_stop()
            s_item = os.path.join(source_songs_dir, item)
            d_item = os.path.join(dest_songs_dir, item)
            if os.path.isdir(s_item):
                shutil.copytree(s_item, d_item, dirs_exist_ok=True)
                copied += 1
                if copied % 10 == 0:
                    logger.info(f"Copied {copied}/{total_dirs} base DLC songs...")

        logger.info(f"Successfully copied all {copied} DLC media folders.")
    except ConversionStopped:
        raise
    except Exception as e:
        logger.error(f"Failed to copy DLC media files: {e}")


def _find_name_id_collisions(dirs_to_convert):
    """Two folders with the same name_id would overwrite each other in the patch."""
    owners = {}
    duplicates = {}
    for dir_name in dirs_to_convert:
        name_id = naming.construct_name_id_from_directory_name(dir_name.rstrip('.'))
        if name_id in owners:
            duplicates[dir_name] = owners[name_id]
        else:
            owners[name_id] = dir_name
    return duplicates


def convert_files(dirs_to_convert, cfg, stop_event=None, progress_callback=None, song_callback=None):
    """Converts every song folder. Returns a summary {'ok': [...], 'skipped': [(dir, reason)],
    'failed': [(dir, error)], 'stopped': bool}.

    song_callback(dir_name, state, detail) is called with state 'running', 'ok', 'skipped' or 'failed'."""
    dlc_id = str(cfg.dlc.id)
    core_id = str(cfg.core.id) if cfg.core.id else None
    output_format = get_output_format(cfg)
    dlc_json_name = str(cfg.dlc.json_name) if cfg.dlc.json_name else None
    target_size_mb = float(cfg.conversion_tweaks.max_video_size or 50)
    pitch_correction_method = str(cfg.conversion_tweaks.pitch_correction or FAST).lower()
    vocal_isolation = getattr(cfg.conversion_tweaks, "vocal_isolation", False)
    ignore_medley = bool(cfg.conversion_tweaks.no_medley)
    ignore_video = bool(cfg.conversion_tweaks.still_video)
    keep_accents = bool(getattr(cfg.conversion_tweaks, "keep_accents", True))
    force_reconvert = bool(getattr(cfg.conversion_tweaks, "force_reconvert", False))
    genius_lookup = bool(getattr(cfg.conversion_tweaks, "genius_lookup", True))
    # chorus lookup on genius.com uses internet for every song; also resets the offline flag of a previous run
    UltrastarToSingit._genius_offline = not genius_lookup
    if not genius_lookup:
        logger.info('Genius chorus lookup disabled: using medley tags or automatic detection (no internet).')
    # Map output_format to UltrastarToSingit OLD/NEW constants
    vxla_output_type = UltrastarToSingit.JSON if output_format == JSON_FORMAT else UltrastarToSingit.XML

    json_file_name = (dlc_json_name + '.json') if dlc_json_name else None
    all_dirs = [d for d in os.listdir(_input_dir) if os.path.isdir(os.path.join(_input_dir, d))] \
        if os.path.isdir(_input_dir) else list(dirs_to_convert)
    game_ids = game_ids_for(sorted(set(all_dirs) | set(dirs_to_convert)), cfg)
    current_game_ids = {g.lower() for g in game_ids.values()}

    summary = {'ok': [], 'skipped': [], 'failed': [], 'stopped': False}
    summary_lock = threading.Lock()

    def report(kind, item):
        with summary_lock:
            summary[kind].append(item)
        if song_callback:
            dir_name, detail = (item, '') if isinstance(item, str) else item
            song_callback(dir_name, kind, detail)

    try:
        _copy_dlc_base_media(cfg, dlc_id)
    except ConversionStopped:
        summary['stopped'] = True
        return summary

    collisions = _find_name_id_collisions(dirs_to_convert)
    for dir_name, other in collisions.items():
        reason = f"same ID as '{other}' (rename one of the folders)"
        logger.error(f"Skipping '{dir_name}': {reason}")
        report('skipped', (dir_name, reason))
    dirs_to_convert = [d for d in dirs_to_convert if d not in collisions]

    total_song_count = len(dirs_to_convert) + len(collisions)
    completed_songs = len(collisions)
    progress_lock = threading.Lock()
    if progress_callback and collisions:
        progress_callback(completed_songs, total_song_count)

    def _process_single_song(dir_long_name):
        nonlocal completed_songs
        if stop_event and stop_event.is_set():
            with progress_lock:
                completed_songs += 1
                if progress_callback:
                    progress_callback(completed_songs, total_song_count)
            return

        # Fix Wine trailing dot bug
        needs_rename = dir_long_name.endswith('.')
        original_dir_long_name = dir_long_name
        if needs_rename:
            clean_name = dir_long_name.rstrip('.')
            original_path = Path(_input_dir) / original_dir_long_name
            clean_path = Path(_input_dir) / clean_name
            try:
                original_path.rename(clean_path)
                dir_long_name = clean_name
            except Exception as e:
                logger.error(f"Failed to temporarily rename {original_dir_long_name}: {e}")
                needs_rename = False

        try:
            if song_callback:
                song_callback(original_dir_long_name, 'running', '')
            _convert_song(dir_long_name)
            report('ok', original_dir_long_name)
        except ConversionStopped:
            summary['stopped'] = True
            logger.info(f"Stopped while converting '{original_dir_long_name}' (finished files are kept in the cache).")
            if song_callback:
                song_callback(original_dir_long_name, 'stopped', '')
        except SongError as e:
            logger.error(f"Skipping '{original_dir_long_name}': {e}")
            report('skipped', (original_dir_long_name, str(e)))
        except Exception as e:
            logger.exception(f"Error with directory {original_dir_long_name}")
            logger.error(f"Error with directory {original_dir_long_name}: {e}")
            report('failed', (original_dir_long_name, str(e)))
        finally:
            if needs_rename:
                try:
                    current_path = Path(_input_dir) / dir_long_name
                    original_path = Path(_input_dir) / original_dir_long_name
                    if current_path.exists():
                        current_path.rename(original_path)
                except Exception as e:
                    logger.error(f"Failed to restore original folder name {original_dir_long_name}: {e}")

            with progress_lock:
                completed_songs += 1
                if progress_callback:
                    progress_callback(completed_songs, total_song_count)

    def _convert_song(dir_long_name):
        name_id = naming.construct_name_id_from_directory_name(dir_long_name)
        legacy_ids = naming.legacy_name_ids(dir_long_name)
        logger.info(f"{dir_long_name} -> {name_id}")

        list_in_dir = Path(_input_dir) / dir_long_name
        adopt_legacy_cache(list_in_dir, name_id, legacy_ids)

        output_video_file_name = name_id + ('.mp4' if output_format == XML_FORMAT else '.bk2')
        png_file_name = name_id + '.png'
        png_in_game_file_name = name_id + '_InGameLoading.png'
        png_long_file_name = name_id + '_long.png'
        png_result_file_name = name_id + '_Result.png'
        vxla_file_name = name_id + '.vxla'
        ogg_file_name = name_id + '.ogg'
        ogg_preview_file_name = name_id + '_preview.ogg'
        xml_file_name = name_id + '_meta.xml'

        # Getting info from the text file
        txt_files = [x for x in list_in_dir.iterdir() if x.is_file() and x.suffix.lower() == SupportedFormats.TXT_EXTENSIONS]
        txt_path = choose_txt_file(txt_files)
        if txt_path is None:
            raise SongError("no UltraStar .txt file found")
        txt_data = UltrastarToSingit.parse_file(txt_path)
        if 'BPM' not in txt_data:
            raise SongError(f"{txt_path.name} has no #BPM tag")

        name_ids = [name_id] + legacy_ids
        audio_source, video_source, cover_source = resolve_song_sources(list_in_dir, txt_data, name_ids)

        video_gap = 0.0
        if 'VIDEOGAP' in txt_data:
            # how many seconds the song is out of sync with the video
            #  positive - video starts before the song
            #  negative - video starts after the song
            try:
                video_gap = float(txt_data['VIDEOGAP'].replace(',', '.'))
            except ValueError:
                logger.warning(f"Ignoring invalid #VIDEOGAP:{txt_data['VIDEOGAP']}")

        # --- audio (needed first: its duration drives the static video and the vxla) ---
        ogg_path = list_in_dir / ogg_file_name
        audio_meta_path = list_in_dir / (name_id + naming.AUDIO_META_SUFFIX)
        lyrics_offset, trim_start, trim_end = 0.0, 0.0, None
        if audio_source is not None and ('START' in txt_data or 'END' in txt_data):
            try:
                source_duration = get_duration(audio_source)
            except SongError:
                source_duration = None
            lyrics_offset, trim_start, trim_end = audio_window(txt_data, source_duration)
            if lyrics_offset:
                logger.info(f"#START:{txt_data.get('START')}: lyrics moved {lyrics_offset:.2f} s"
                            + (" and audio cut to the same part" if trim_start or trim_end else
                               " (the audio file already starts there)"))
        audio_params = {'trim_start': trim_start, 'trim_end': trim_end, 'video_gap': video_gap,
                        'lyrics_offset': lyrics_offset}
        cached_params = _read_json(audio_meta_path)
        if ogg_path.exists() and cached_params is None:
            # converted by a previous version (no window applied): still valid if no window is needed now
            cached_params = {'trim_start': 0.0, 'trim_end': None, 'video_gap': video_gap, 'lyrics_offset': 0.0}
        audio_changed = cached_params != audio_params
        if not ogg_path.exists() or audio_changed:
            if audio_source is None:
                raise SongError("no audio file found (#MP3/#AUDIO tag or any audio file)")
            if not create_audio(audio_source, list_in_dir, ogg_file_name, video_gap, trim_start, trim_end):
                raise SongError("audio conversion failed")
        if audio_changed or not audio_meta_path.exists():
            with open(audio_meta_path, 'w', encoding='utf-8') as f:
                json.dump(audio_params, f)
        song_duration = get_duration(ogg_path)

        if audio_changed or not (list_in_dir / ogg_preview_file_name).exists():
            # the preview is cut from the original audio (the converted one is shifted by VIDEOGAP)
            create_audio_preview(audio_source or ogg_path, list_in_dir, ogg_preview_file_name, txt_data,
                                 lyrics_offset - trim_start if audio_source else lyrics_offset)

        # no image at all: try a frame of the video, else a placeholder with artist and title
        if cover_source is None:
            auto_cover = list_in_dir / (name_id + naming.AUTO_COVER_SUFFIX)
            if not auto_cover.exists():
                readable_video = video_source is not None and video_source.suffix.lower() != '.bk2'
                if not (readable_video and create_cover(video_source, list_in_dir, auto_cover.name, from_video=True)):
                    title, artist = txt_data.get('TITLE', dir_long_name), txt_data.get('ARTIST', '')
                    create_placeholder_cover(list_in_dir, auto_cover.name, artist, title)
            cover_source = auto_cover

        # --- video ---
        output_video_path = list_in_dir / output_video_file_name
        video_for_patch = output_video_path
        real_video = video_source
        if trim_start > 0 and (list_in_dir / output_video_file_name).exists() \
                and not ignore_video and video_source is not None:
            logger.warning(f"{output_video_file_name} was converted from the whole clip: the video starts "
                           f"{trim_start:.1f} s earlier than the song. To fix it, delete only {output_video_file_name}"
                           f" (and {name_id}.avi) of this song and convert again.")
        if real_video is not None and output_format == XML_FORMAT and real_video.suffix.lower() == '.bk2':
            real_video = None  # ffmpeg can't decode Bink 2: XML games get the static video

        if real_video is not None and not ignore_video and output_video_path.exists() \
                and real_video.suffix.lower() != '.bk2' and real_video.stat().st_size > 5 * 2 ** 20 \
                and output_video_path.stat().st_size < STILL_BK2_BYTES_PER_S * max(song_duration, 1):
            # converted while the song had no video (the still cover), the real video was added afterwards
            logger.warning(f"{output_video_file_name} looks like the still cover but {real_video.name} is a real "
                           f"video: right click the song > 'Encode the video again from its source' (the current "
                           f".bk2 is kept in _replaced_videos)")
        if real_video is not None and not ignore_video and not output_video_path.exists():
            _check_stop()
            duration = get_duration(real_video)
            original_size_mb = real_video.stat().st_size / (1024 * 1024)
            original_bitrate_kbps = int((original_size_mb * 8192) / duration) if duration > 0 else 2000
            limited_bitrate_kbps = int((target_size_mb * 8192) / duration) if duration > 0 else 2000
            target_bitrate_kbps = max(200, min(original_bitrate_kbps, limited_bitrate_kbps))

            if output_format == XML_FORMAT:
                create_video(real_video, list_in_dir, output_video_file_name, target_bitrate_kbps, trim_start)
            elif real_video.suffix.lower() == '.bk2':
                # already in the game's format
                shutil.copy2(real_video, output_video_path)
                logger.info(f"Using {real_video.name} as {output_video_file_name}")
            else:
                quality = 0.1 if is_video_still_image(real_video) else None
                temp_video_file = list_in_dir / (name_id + naming.VIDEO_INTERMEDIATE_SUFFIX)
                if not temp_video_file.exists():
                    create_video(real_video, list_in_dir, temp_video_file.name, target_bitrate_kbps, trim_start)
                if temp_video_file.exists():
                    temp_size_mb = temp_video_file.stat().st_size / (1024 * 1024)
                    compression_percentage = 100 if temp_size_mb <= target_size_mb else \
                        max(1, min(200, int(round(target_size_mb / temp_size_mb * 100))))
                    create_video_bink(temp_video_file, list_in_dir, output_video_file_name, quality, duration,
                                      compression_percentage)

        if output_format == XML_FORMAT and output_video_path.exists() and 'avi' in get_container_format(output_video_path):
            # created by a previous version: an AVI named .mp4 is not played by the game
            logger.warning(f"{output_video_file_name} is an AVI file, remuxing it to MP4")
            fixed = list_in_dir / (name_id + '.remux.mp4')
            if _ffmpeg(['-i', os.fspath(output_video_path), '-c', 'copy', '-movflags', '+faststart'], fixed):
                os.replace(fixed, output_video_path)

        if output_format == JSON_FORMAT:
            if ignore_video and output_video_path.exists():
                logger.info(f"Still video requested but {output_video_file_name} is already cached, using it")
            elif not output_video_path.exists():
                # no video, or binkc failed: static video from the cover image
                still_file = list_in_dir / (name_id + naming.STILL_VIDEO_SUFFIX)
                if not still_file.exists():
                    create_still_video_from_cover_image(cover_source, list_in_dir, still_file.name, song_duration)
                else:
                    logger.info(f"Static video already exists, skipping generation: {still_file.name}")
                if still_file.exists():
                    create_video_bink(still_file, list_in_dir, output_video_file_name, quality=0.1,
                                      duration=song_duration)
        else:
            if ignore_video or not output_video_path.exists():
                still_file = list_in_dir / (name_id + naming.STILL_VIDEO_MP4_SUFFIX)
                if still_file.exists() and 'avi' in get_container_format(still_file):
                    still_file.unlink()  # static video made by a previous version, cheap to rebuild
                if not still_file.exists():
                    create_still_video_from_cover_image(cover_source, list_in_dir, still_file.name, song_duration)
                if still_file.exists():
                    if not output_video_path.exists():
                        shutil.copy2(still_file, output_video_path)
                    # with "still video" the real cached video is kept, only the patch gets the static one
                    video_for_patch = still_file

        # --- images (a cached image of the wrong size, e.g. a full-size copy left by an extractor, is rebuilt) ---
        if not _image_is_current(list_in_dir / png_file_name, 256, 256, cover_source):
            create_cover(cover_source, list_in_dir, png_file_name)
        if output_format == XML_FORMAT:
            if not _image_is_current(list_in_dir / png_long_file_name, 191, 396, cover_source):
                create_cover_long(cover_source, list_in_dir, png_long_file_name)
            if not _image_is_current(list_in_dir / png_in_game_file_name, 512, 512, cover_source):
                create_in_game_loading_picture(cover_source, list_in_dir, png_in_game_file_name)

        # --- vxla ---
        vxla_path = list_in_dir / vxla_file_name
        meta_path = list_in_dir / (name_id + naming.VXLA_META_SUFFIX)
        params = _vxla_cache_params(txt_path, output_format, pitch_correction_method, ignore_medley, keep_accents,
                                    song_duration, vocal_isolation, genius_lookup, lyrics_offset)
        official_vxla = list_in_dir / naming.OFFICIAL_VXLA_NAME
        if official_vxla.is_file():
            # lyrics/notes of a Let's Sing DLC song: reuse them exactly instead of rebuilding them from the txt
            params = {'version': VXLA_GENERATOR_VERSION, 'format': output_format, 'official': official_vxla.name,
                      'official_size': official_vxla.stat().st_size, 'official_mtime': int(official_vxla.stat().st_mtime),
                      'duration': round(song_duration, 1)}
            if force_reconvert or not _vxla_is_current(vxla_path, meta_path, params):
                count = OfficialVxla.convert(official_vxla, vxla_file_name, list_in_dir, song_duration, vxla_output_type)
                logger.info(f"Using the official Let's Sing lyrics/notes of {dir_long_name} ({count} notes)")
                with open(meta_path, 'w', encoding='utf-8') as f:
                    json.dump(params, f, indent=1)
            else:
                logger.info(f"Using cached vxla for {dir_long_name} (no changes detected).")
        elif force_reconvert or not _vxla_is_current(vxla_path, meta_path, params):
            _check_stop()
            if pitch_correction_method == SLOW:
                pitch_corr = PitchAnalyzer.get_pitch_correction_suggestion_slow(txt_data, os.fspath(ogg_path), min_pitch=PITCH_MIN, max_pitch=PITCH_MAX, use_demucs=vocal_isolation)
            else:
                pitch_corr = PitchAnalyzer.get_pitch_correction_suggestion_fast(txt_data, min_pitch=PITCH_MIN, max_pitch=PITCH_MAX)
            UltrastarToSingit.main(txt_path, song_duration, pitch_corr, s=name_id, directory=list_in_dir,
                                   output_type=vxla_output_type, ignore_medley=ignore_medley,
                                   keep_accents=keep_accents, time_offset=lyrics_offset)
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(params, f, indent=1)
        else:
            logger.info(f"Using cached vxla for {dir_long_name} (no changes detected).")

        # Validate that all required converted files were created successfully
        required = get_required_files(name_id, output_format, list_in_dir)
        missing = validate_converted_files(required)
        if missing:
            raise SongError(f"missing converted files: {', '.join(missing)}")

        # placing all files into the correct folders, BEFORE registering the song: a song listed in
        # name.txt / the JSON without its files can hang the game
        base_dlc_dir = os.path.join(_output_dir, dlc_id)
        songs_dir = os.path.join(base_dlc_dir, 'romfs', 'Songs')
        # inside the patch the files carry the game ID (title first for 2026), the cache keeps name_id
        game_id = game_ids.get(dir_long_name, name_id)
        in_patch = lambda file_name: game_id + file_name[len(name_id):]
        copies = [
            (list_in_dir / ogg_file_name, os.path.join(songs_dir, 'audio', in_patch(ogg_file_name))),
            (list_in_dir / ogg_preview_file_name,
             os.path.join(songs_dir, 'audio_preview', in_patch(ogg_preview_file_name))),
            (list_in_dir / png_file_name, os.path.join(songs_dir, 'covers', in_patch(png_file_name))),
            (list_in_dir / vxla_file_name, os.path.join(songs_dir, 'vxla', in_patch(vxla_file_name))),
            (video_for_patch, os.path.join(songs_dir, 'videos', in_patch(output_video_file_name))),
        ]
        if output_format == XML_FORMAT:
            os.makedirs(os.path.join(songs_dir, 'covers_duet'), exist_ok=True)
            copies += [
                (list_in_dir / png_in_game_file_name, os.path.join(songs_dir, 'backgrounds', 'InGameLoading', png_in_game_file_name)),
                (list_in_dir / png_in_game_file_name, os.path.join(songs_dir, 'backgrounds', 'Result', png_result_file_name)),
                (list_in_dir / png_long_file_name, os.path.join(songs_dir, 'covers_long', png_long_file_name)),
            ]
        copied = []
        try:
            for source, destination in copies:
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(os.fspath(source), destination)
                copied.append(destination)

            # Handle name.txt, then SongsDLC.tsv + meta xml (XML format) or the json file (JSON format)
            profile = None
            if uses_game_ids(cfg):  # Let's Sing 2026 only: older editions keep what they always had
                official = (list_in_dir / naming.OFFICIAL_VXLA_NAME).exists()
                pitch = sung_median_pitch(list_in_dir / (naming.OFFICIAL_VXLA_NAME if official else vxla_file_name),
                                          list_in_dir / (name_id + naming.VOICE_SUFFIX), official)
                profile = (song_difficulty(list_in_dir / vxla_file_name),
                           singer_gender(txt_data.get('ARTIST', ''), txt_data.get('TITLE', ''), pitch))
            handle_xml_or_json(dlc_id, core_id, json_file_name, list_in_dir, txt_data,
                               game_id, output_format, xml_file_name, cfg,
                               old_ids=[i for i in [name_id] + legacy_ids if i != game_id], profile=profile)
            if output_format == XML_FORMAT:
                shutil.copy2(os.fspath(list_in_dir / xml_file_name), os.path.join(base_dlc_dir, 'romfs'))
            add_data_to_name_txt(dlc_id, game_id, output_format, dlc_json_name, cfg)
            if game_id != name_id:
                _remove_old_patch_copies(songs_dir, [name_id] + legacy_ids, list_in_dir, current_game_ids)
        except Exception:
            # don't leave half a song in the patch (these are copies, the cache is untouched)
            for destination in copied:
                try:
                    os.remove(destination)
                except OSError:
                    pass
            raise

    is_multithreaded = bool(getattr(cfg.conversion_tweaks, "multithreading", False))
    max_workers = 1
    if is_multithreaded:
        max_workers = int(getattr(cfg.conversion_tweaks, "multithreading_workers", None) or 3)

    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for d_name in dirs_to_convert:
                executor.submit(_process_single_song, d_name)
    else:
        for d_name in dirs_to_convert:
            _process_single_song(d_name)

    if stop_event and stop_event.is_set():
        summary['stopped'] = True
    return summary


def log_summary(summary) -> None:
    logger.info(f"Converted: {len(summary['ok'])}, skipped: {len(summary['skipped'])}, "
                f"failed: {len(summary['failed'])}{' (stopped by user)' if summary['stopped'] else ''}")
    for dir_name, reason in summary['skipped']:
        logger.info(f"  skipped  {dir_name}: {reason}")
    for dir_name, error in summary['failed']:
        logger.info(f"  FAILED   {dir_name}: {error}")


def main(cfg=None, stop_event=None, progress_callback=None, song_callback=None, only_dirs=None):
    """only_dirs: convert just these song folders and update the existing patch (the output folder
    is not cleared, songs already in it are kept)."""
    global _stop_event
    _stop_event = stop_event

    if cfg is None:
        cfg = load_config()
    cfg = resolve_config(cfg)

    _init_paths(cfg)
    output_format = get_output_format(cfg)

    if not bool(cfg.conversion_tweaks.enable):
        cfg.conversion_tweaks = load_default_config().conversion_tweaks

    pitch_method = str(cfg.conversion_tweaks.pitch_correction).lower()
    ignore_medley = bool(cfg.conversion_tweaks.no_medley)
    ignore_video = bool(cfg.conversion_tweaks.still_video)

    dirs_to_convert = find_folders_to_convert()
    if only_dirs is not None:
        wanted = set(only_dirs)
        dirs_to_convert = [d for d in dirs_to_convert if d in wanted]
        logger.info(f'Converting {len(dirs_to_convert)} selected song(s) and updating the existing patch.')
    else:
        delete_output_folder(cfg, dirs_to_convert)

    logger.info('Beginning conversion - format: ' + output_format.upper())
    logger.info('Output folder: ' + _output_dir)
    logger.info('Pitch correction method: ' + pitch_method)
    if ignore_medley:
        logger.info('MODE: Ignoring Medley tags (forcing Genius/Auto detection)')
    if ignore_video:
        logger.info('MODE: Ignoring original video (forcing still image video)')
    summary = convert_files(dirs_to_convert, cfg, stop_event=stop_event, progress_callback=progress_callback,
                            song_callback=song_callback)
    log_summary(summary)
    return summary
