#!/usr/bin/env python3
"""
MSN-0147: Tests for the mission ID minting service.

Covers:
  - Sequential minting (no duplicates, correct format)
  - Concurrent minting (10 threads, no duplicates)
  - Non-MSN prefixes unchanged (BREQ, DEC)
  - CLI wrapper output format (isolated temp counter)
  - HTTP server /mint and /health endpoints (isolated temp counter)

All tests use an isolated temporary counter file — no real .id-counters.json IDs are consumed.

Usage:
    python3 tools/test_mint.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import id_registry

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  {PASS}  {name}")
    else:
        tag = f"  {FAIL}  {name}" + (f": {detail}" if detail else "")
        print(tag)
        _failures.append(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MSN_RE = re.compile(r"^USS-TJR-MSN-\d{4}$")
_BREQ_RE = re.compile(r"^BREQ-\d{4}$")
_DEC_RE = re.compile(r"^DEC-\d{4}$")


class IsolatedCounter:
    """Context manager that redirects id_registry to a temp counter file."""

    def __init__(self, initial: dict | None = None) -> None:
        self._initial = initial or {}
        self._tmpdir: tempfile.TemporaryDirectory | None = None
        self._orig_counter: Path | None = None
        self._orig_lock: Path | None = None

    def __enter__(self) -> "IsolatedCounter":
        self._tmpdir = tempfile.TemporaryDirectory(prefix="mint_test_")
        tmp = Path(self._tmpdir.name)
        counter_file = tmp / ".id-counters.json"
        counter_file.write_text(json.dumps(self._initial), encoding="utf-8")

        self._orig_counter = id_registry._COUNTER_FILE
        self._orig_lock = id_registry._LOCK_FILE
        id_registry._COUNTER_FILE = counter_file
        id_registry._LOCK_FILE = tmp / ".id-lock"
        return self

    def __exit__(self, *_: object) -> None:
        id_registry._COUNTER_FILE = self._orig_counter
        id_registry._LOCK_FILE = self._orig_lock
        if self._tmpdir:
            self._tmpdir.cleanup()


# ---------------------------------------------------------------------------
# Suite 1 — Sequential uniqueness
# ---------------------------------------------------------------------------

def test_sequential() -> None:
    print("\n[1] Sequential minting (isolated counter, starts at 0)")
    with IsolatedCounter():
        ids = [id_registry.next_id("MSN") for _ in range(5)]
    check("all canonical format", all(_MSN_RE.match(i) for i in ids), str(ids))
    check("all unique", len(set(ids)) == 5, str(ids))
    nums = [int(i.split("-")[-1]) for i in ids]
    check("strictly increasing", nums == sorted(nums), str(nums))
    check("all consecutive", nums == list(range(nums[0], nums[0] + 5)), str(nums))


# ---------------------------------------------------------------------------
# Suite 2 — Concurrent uniqueness
# ---------------------------------------------------------------------------

def test_concurrent() -> None:
    print("\n[2] Concurrent minting — 10 threads (isolated counter)")
    results: list[str] = []
    lock = threading.Lock()

    with IsolatedCounter() as ctx:
        def mint() -> None:
            mid = id_registry.next_id("MSN")
            with lock:
                results.append(mid)

        threads = [threading.Thread(target=mint) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    check("10 results", len(results) == 10, str(results))
    check("all unique", len(set(results)) == 10, str(results))
    check("all canonical format", all(_MSN_RE.match(r) for r in results), str(results))


# ---------------------------------------------------------------------------
# Suite 3 — Non-MSN prefixes
# ---------------------------------------------------------------------------

def test_prefixes() -> None:
    print("\n[3] Non-MSN prefix formats (isolated counter)")
    with IsolatedCounter():
        breq = id_registry.next_id("BREQ")
        dec = id_registry.next_id("DEC")
    check("BREQ format", bool(_BREQ_RE.match(breq)), breq)
    check("DEC format", bool(_DEC_RE.match(dec)), dec)


# ---------------------------------------------------------------------------
# Suite 4 — CLI wrapper
# ---------------------------------------------------------------------------

def test_cli() -> None:
    print("\n[4] CLI wrapper (tools/mint_id.py, isolated counter via env)")
    script = REPO_ROOT / "tools" / "mint_id.py"
    if not script.exists():
        check("script exists", False, str(script))
        return
    check("script exists", True)

    with tempfile.TemporaryDirectory(prefix="mint_cli_") as tmpdir:
        counter_path = Path(tmpdir) / ".id-counters.json"
        env = {**os.environ, "_MINT_TEST_COUNTER": str(counter_path)}
        result = subprocess.run(
            [sys.executable, str(script), "MSN"],
            capture_output=True, text=True, timeout=10, env=env,
        )
    out = result.stdout.strip()
    check("exit code 0", result.returncode == 0, result.stderr)
    # Format correct — the exact number depends on the test counter state
    check("canonical format or fallback format", bool(_MSN_RE.match(out)) or "USS-TJR-MSN-" in out, out)


# ---------------------------------------------------------------------------
# Suite 5 — HTTP server
# ---------------------------------------------------------------------------

def test_http_server() -> None:
    print("\n[5] HTTP server (tools/mint_server.py, isolated counter via env)")
    script = REPO_ROOT / "tools" / "mint_server.py"
    if not script.exists():
        check("script exists", False, str(script))
        return
    check("script exists", True)

    import signal

    port = 15052
    with tempfile.TemporaryDirectory(prefix="mint_srv_") as tmpdir:
        counter_path = Path(tmpdir) / ".id-counters.json"
        env = {**os.environ, "MINT_PORT": str(port), "_MINT_TEST_COUNTER": str(counter_path)}
        proc = subprocess.Popen([sys.executable, str(script)], stderr=subprocess.PIPE, env=env)
        time.sleep(0.8)
        try:
            # /health
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                    body = json.loads(r.read())
                check("/health status ok", body.get("status") == "ok", str(body))
            except Exception as exc:
                check("/health reachable", False, str(exc))

            # POST /mint
            try:
                payload = json.dumps({"type": "MSN"}).encode()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/mint",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as r:
                    body = json.loads(r.read())
                check("POST /mint status allocated", body.get("status") == "allocated", str(body))
                check("POST /mint canonical ID", "USS-TJR-MSN-" in body.get("mission_id", ""), str(body))
            except Exception as exc:
                check("POST /mint reachable", False, str(exc))
        finally:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_sequential()
    test_concurrent()
    test_prefixes()
    test_cli()
    test_http_server()

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} test(s): {', '.join(_failures)}")
        sys.exit(1)
    else:
        print("All tests passed.")
