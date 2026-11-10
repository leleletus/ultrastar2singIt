"""Updates the patch on the Switch copying only the files that changed: over MTP (KDE's kioclient + DBI MTP) or over
FTP (an FTP server on the Switch, e.g. ftpd on port 5000).

Usage:
    python tools/switch_update.py <local patch folder> [--remote URL] [--baseline foto.json]           # only lists
    python tools/switch_update.py <local patch folder> [--remote URL] [--baseline foto.json] --apply   # copies
    python tools/switch_update.py <local patch folder> --ftp 192.168.1.20:5000 [--apply]               # over FTP

<local patch folder> is the DLC folder of the output, e.g. <output folder>/0100EE4020D19003.
--remote defaults to the same folder on the SD card through DBI's MTP responder; --ftp HOST:PORT uses
ftp://HOST:PORT/atmosphere/contents/<dlc> instead (anonymous login; --remote may also be an ftp:// URL).

A "photo" (size + hash of every file) of what the Switch has is kept next to the patch
(next to the output folder: <output>/../<dlc>.switch.json, the converter empties <output>) and written
after every update. The first time, --baseline gives the photo of the
patch that was copied to the Switch, or --first-copy copies the whole patch when the Switch has none for this DLC
yet (its folder is missing or empty; a folder with files is never touched). Before copying, a sample of the files that did not change is checked on the
Switch: if their sizes differ, the Switch has another patch and nothing is copied (copy the whole folder instead).
Every file replaced on the Switch is first saved to <output>/../switch_backup_<date>/, and so is every file removed
with --prune. Nothing is deleted on the Switch without --prune (files of songs removed from the patch are only
listed); a file is removed only to be replaced, after its backup (DBI's MTP responder does not overwrite files).
"""
import argparse
import ftplib
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from urllib.parse import urlparse

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


def kio_retry(*args, tries=4):
    """kio that tries again when DBI's MTP responder drops a request (it does now and then)."""
    for attempt in range(tries):
        result = kio(*args)
        if result.returncode == 0:
            break
        time.sleep(2 * (attempt + 1))
    return result


class KioRemote:
    """The patch folder on the Switch through KIO (DBI's MTP responder)."""
    overwrites = False  # DBI's MTP responder refuses to overwrite a file

    def __init__(self, url):
        self.url = url

    def listing(self, rel=''):
        """Names in the folder, or None when it can't be opened."""
        result = kio('ls', (f"{self.url}/{rel}" if rel else self.url) + '/', timeout=60)
        if result.returncode != 0:
            return None
        return [e for e in result.stdout.splitlines() if e.strip() not in ('', '.', '..')]

    def parent_listing(self):
        return kio('ls', self.url.rsplit('/', 1)[0] + '/', timeout=60).returncode == 0

    def make_root(self):
        kio('mkdir', self.url)

    def mkdir(self, rel):
        kio('mkdir', f"{self.url}/{rel}")

    def size(self, rel):
        result = kio('stat', f"{self.url}/{rel}", timeout=60)
        for line in result.stdout.splitlines():
            if line.startswith('SIZE'):
                return int(line.split()[1])
        return None

    def get(self, rel, dest):
        return kio_retry('copy', f"{self.url}/{rel}", 'file://' + dest).returncode == 0

    def put(self, src, rel):
        result = kio('copy', '--overwrite', 'file://' + src, f"{self.url}/{rel}")
        if result.returncode != 0 and self.size(rel) is not None:
            # DBI's MTP responder refuses to overwrite: remove it (already backed up, or a leftover) and copy again
            kio('remove', f"{self.url}/{rel}")
            result = kio_retry('copy', 'file://' + src, f"{self.url}/{rel}")
        return result.returncode == 0, result.stderr.strip()[:200]

    def remove(self, rel):
        return kio('remove', f"{self.url}/{rel}").returncode == 0 or self.size(rel) is None


