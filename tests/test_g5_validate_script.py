"""SEC-01 G5: guard tests for deploy/caddy/g5_validate.sh.

The dry-run is executed with a stub `curl` on PATH that logs its argv. The
--live section is only parsed as text. No test runs --live or opens a socket.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "deploy" / "caddy" / "g5_validate.sh"
TEXT = SCRIPT.read_text(encoding="utf-8")
LIVE_IF = "if [ $LIVE -eq 0 ]"
READS_EXPECTED = [
    "/self-improvement/api/findings",
    "/self-improvement/api/opportunities",
    "/self-improvement/api/evolution-summary",
    "/self-improvement/api/mission-dispatch-status",
    "/self-improvement/api/engineering-handoffs",
    "/self-improvement/api/status",
    "/self-improvement/",
]
WRITES_EXPECTED = [
    "/self-improvement/api/decide",
    "/self-improvement/api/opportunity/decide",
    "/api/self-improvement/decide",
    "/api/self-improvement/opportunities/decide",
]


def _block_bounds() -> tuple[int, int]:
    """Offsets of the dry-run `if` block: its start and the end of its closing `fi`."""
    start = TEXT.index(LIVE_IF)
    return start, TEXT.index("\nfi\n", start) + len("\nfi\n")


def _live_curl_lines() -> list[str]:
    _, end = _block_bounds()
    return [line for line in TEXT[end:].splitlines() if "curl" in line]


def _array(name: str) -> list[str]:
    match = re.search(rf"^{name}=\((.*)\)\s*$", TEXT, re.MULTILINE)
    assert match, f"{name}=( ... ) array not found"
    return match.group(1).split()


def test_script_exists_executable_and_parses() -> None:
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)
    result = subprocess.run(["bash", "-n", str(SCRIPT)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_dry_run_no_args_sends_nothing(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "curl.log"
    stub = bindir / "curl"
    stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" >> "{log}"\nexit 0\n', encoding="utf-8")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
    result = subprocess.run([str(SCRIPT)], check=False, capture_output=True, text=True, env=env, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN" in result.stdout
    assert not [ln for ln in result.stdout.splitlines() if ln.startswith(("PASS", "FAIL"))]
    assert not log.exists(), "curl was invoked during the dry-run"


def test_curl_only_in_live_section() -> None:
    start, end = _block_bounds()
    assert "curl" not in TEXT[start:end], "dry-run block must not contain curl"
    offsets = [m.start() for m in re.finditer("curl", TEXT)]
    assert offsets and all(off >= end for off in offsets)


def test_no_valid_secret_or_auth_header() -> None:
    assert "SELF_IMPROVEMENT_API_SECRET" not in TEXT
    assert "authorization" not in TEXT.lower()
    assert re.search(r'^PROBE="[^"]+"$', TEXT, re.MULTILINE), "PROBE constant missing"
    post_lines = [line for line in _live_curl_lines() if "-X POST" in line]
    assert len(post_lines) == 1
    assert "$PROBE" in post_lines[0]


def test_read_list_matches_documented_paths() -> None:
    assert _array("READS") == READS_EXPECTED


def test_write_list_matches_documented_paths() -> None:
    assert _array("WRITES") == WRITES_EXPECTED


def test_live_curl_methods_are_safe() -> None:
    lines = _live_curl_lines()
    assert len(lines) == 4, lines
    for line in lines:
        match = re.search(r"-X\s+(\S+)", line)
        method = match.group(1) if match else "GET"
        assert method in {"GET", "OPTIONS", "POST"}, line
        if "-H" in line:
            assert method == "POST" and "$PROBE" in line, line


def test_no_mutating_methods_anywhere() -> None:
    assert not re.search(r"-X\s*(PUT|PATCH|DELETE)\b", TEXT, re.IGNORECASE)
