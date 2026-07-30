"""SSH/rsync transport for the Secure File Transfer to VM agent
(USS-TJR-MSN-0205B).

Shells out to the system `ssh` and `rsync` binaries — key-based auth only,
no bundled credentials. All remote paths that get interpolated into a
remote shell command are quoted with shlex.quote(); the outer ssh/rsync
invocations themselves are run as argument lists (no shell=True), so this
process never shell-interprets locally-controlled input.

Engine code depends on this only by duck-typed method signatures
(ensure_remote_dirs, rsync_push, push_text_file, verify_checksums,
run_remote_script) so tests can substitute a fake transport with no
network access.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

REMOTE_SUBDIRS = ("pending", "received", "failed", "archive", "pending/_manifests")


class RemoteCommandError(RuntimeError):
    def __init__(self, message, returncode, stdout, stderr):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RemoteTransport:
    def __init__(self, remote_config):
        self.remote = remote_config

    def _ssh_base_args(self):
        args = ["ssh", "-p", str(self.remote.port)]
        if self.remote.ssh_key:
            args += ["-i", str(Path(self.remote.ssh_key).expanduser())]
        args += [
            "-o", f"StrictHostKeyChecking={self.remote.strict_host_key_checking}",
            "-o", f"ConnectTimeout={self.remote.connect_timeout}",
            "-o", "BatchMode=yes",
        ]
        return args

    def _target(self):
        return f"{self.remote.user}@{self.remote.host}"

    def ensure_remote_dirs(self):
        quoted = " ".join(
            shlex.quote(f"{self.remote.base_path}/{d}") for d in REMOTE_SUBDIRS
        )
        return self.run_remote_script(f"mkdir -p {quoted}")

    def run_remote_script(self, script: str, stdin_text: str = None):
        # ssh concatenates all trailing argv elements with spaces and re-parses
        # the result with the remote login shell before our intended "bash -c
        # <script>" ever runs — passing them as separate argv items (the old
        # ["bash", "-c", script] form) silently loses "&&"/"cd"/redirection
        # semantics inside `script` to that outer re-parse. Collapsing to a
        # single pre-quoted command string is the only form ssh passes through
        # to the remote shell intact.
        remote_cmd = f"bash -c {shlex.quote(script)}"
        cmd = self._ssh_base_args() + [self._target(), remote_cmd]
        proc = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def push_text_file(self, remote_path: str, content: str):
        remote_cmd = f"bash -c {shlex.quote(f'cat > {shlex.quote(remote_path)}')}"
        cmd = self._ssh_base_args() + [self._target(), remote_cmd]
        proc = subprocess.run(cmd, input=content, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def rsync_push(self, local_root: Path, remote_dir: str, rel_paths, dry_run=False, extra_args=None):
        if not rel_paths:
            return 0, "", ""
        fd, list_path = tempfile.mkstemp(suffix=".txt", prefix="vm-transfer-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write("\n".join(rel_paths) + "\n")

            ssh_cmd = " ".join(shlex.quote(a) for a in self._ssh_base_args())
            cmd = ["rsync", "-az", "--files-from", list_path, "-e", ssh_cmd]
            if dry_run:
                cmd.append("--dry-run")
            cmd += list(extra_args or [])
            local_src = str(local_root).rstrip("/") + "/"
            cmd += [local_src, f"{self._target()}:{remote_dir}/"]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            return proc.returncode, proc.stdout, proc.stderr
        finally:
            os.unlink(list_path)

    def verify_checksums(self, remote_dir: str, checksums_text: str):
        script = f"cd {shlex.quote(remote_dir)} && sha256sum -c -"
        return self.run_remote_script(script, stdin_text=checksums_text)