class FtpRemote:
    """The patch folder on the Switch through its FTP server (anonymous); reconnects when Wi-Fi drops."""
    overwrites = True

    def __init__(self, url):
        u = urlparse(url)
        self.host, self.port, self.root = u.hostname, u.port or 21, u.path.rstrip('/')
        self.ftp = None

    def _conn(self):
        if self.ftp is None:
            ftp = ftplib.FTP()
            ftp.connect(self.host, self.port, timeout=60)
            ftp.login()
            ftp.set_pasv(True)
            ftp.voidcmd('TYPE I')
            self.ftp = ftp
        return self.ftp

    def _do(self, fn, tries=4):
        """fn(ftp), again on a fresh connection when the network drops; ftplib.error_perm is not retried."""
        for attempt in range(tries):
            try:
                return fn(self._conn())
            except ftplib.error_perm:
                raise
            except (OSError, EOFError, ftplib.Error):
                try:
                    self.ftp and self.ftp.close()
                except OSError:
                    pass
                self.ftp = None
                if attempt == tries - 1:
                    raise
                time.sleep(3 * (attempt + 1))

    def _path(self, rel=''):
        return f"{self.root}/{rel}" if rel else self.root

    def listing(self, rel=''):
        try:
            names = self._do(lambda f: f.nlst(self._path(rel)))
        except ftplib.error_perm:
            return None
        return [n.rsplit('/', 1)[-1] for n in names if n.rsplit('/', 1)[-1] not in ('', '.', '..')]

    def parent_listing(self):
        try:
            self._do(lambda f: f.nlst(self.root.rsplit('/', 1)[0] or '/'))
            return True
        except ftplib.error_perm:
            return False

    def make_root(self):
        parts = self.root.strip('/').split('/')
        for i in range(1, len(parts) + 1):
            try:
                self._do(lambda f: f.mkd('/' + '/'.join(parts[:i])))
            except ftplib.error_perm:
                pass  # already there

    def mkdir(self, rel):
        try:
            self._do(lambda f: f.mkd(self._path(rel)))
        except ftplib.error_perm:
            pass  # already there

    def size(self, rel):
        try:
            return self._do(lambda f: f.size(self._path(rel)))
        except ftplib.error_perm:
            return None

    def get(self, rel, dest):
        try:
            with open(dest, 'wb') as out:
                def fetch(f):
                    out.seek(0)
                    out.truncate()
                    f.retrbinary(f"RETR {self._path(rel)}", out.write, blocksize=1 << 20)
                self._do(fetch)
            return True
        except (ftplib.Error, OSError, EOFError):
            return False

    def put(self, src, rel):
        try:
            def send(f):
                with open(src, 'rb') as data:
                    f.storbinary(f"STOR {self._path(rel)}", data, blocksize=1 << 20)
            self._do(send)
            return True, ''
        except (ftplib.Error, OSError, EOFError) as e:
            return False, str(e)[:200]

    def remove(self, rel):
        try:
            self._do(lambda f: f.delete(self._path(rel)))
            return True
        except ftplib.error_perm:
            return self.size(rel) is None


