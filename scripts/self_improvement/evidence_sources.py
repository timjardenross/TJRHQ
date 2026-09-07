"""
Thin, read-only evidence readers for HQ Evolution's outcome loop (V2
sections 12-13): "domain owns its data and interpretation, consumers read
a small stable assessed output." This module never imports another
workbench's ingestion/reasoning code, never writes to another domain's
store, and never raises — every reader degrades to
{"available": False, "reason": ...} on any failure, since a missing metric
must become an honest "unknown", never a fabricated baseline (section 8).

Sources covered (deliberately narrow — see HQ-EVOLUTION.md's V2 audit for
why these three and not more):
  - the Model Router's own call_log.jsonl (bounded tail-read)
  - domain_heartbeats (via core/platform/heartbeat.py's existing
    supabase_get — the same thin client every other job already uses)
  - the missions table (status only — the canonical mission lifecycle)
  - a local file-size check (for internal_discovery.py's own
    measurement_hint candidates, e.g. call_log.jsonl's own size)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core" / "platform"))
from heartbeat import supabase_get  # noqa: E402

log = logging.getLogger("evidence_sources")

_MAX_LOG_TAIL_LINES = 20_000  # bounded read of call_log.jsonl — never load an unbounded file


def file_size_mb(path: Path) -> dict[str, Any]:
    """Deterministic, local, no network — used for internal_discovery.py's
    own measurement_hint candidates (e.g. call_log.jsonl's own size)."""
    try:
        if not path.exists():
            return {"available": True, "value": 0.0, "description": f"{path.name} does not exist (0 MB)"}
        size_mb = path.stat().st_size / (1024 * 1024)
        return {"available": True, "value": round(size_mb, 3), "description": f"{path.name} is {size_mb:.2f}MB"}
    except OSError as exc:
        return {"available": False, "reason": f"Could not stat {path}: {exc}"}


def model_router_call_stats(repo_root: Path, task_type: Optional[str] = None) -> dict[str, Any]:
    """Bounded tail-read of core/model-router/call_log.jsonl. Returns
    aggregate call count / success rate / avg duration, optionally filtered
    to one task_type. Never loads the whole file into memory unbounded —
    reads at most the last _MAX_LOG_TAIL_LINES lines."""
    log_path = repo_root / "core" / "model-router" / "call_log.jsonl"
    if not log_path.exists():
        return {"available": False, "reason": "call_log.jsonl does not exist"}

    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            # Read from the end in a bounded chunk rather than the whole file.
            chunk_size = min(file_size, 8 * 1024 * 1024)  # 8MB cap
            f.seek(max(0, file_size - chunk_size))
            raw = f.read().decode("utf-8", errors="ignore")
    except OSError as exc:
        return {"available": False, "reason": f"Could not read call_log.jsonl: {exc}"}

    lines = raw.splitlines()[-_MAX_LOG_TAIL_LINES:]
    entries = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if task_type:
        entries = [e for e in entries if e.get("task_type") == task_type]

    if not entries:
        return {"available": False, "reason": f"No call_log.jsonl entries found{f' for task_type={task_type}' if task_type else ''}"}

    success_count = sum(1 for e in entries if e.get("success"))
    durations = [e["duration_ms"] for e in entries if isinstance(e.get("duration_ms"), (int, float))]
    return {
        "available": True,
        "count": len(entries),
        "success_count": success_count,
        "failure_count": len(entries) - success_count,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "window_start": entries[0].get("ts"),
        "window_end": entries[-1].get("ts"),
        "sample_note": f"last {len(entries)} call(s) in the bounded tail read"
                       + (f", filtered to task_type={task_type}" if task_type else ", all task types (no specific task_type identified for this opportunity)"),
    }


def domain_heartbeat_stats(domain_key: str, limit: int = 20, timeout: int = 10) -> dict[str, Any]:
    """Recent domain_heartbeats rows for one domain_key — job success/
    failure/latency, the same table Agent & Job Status itself reads.
    Degrades to unavailable if Supabase credentials aren't configured in
    this process (matches heartbeat.py's own convention)."""
    try:
        rows = supabase_get(
            f"domain_heartbeats?select=status,checked_at,latency_ms&domain_key=eq.{domain_key}"
            f"&order=checked_at.desc&limit={limit}",
            timeout=timeout,
        )
    except RuntimeError as exc:
        return {"available": False, "reason": str(exc)}

    if not rows:
        return {"available": False, "reason": f"No domain_heartbeats rows for domain_key={domain_key}"}

    success_count = sum(1 for r in rows if r.get("status") == "ok")
    latencies = [r["latency_ms"] for r in rows if isinstance(r.get("latency_ms"), (int, float))]
    return {
        "available": True,
        "count": len(rows),
        "success_count": success_count,
        "failure_count": len(rows) - success_count,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "most_recent_checked_at": rows[0].get("checked_at"),
        "sample_note": f"last {len(rows)} heartbeat(s) for {domain_key}",
    }


def mission_status(mission_id: str, timeout: int = 10) -> dict[str, Any]:
    """Status only — the canonical mission lifecycle, read thin (section 13:
    consume the assessed output, don't take ownership of Missions' data)."""
    try:
        rows = supabase_get(f"missions?select=status,updated_at&mission_id=eq.{mission_id}", timeout=timeout)
    except RuntimeError as exc:
        return {"available": False, "reason": str(exc)}

    if not rows:
        return {"available": False, "reason": f"No mission row for mission_id={mission_id}"}

    return {"available": True, "status": rows[0].get("status"), "updated_at": rows[0].get("updated_at")}


# Statuses that mean "the Mission's implementation work is done" — good
# enough signal to start the observation window. "Closed"/"Archived" are
# deliberately excluded from this READY set even though they're terminal:
# a mission can close without ever having been implemented (abandoned,
# superseded), and that must never be misread as "implemented".
MISSION_IMPLEMENTED_STATUSES = frozenset({"Implemented", "Tested", "Validated"})


def read_measurement(hint: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Dispatch a measurement_hint (set by a discovery module, e.g.
    internal_discovery.py's call-log-size candidate) to the matching
    reader. The SAME hint is read once at baseline-capture time and once
    at evaluation time — apples to apples, never two different metrics."""
    hint_type = hint.get("type")
    if hint_type == "file_size_mb":
        return file_size_mb(repo_root / hint["path"])
    if hint_type == "model_router_call_count":
        return model_router_call_stats(repo_root, task_type=hint.get("task_type"))
    if hint_type == "domain_heartbeat_success_rate":
        return domain_heartbeat_stats(hint["domain_key"], limit=hint.get("limit", 20))
    log.warning(f"Unknown measurement_hint type: {hint_type!r}")
    return {"available": False, "reason": f"Unknown measurement_hint type: {hint_type!r}"}
