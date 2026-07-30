"""In-memory stand-in for RemoteTransport — no network, no subprocess.

Mirrors the duck-typed interface engine.TransferEngine depends on:
ensure_remote_dirs, rsync_push, push_text_file, verify_checksums,
run_remote_script.
"""


class FakeTransport:
    def __init__(self, rsync_results=None, checksum_overrides=None):
        # rsync_results: {source_name: [(rc, out, err), ...]} consumed in order,
        # one entry popped per rsync_push call for that source; once exhausted,
        # defaults to success.
        self.rsync_results = rsync_results or {}
        # checksum_overrides: {source_name: {rel_path: bool_ok}} — anything not
        # listed defaults to OK.
        self.checksum_overrides = checksum_overrides or {}

        self.calls = []
        self.ensure_dirs_calls = 0
        self.pushed_files = {}
        self.moved_scripts = []

    def ensure_remote_dirs(self):
        self.ensure_dirs_calls += 1
        return 0, "", ""

    def rsync_push(self, local_root, remote_dir, rel_paths, dry_run=False, extra_args=None):
        self.calls.append(("rsync_push", str(local_root), remote_dir, list(rel_paths), dry_run))
        source = remote_dir.rstrip("/").split("/")[-1]
        seq = self.rsync_results.get(source)
        if seq:
            return seq.pop(0)
        return 0, "sent", ""

    def push_text_file(self, remote_path, content):
        self.pushed_files[remote_path] = content
        return 0, "", ""

    def verify_checksums(self, remote_dir, checksums_text):
        self.calls.append(("verify_checksums", remote_dir, checksums_text))
        source = remote_dir.rstrip("/").split("/")[-1]
        overrides = self.checksum_overrides.get(source, {})
        lines = []
        for line in checksums_text.splitlines():
            if not line.strip():
                continue
            _sha, rel = line.split("  ", 1)
            ok = overrides.get(rel, True)
            lines.append(f"{rel}: {'OK' if ok else 'FAILED'}")
        return 0, "\n".join(lines), ""

    def run_remote_script(self, script, stdin_text=None):
        self.calls.append(("run_remote_script", script))
        self.moved_scripts.append(script)
        return 0, "", ""