def make_dirs(remote, relative, made):
    """Creates on the Switch every folder of relative's path, top first (MTP can't make a/b/c if a/b is missing)."""
    parts = relative.split('/')[:-1]
    for i in range(1, len(parts) + 1):
        folder = '/'.join(parts[:i])
        if folder not in made:
            remote.mkdir(folder)
            made.add(folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('patch')
    parser.add_argument('--remote')
    parser.add_argument('--ftp', metavar='HOST:PORT', help="copy over FTP to HOST:PORT instead of DBI's MTP")
    parser.add_argument('--baseline', help="photo of the patch the Switch has (first time only)")
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--sample', type=int, default=25, help="unchanged files checked on the Switch")
    parser.add_argument('--prune-first', action='store_true',
                        help="with --apply: remove the old files before copying, for an SD card without room for both "
                             "patches (the old files without an identical copy in the patch are backed up first)")
    parser.add_argument('--first-copy', action='store_true',
                        help="no photo yet and the Switch has no patch of this DLC (its folder is missing or empty): "
                             "copy the whole patch")
    parser.add_argument('--prune', action='store_true',
                        help="with --apply: also remove from the Switch the files of the photo that are no longer in "
                             "the patch (e.g. after the songs were renamed); only files this tool knows it put there, "
                             "each one backed up first")
    args = parser.parse_args()

    patch = os.path.abspath(os.path.expanduser(args.patch))
    dlc = os.path.basename(patch)
    if args.ftp:
        url = f"ftp://{args.ftp}/atmosphere/contents/{dlc}"
    else:
        url = (args.remote or DEFAULT_REMOTE.format(dlc=dlc)).rstrip('/')
    remote = FtpRemote(url) if url.startswith('ftp://') else KioRemote(url)
    how = 'the FTP server running on the Switch' if isinstance(remote, FtpRemote) else 'DBI in MTP mode'
    keep_dir = os.path.dirname(os.path.dirname(patch))  # outside the output folder, which gets emptied
    manifest_path = os.path.join(keep_dir, dlc + '.switch.json')
    baseline_path = args.baseline or manifest_path
    first_copy = not os.path.exists(baseline_path)
    if first_copy and (args.baseline or not args.first_copy):
        sys.exit(f"No photo of the Switch patch ({baseline_path}): the first time pass --baseline <photo>, or "
                 f"--first-copy if the Switch has no patch of this DLC yet.")
    if args.apply:  # two copies at once would both write the photo and fight over the same files on the Switch
        import fcntl
        lock = open(manifest_path + '.lock', 'w')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit("Another update of the Switch is already running; wait for it to finish.")
    if first_copy:
        on_switch = {}
    else:
        with open(baseline_path, encoding='utf-8') as f:
            on_switch = json.load(f)

    def save_photo():
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(on_switch, f)

    local = photo(patch)
    changed = sorted(k for k in local if on_switch.get(k) != local[k])
    # the song lists last: until every file of the new songs is there, the console keeps listing the songs it has
    changed.sort(key=lambda k: os.path.basename(k).startswith('songs_') and k.endswith('.json'))
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

    entries = remote.listing()
    if first_copy:
        if entries:
            sys.exit(f"{url} already has {len(entries)} item(s) (e.g. {entries[:3]}): --first-copy only copies to a "
                     f"folder that is missing or empty. Empty it first, or pass --baseline.")
        if entries is None and not remote.parent_listing():
            sys.exit(f"Can't open {url.rsplit('/', 1)[0]}: is the Switch connected with {how}?")
        print(f"First copy: {url} is {'empty' if entries is not None else 'not there yet'}.")
        if not args.apply:
            print("Run again with --apply to copy.")
            return
        if entries is None:
            remote.make_root()
    # is the Switch really at the photo? check a sample of the unchanged files
    elif entries is None:
        sys.exit(f"Can't open {url}: is the Switch connected with {how}?")
    # what the photo says the Switch has (unchanged files first; after a rename almost everything changes)
    unchanged = [k for k in local if k not in changed and k in on_switch]
    others = [k for k in on_switch if k not in unchanged]
    sample = random.sample(unchanged, min(args.sample, len(unchanged)))
    sample += random.sample(others, min(args.sample - len(sample), len(others)))
    wrong = [k for k in sample if remote.size(k) != on_switch[k][0]]
    if wrong:
        sys.exit(f"The Switch does not have the expected patch ({len(wrong)} of {len(sample)} checked files differ, "
                 f"e.g. {wrong[:3]}). Nothing copied: copy the whole folder once instead.")
    print(f"Switch checked: {len(sample)} files match the photo.")
    if not args.apply:
        print("Run again with --apply to copy.")
        return

    backup = os.path.join(keep_dir, f"switch_backup_{time.strftime('%Y-%m-%d_%H%M%S')}")

    def back_up(k):
        dest = os.path.join(backup, k)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        return remote.get(k, dest) and os.path.getsize(dest) == on_switch[k][0]

    made = set()
    if args.prune_first and removed:
        # the console keeps its previous song list (songs_xx.json is copied last) but its songs lose their files
        # until the copy ends: do not play meanwhile
        in_patch = {tuple(v) for v in local.values()}
        for k in removed:
            if not (k.endswith('.bk2') and tuple(on_switch[k]) in in_patch):  # videos already in the patch: no copy
                if not back_up(k) and remote.size(k) is not None:
                    sys.exit(f"Could not back up {k} from the Switch: nothing else removed.")
            if remote.remove(k):
                del on_switch[k]
                save_photo()
        print(f"   {len(removed)} old file(s) removed from the Switch first", flush=True)
        removed = []
    started, sent = time.time(), 0
    for n, k in enumerate(changed, 1):
        if k in on_switch:  # keep what the Switch had
            if not back_up(k):
                sys.exit(f"Could not back up {k} from the Switch: stopped before changing anything else.")
        else:
            make_dirs(remote, k, made)
        ok, error = remote.put(os.path.join(patch, k), k)
        got = remote.size(k)
        if not ok or got != local[k][0]:
            sys.exit(f"Copy of {k} failed ({error}); the Switch keeps the other files. "
                     f"Backup of the replaced files: {backup}")
        on_switch[k] = local[k]
        sent += local[k][0]
        speed = sent / max(time.time() - started, 1) / 2**20
        print(f"   [{n}/{len(changed)}] copied {k} ({speed:.1f} MB/s)", flush=True)
        save_photo()  # after every file: a cut leaves it consistent
    if args.prune:
        for k in removed:
            if not back_up(k) and remote.size(k) is not None:
                print(f"   could not back up {k}: left on the Switch")
                continue
            if remote.remove(k):
                del on_switch[k]
                save_photo()
            else:
                print(f"   could not remove {k}")
        print(f"   {len(removed)} old file(s) removed from the Switch (backed up)")
    print(f"Done. Previous versions saved in {backup}" if os.path.isdir(backup) else "Done.")


if __name__ == '__main__':
    main()
