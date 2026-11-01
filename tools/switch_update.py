"""Updates the patch on the Switch over MTP copying only the files that changed (KDE's kioclient + DBI MTP).

Usage:
    python tools/switch_update.py <local patch folder> [--remote URL] [--baseline foto.json]           # only lists
    python tools/switch_update.py <local patch folder> [--remote URL] [--baseline foto.json] --apply   # copies

<local patch folder> is the DLC folder of the output, e.g. ~/LetsSing/output/0100EE4020D19003.
--remote defaults to the same folder on the SD card through DBI's MTP responder.

A "photo" (size + hash of every file) of what the Switch has is kept next to the patch
(next to the output folder: <output>/../<dlc>.switch.json, the converter empties <output>) and written
after every update. The first time, --baseline gives the photo of the
patch that was copied to the Switch. Before copying, a sample of the files that did not change is checked on the
Switch: if their sizes differ, the Switch has another patch and nothing is copied (copy the whole folder instead).
Every file replaced on the Switch is first saved to <output>/../switch_backup_<date>/. Nothing is deleted on the
Switch (files of songs removed from the patch are only listed); a file is removed only to be replaced, after its
backup (DBI's MTP responder does not overwrite files).
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time

DEFAULT_REMOTE = "mtp:/DBI MTP Responder/1: SD Card/atmosphere/contents/{dlc}"


def photo(root):
    """{relative path: [size, sha1]} of every file (big videos: sha1 of the first and last MB)."""
    out = {}
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            size = os.path.getsize(path)
            h = hashlib.sha1()
            with open(path, 'rb') as f:
                if size > 8 * 1024 * 1024:
                    h.update(f.read(1 << 20))
                    f.seek(-(1 << 20), 2)
                    h.update(f.read())
                else:
                    h.update(f.read())
            out[os.path.relpath(path, root).replace(os.sep, '/')] = [size, h.hexdigest()]
    return out


def kio(*args, timeout=600):
    return subprocess.run(['kioclient', '--noninteractive', *args], capture_output=True, text=True, timeout=timeout)


def make_dirs(remote, relative, made):
    """Creates on the Switch every folder of relative's path, top first (MTP can't make a/b/c if a/b is missing)."""
    parts = relative.split('/')[:-1]
    for i in range(1, len(parts) + 1):
        folder = '/'.join(parts[:i])
        if folder not in made:
            kio('mkdir', f"{remote}/{folder}")
            made.add(folder)


def remote_size(url):
    result = kio('stat', url, timeout=60)
    for line in result.stdout.splitlines():
        if line.startswith('SIZE'):
            return int(line.split()[1])
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('patch')
    parser.add_argument('--remote')
    parser.add_argument('--baseline', help="photo of the patch the Switch has (first time only)")
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--sample', type=int, default=25, help="unchanged files checked on the Switch")
    parser.add_argument('--prune-first', action='store_true',
                        help="with --apply: remove the old files before copying, for an SD card without room for both "
                             "patches (the old files without an identical copy in the patch are backed up first)")
    parser.add_argument('--prune', action='store_true',
                        help="with --apply: also remove from the Switch the files of the photo that are no longer in "
                             "the patch (e.g. after the songs were renamed); only files this tool knows it put there")
    args = parser.parse_args()

    patch = os.path.abspath(os.path.expanduser(args.patch))
    dlc = os.path.basename(patch)
    remote = (args.remote or DEFAULT_REMOTE.format(dlc=dlc)).rstrip('/')
    keep_dir = os.path.dirname(os.path.dirname(patch))  # outside the output folder, which gets emptied
    manifest_path = os.path.join(keep_dir, dlc + '.switch.json')
    baseline_path = args.baseline or manifest_path
    if not os.path.exists(baseline_path):
        sys.exit(f"No photo of the Switch patch ({manifest_path}): pass --baseline the first time, "
                 f"or copy the whole folder once and run this again.")
    if args.apply:  # two copies at once would both write the photo and fight over the same files on the Switch
        import fcntl
        lock = open(manifest_path + '.lock', 'w')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit("Another update of the Switch is already running; wait for it to finish.")
    with open(baseline_path, encoding='utf-8') as f:
        on_switch = json.load(f)

    local = photo(patch)
    changed = sorted(k for k in local if on_switch.get(k) != local[k])
    removed = sorted(k for k in on_switch if k not in local)
    size = sum(local[k][0] for k in changed)
    print(f"{len(changed)} file(s) to copy ({size / 1024 / 1024:.1f} MB); {len(local) - len(changed)} unchanged")
    for k in changed:
        print(f"   {'new    ' if k not in on_switch else 'changed'}  {k}")
    if removed:
        action = 'will be removed from the Switch' if args.prune else 'left on the Switch (use --prune to remove them)'
        print(f"{len(removed)} file(s) no longer in the patch ({sum(on_switch[k][0] for k in removed) / 2**30:.1f} GB), "
              f"{action}: {removed[:5]}")
    if not changed and not (removed and args.prune):
        return

    # is the Switch really at the photo? check a sample of the unchanged files
    if kio('ls', remote + '/', timeout=60).returncode != 0:
        sys.exit(f"Can't open {remote}: is the Switch connected with DBI in MTP mode?")
    # what the photo says the Switch has (unchanged files first; after a rename almost everything changes)
    unchanged = [k for k in local if k not in changed and k in on_switch]
    others = [k for k in on_switch if k not in unchanged]
    sample = random.sample(unchanged, min(args.sample, len(unchanged)))
    sample += random.sample(others, min(args.sample - len(sample), len(others)))
    wrong = [k for k in sample if remote_size(f"{remote}/{k}") != on_switch[k][0]]
    if wrong:
        sys.exit(f"The Switch does not have the expected patch ({len(wrong)} of {len(sample)} checked files differ, "
                 f"e.g. {wrong[:3]}). Nothing copied: copy the whole folder once instead.")
    print(f"Switch checked: {len(sample)} files match the photo.")
    if not args.apply:
        print("Run again with --apply to copy.")
        return

    backup = os.path.join(keep_dir, f"switch_backup_{time.strftime('%Y-%m-%d_%H%M%S')}")
    made = set()
    if args.prune_first and removed:
        # the console keeps its previous song list (songs_xx.json is copied last) but its songs lose their files
        # until the copy ends: do not play meanwhile
        in_patch = {tuple(v) for v in local.values()}
        for k in removed:
            url = f"{remote}/{k}"
            if not (k.endswith('.bk2') and tuple(on_switch[k]) in in_patch):  # videos already in the patch: no copy
                os.makedirs(os.path.dirname(os.path.join(backup, k)), exist_ok=True)
                if kio('copy', url, 'file://' + os.path.join(backup, k)).returncode != 0 \
                        and remote_size(url) is not None:
                    sys.exit(f"Could not back up {k} from the Switch: nothing else removed.")
            if kio('remove', url).returncode == 0 or remote_size(url) is None:
                del on_switch[k]
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(on_switch, f)
        print(f"   {len(removed)} old file(s) removed from the Switch first", flush=True)
        removed = []
    for k in changed:
        url = f"{remote}/{k}"
        if k in on_switch:  # keep what the Switch had
            os.makedirs(os.path.dirname(os.path.join(backup, k)), exist_ok=True)
            if kio('copy', url, 'file://' + os.path.join(backup, k)).returncode != 0:
                sys.exit(f"Could not back up {k} from the Switch: stopped before changing anything else.")
        else:
            make_dirs(remote, k, made)
        result = kio('copy', '--overwrite', 'file://' + os.path.join(patch, k), url)
        if result.returncode != 0 and (k in on_switch or remote_size(url) is not None):
            # DBI's MTP responder refuses to overwrite: remove it (backed up, or a leftover the photo does not know)
            # and copy again
            kio('remove', url)
            result = kio('copy', 'file://' + os.path.join(patch, k), url)
        got = remote_size(url)
        if result.returncode != 0 or got != local[k][0]:
            sys.exit(f"Copy of {k} failed ({result.stderr.strip()[:200]}); the Switch keeps the other files. "
                     f"Backup of the replaced files: {backup}")
        on_switch[k] = local[k]
        print(f"   copied {k}")
        with open(manifest_path, 'w', encoding='utf-8') as f:  # after every file: a cut leaves it consistent
            json.dump(on_switch, f)
    if args.prune:
        for k in removed:
            if kio('remove', f"{remote}/{k}").returncode == 0 or remote_size(f"{remote}/{k}") is None:
                del on_switch[k]
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(on_switch, f)
            else:
                print(f"   could not remove {k}")
        print(f"   {len(removed)} old file(s) removed from the Switch")
    print(f"Done. Previous versions saved in {backup}" if os.path.isdir(backup) else "Done.")


if __name__ == '__main__':
    main()
