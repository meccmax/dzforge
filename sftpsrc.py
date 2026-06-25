"""
Remote SFTP source for DZ Forge, driven through Windows' built-in (Microsoft-signed)
sftp.exe so Smart App Control allows it. Key-based auth only (password auth can't be fed
to sftp.exe non-interactively under SAC). Backups of remote files are kept locally.
"""
import os, subprocess, tempfile, time

SFTP = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "sftp.exe")
HERE = os.path.dirname(os.path.abspath(__file__))
# Trust-on-first-use: remember each server's SSH host key and refuse to connect if it
# later changes (detects a man-in-the-middle), instead of blindly ignoring host keys.
KNOWN_HOSTS = os.path.join(HERE, ".dzforge_known_hosts")


class SftpConn:
    def __init__(self, host, port, user, key, base):
        self.host = host
        self.port = int(port or 22)
        self.user = user
        self.key = os.path.expanduser(key)
        self.base = base or "."

    def _run(self, batch, timeout=45):
        bf = os.path.join(tempfile.gettempdir(), f"dz_sftp_{int(time.time()*1000)}.txt")
        with open(bf, "w", encoding="utf-8") as f:
            f.write(batch)
        try:
            args = [SFTP, "-i", self.key, "-P", str(self.port),
                    "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                    "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
                    "-b", bf, f"{self.user}@{self.host}"]
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout, r.stderr
        finally:
            try: os.remove(bf)
            except OSError: pass

    def listdir(self, path):
        rc, out, err = self._run(f'ls -la "{path}"\n')
        if rc != 0:
            raise RuntimeError(err.strip() or "sftp ls failed")
        entries = []
        for line in out.splitlines():
            if line.startswith("sftp>") or not line.strip():
                continue
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue
            name = parts[8].rstrip()
            if name in (".", ".."):
                continue
            entries.append({"name": name, "dir": parts[0].startswith("d")})
        return entries

    def read(self, path):
        tmp = os.path.join(tempfile.gettempdir(), f"dz_get_{int(time.time()*1000)}")
        rc, out, err = self._run(f'get "{path}" "{tmp}"\n')
        if rc != 0 or not os.path.exists(tmp):
            raise RuntimeError(err.strip() or "sftp get failed")
        try:
            with open(tmp, "r", encoding="utf-8-sig") as f:
                return f.read()
        finally:
            try: os.remove(tmp)
            except OSError: pass

    def pull(self, remote_dir, local_parent):
        """Recursively download remote_dir into local_parent (creates local_parent/<name>)."""
        os.makedirs(local_parent, exist_ok=True)
        rc, out, err = self._run(f'get -r "{remote_dir}" "{local_parent}"\n', timeout=900)
        if rc != 0:
            raise RuntimeError(err.strip() or "sftp get -r failed")

    def get_into(self, remote_glob, local_dir):
        """Download files matching remote_glob into local_dir (no error if nothing matches)."""
        os.makedirs(local_dir, exist_ok=True)
        self._run(f'get "{remote_glob}" "{local_dir}"\n', timeout=300)

    def write(self, path, content):
        backup = "(new file)"
        try:
            orig = self.read(path)
            bdir = os.path.join(HERE, ".dzforge-remote-backups")
            os.makedirs(bdir, exist_ok=True)
            backup = os.path.join(bdir, f"{os.path.basename(path)}.{int(time.time())}.bak")
            with open(backup, "w", encoding="utf-8") as f:
                f.write(orig)
        except Exception:
            pass  # new file or unreadable original
        tmp = os.path.join(tempfile.gettempdir(), f"dz_put_{int(time.time()*1000)}")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        try:
            rc, out, err = self._run(f'put "{tmp}" "{path}"\n')
            if rc != 0:
                raise RuntimeError(err.strip() or "sftp put failed")
        finally:
            try: os.remove(tmp)
            except OSError: pass
        return backup
