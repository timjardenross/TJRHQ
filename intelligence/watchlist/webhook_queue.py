"""
Webhook-to-collection bridge — the queue that decouples a push-notification
receiver (changedetection_webhook.py, uptime_kuma_webhook.py) from the
pull-based collection cycle (collection_engine.collect_all()).

Why a queue, and not a direct write into the pipeline from the webhook
handler itself: changedetection.io and Uptime Kuma are each a separate,
persistent, single-process Docker container that does its OWN real polling
of the watched target on its OWN schedule — the actual "diff-watching" and
"up/down probing" this mission asks for already happened by the time either
service fires its webhook. This process's job is only to receive that real
event, normalise it, and hold it until the next scheduled collection run
picks it up through collection_engine.py's *existing* adapter contract
(SourceRecord in, list[IntelligenceItem] out) — the same contract every
other source in this codebase uses (see downdetector_adapter.py). A queue
is what makes that possible without changing collect_all()'s synchronous,
pull-driven shape: the webhook process (which may not even be running in
the same Python process as the scheduler) appends; the adapter's collect()
call, next cycle, drains.

Storage: flat JSONL under intelligence/watchlist/_queue/<name>.jsonl — no
new infra dependency for what is, at expected volume (a handful of watched
pages/monitors), a tiny amount of state. Each record carries a
`source_url` so one shared queue file per signal TYPE (not per source) can
still be drained per-SOURCE by the matching adapter instance — mirrors how
one adapter class in this codebase (e.g. DowndetectorAdapter) is
instantiated once per registered source but shares one module.

Best-effort throughout: a queue read/write failure must never break the
webhook receiver's HTTP response (the sending service would just retry/log
a failed notification) nor the adapter's collect() (a collection cycle
proceeding with zero items for this source is the same safe "quiet"
outcome as a source with nothing new to report).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)

QUEUE_DIR = Path(__file__).parent / "_queue"

# One process-local lock per queue name — good enough for this queue's real
# concurrency profile (one webhook receiver process appending, one
# collection-cycle thread draining; collection_engine.py's own
# ThreadPoolExecutor could run multiple adapters of the same class
# concurrently against different sources, so this still matters).
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(queue_name: str) -> threading.Lock:
    with _locks_guard:
        if queue_name not in _locks:
            _locks[queue_name] = threading.Lock()
        return _locks[queue_name]


def _queue_path(queue_name: str) -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    return QUEUE_DIR / f"{queue_name}.jsonl"


def append_signal(queue_name: str, record: dict) -> None:
    """Append one normalised signal record. Called by a webhook receiver on
    every real inbound notification. Never raises — a write failure here
    should not turn into a 500 back to changedetection.io/Uptime Kuma's own
    notification-delivery logic (both treat a non-2xx as a failed
    notification and may retry/alert on it, which is noisy for something
    that isn't the target site's fault)."""
    try:
        path = _queue_path(queue_name)
        line = json.dumps(record, default=str)
        with _lock_for(queue_name), open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:  # noqa: BLE001 - generic queue-append wrapper, already logged; a write failure means this webhook event is dropped, an accepted degrade per this queue's best-effort design
        log.error("[webhook_queue] failed to append to %s: %s", queue_name, exc)


def drain_signals(queue_name: str, source_url: str | None = None) -> list[dict]:
    """Return and remove every queued record for `queue_name`, optionally
    filtered to one `source_url` (leaving records for other sources/watches
    in the same queue file untouched — one adapter instance per registered
    source drains only its own). Returns [] (never raises) on any failure
    or when the queue file doesn't exist yet, which is the correct "nothing
    new" state for collect()."""
    path = _queue_path(queue_name)
    if not path.exists():
        return []

    with _lock_for(queue_name):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
        except Exception as exc:  # noqa: BLE001 - generic queue-read wrapper — caller sees [] and handles it; already logged
            log.error("[webhook_queue] failed to read %s: %s", queue_name, exc)
            return []

        matched: list[dict] = []
        remaining: list[str] = []
        for ln in lines:
            try:
                rec = json.loads(ln)
            except Exception:  # noqa: BLE001 - per-line parse inside a batch loop — one malformed line must not abort the drain; already logged and the line is dropped
                log.warning("[webhook_queue] dropping unparseable line in %s", queue_name)
                continue
            if source_url is None or rec.get("source_url") == source_url:
                matched.append(rec)
            else:
                remaining.append(ln)

        try:
            _atomic_rewrite(path, remaining)
        except Exception as exc:  # noqa: BLE001 - best-effort rewrite-after-drain, already logged; comment below documents the accepted at-most-once-more-reread tradeoff
            log.error(
                "[webhook_queue] failed to rewrite %s after drain (matched "
                "records are still returned this once, but may be re-read "
                "next cycle if the file wasn't actually truncated): %s",
                queue_name, exc,
            )

        return matched


def _atomic_rewrite(path: Path, lines: list[str]) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".jsonl")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def peek_count(queue_name: str) -> int:
    """Diagnostic only — total queued records across all sources for this
    queue name, without draining. Used by health checks / manual debugging."""
    path = _queue_path(queue_name)
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for ln in f if ln.strip())
    except Exception as exc:  # noqa: BLE001 - read-only health-check/debug helper; caller treats 0 as "queue empty or unreadable", worth a trace either way
        log.debug("[webhook_queue] failed to count %s: %s", queue_name, exc)
        return 0
