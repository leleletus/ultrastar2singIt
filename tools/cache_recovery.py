import os
import shutil

import naming


def _find_songs_dirs(output_dir: str) -> list:
    """Every <TitleID>/romfs/Songs folder of the patch (XML patches also contain the core's romfs)."""
    found = []
    for root, dirs, files in os.walk(output_dir):
        if os.path.basename(root) == "Songs" and os.path.basename(os.path.dirname(root)) == "romfs":
            found.append(root)
            dirs[:] = []
    return found


def recover_cache(input_dir: str, output_dir: str) -> tuple[int, str]:
    """
    Recovers cached output files from the destination directory back to the input directories.
    Existing files in the song folders are never overwritten.
    Returns (count, message).
    """
    if not input_dir or not output_dir or not os.path.exists(input_dir) or not os.path.exists(output_dir):
        return 0, "Input and Output directories must be set and exist."

    songs_dirs = _find_songs_dirs(output_dir)
    if not songs_dirs:
        return 0, "Could not find romfs/Songs in output directory. Nothing to recover."

    count = 0
    files_to_recover = [
        ("videos", naming.VIDEO_BK2_SUFFIX),
        ("videos", naming.VIDEO_MP4_SUFFIX),
        ("audio", naming.AUDIO_SUFFIX),
        ("audio_preview", naming.AUDIO_PREVIEW_SUFFIX),
        ("covers", naming.COVER_SUFFIX),
        ("covers_long", naming.COVER_LONG_SUFFIX),
        (os.path.join("backgrounds", "InGameLoading"), naming.IN_GAME_LOADING_SUFFIX),
    ]

    for d in sorted(os.listdir(input_dir)):
        d_path = os.path.join(input_dir, d)
        if not (os.path.isdir(d_path) and " - " in d):
            continue
        name_id = naming.construct_name_id_from_directory_name(d.rstrip('.'))
        for songs_dir in songs_dirs:
            for sub_dir, suffix in files_to_recover:
                dest = os.path.join(d_path, name_id + suffix)
                if os.path.exists(dest):
                    continue
                # the patch may still use an ID made by an older version
                for nid in naming.all_name_ids(d.rstrip('.')):
                    src = os.path.join(songs_dir, sub_dir, nid + suffix)
                    if os.path.exists(src):
                        try:
                            shutil.copy2(src, dest)
                            count += 1
                        except OSError:
                            pass  # Ignore individual file permission errors
                        break

    return count, f"Recovered {count} files successfully!"
