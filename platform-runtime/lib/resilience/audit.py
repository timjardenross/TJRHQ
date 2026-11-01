"""Append-only audit trail for crosswalk runs and the Captain's review decisions.

One JSON object per line. A run record captures what produced the output (prompt
version, knowledge-pack hash, corpus fingerprint) so any crosswalk can be traced
later; a review record captures the human accept / edit / reject decision.

Path: ``RESILIENCE_AUDIT_LOG`` env var, default ``data/resilience-crosswalk/audit.jsonl``.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .corpus import REPO_ROOT

DEFAULT_AUDIT_PATH = REPO_ROOT / "data" / "resilience-crosswalk" / "audit.jsonl"
REVIEW_DECISIONS = {"accepted", "edited", "rejected"}


def audit_path() -> Path:
    override = os.getenv("RESILIENCE_AUDIT_LOG")
    return Path(override) if override else DEFAULT_AUDIT_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(record: dict, path: Path | None = None) -> None:
    target = path or audit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def new_run_id() -> str:
    return f"xw-{uuid.uuid4().hex[:12]}"


def record_run(run: dict, path: Path | None = None) -> None:
    _append({"type": "run", "recorded_at": _now(), **run}, path)


def record_review(run_id: str, decision: str, note: str = "", path: Path | None = None) -> None:
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(REVIEW_DECISIONS)}")
    _append({"type": "review", "recorded_at": _now(), "run_id": run_id,
             "decision": decision, "note": note}, path)


def read_log(path: Path | None = None) -> list[dict]:
    target = path or audit_path()
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def unreviewed_runs(path: Path | None = None) -> list[str]:
    """Run IDs with a produced crosswalk but no review decision yet."""
    records = read_log(path)
    reviewed = {r["run_id"] for r in records if r.get("type") == "review"}
    return [r["run_id"] for r in records
            if r.get("type") == "run" and r.get("status") == "ok" and r["run_id"] not in reviewed]
