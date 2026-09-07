#!/usr/bin/env python3
"""
Mission Engineering Auto-Dispatch.

A Mission reaching "Approved for Engineering" status used to only trigger
a Slack/Telegram notification (core/command-centre/backend/services/
notification-engine.js) telling a human to go implement it — nothing
actually dispatched the work. This closes that gap by watching for
Approved-for-Engineering Missions and dispatching them to the platform's
one real AI-coding pipeline (core/engineering/batch_coding.py's
`sync-one`), the exact same mechanism auto_remediation.py's
HandoffPRStrategy already uses for approved findings.

Writes the same ENG-HANDOFF-*.md format HandoffPRStrategy writes, so
core/coordination/engineering_handoff_reader.py's existing read-only
status surfacing into Number One's advisory queue picks these up for
free — no new UI needed there.

Never commits to main: batch_coding.py sync-one always opens a **draft**
GitHub PR for human review, matching the platform's only existing
precedent for AI-authored code changes (same guarantee HandoffPRStrategy
relies on). A hard fence against CI/CD config and anything
credential-shaped lives in batch_coding._is_fenced_path, applied
regardless of what dispatched the handoff.

Idempotent: tracks dispatched mission_ids in a local JSONL log so the
same Mission is never dispatched twice, even across repeated runs — no
new Supabase column or migration needed for this first pass.

CLI:
    python3 mission_dispatch.py [--dry-run] [--data-root PATH] [--repo-root PATH]

2026-09-06: (Platform Registry correction) the Registry's Engineering
Runtime entry lists core/coordination/telegram_build_executor.py as the
`/build` flow's consumer — that file does not exist in this repo; the
Telegram bot that used it is retired (telegram-bot.DEPRECATED-2026-07-12/
eng_operator.py). batch_coding.py sync-one, invoked directly, is the real,
current, live entry point — confirmed by reading auto_remediation.py's
HandoffPRStrategy, which already uses exactly this path in production.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "core" / "platform"))
from heartbeat import supabase_get  # noqa: E402

log = logging.getLogger("mission_dispatch")

APPROVED_STATUS = "Approved for Engineering"
DISPATCH_LOG_NAME = "mission_dispatch_log.jsonl"


def fetch_approved_missions(limit: int = 25) -> list[dict[str, Any]]:
    """Missions currently sitting at APPROVED_STATUS. Never raises — a
    Supabase read failure here must not crash the whole cycle; caller
    treats an empty list the same as "nothing to dispatch this run"."""
    try:
        path = (
            f"missions?select=mission_id,title,description,status,updated_at"
            f"&status=eq.{quote(APPROVED_STATUS)}&order=updated_at.asc&limit={limit}"
        )
        return supabase_get(path)
    except Exception as exc:
        log.warning(f"Failed to fetch Approved-for-Engineering missions: {exc}")
        return []


def load_dispatched_ids(data_root: Path) -> set[str]:
    log_path = data_root / "review" / DISPATCH_LOG_NAME
    if not log_path.exists():
        return set()
    ids: set[str] = set()
    try:
        with open(log_path) as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    mid = rec.get("mission_id")
                    if mid:
                        ids.add(mid)
    except Exception as exc:
        log.warning(f"Failed to read {log_path}: {exc}")
    return ids


def record_dispatch(data_root: Path, mission_id: str, success: bool, message: str) -> None:
    log_path = data_root / "review" / DISPATCH_LOG_NAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mission_id": mission_id,
        "success": success,
        "message": message,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def write_handoff_file(repo_root: Path, mission: dict[str, Any]) -> Path:
    """Same header/section format HandoffPRStrategy writes for a Finding,
    so engineering_handoff_reader.py treats these identically — it only
    ever reads the `- Status:`/`- Batch Status:`/`## Mission Title`
    sections, format-compatible regardless of what created the file."""
    mission_id = mission.get("mission_id", "UNKNOWN")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    handoff_id = f"ENG-HANDOFF-{mission_id}-{stamp}"
    handoffs_dir = repo_root / "Missions" / "Engineering-Handoffs"
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = handoffs_dir / f"{handoff_id}.md"

    title = mission.get("title") or mission_id
    description = mission.get("description") or "(no description recorded)"

    handoff_path.write_text(
        f"- Status: APPROVED_FOR_ENGINEERING\n"
        f"- Batch Status: PENDING\n"
        f"- Mission ID: {handoff_id}\n"
        f"- Priority: P3\n"
        f"- Batch Group: Mission Engineering Auto-Dispatch\n"
        f"\n## Mission Title\n{title}\n"
        f"\n## Summary\n{description}\n"
        f"\n## Rationale\n"
        f"Auto-dispatched from Mission {mission_id} on reaching "
        f"'{APPROVED_STATUS}' status.\n"
        f"\n## Suggested Next Step\nSee summary.\n"
        f"\n## Risks\n"
        f"Auto-generated by Mission Engineering Auto-Dispatch. Opened as a "
        f"draft PR only — review before merging, same as any other "
        f"batch-coded handoff.\n",
        encoding="utf-8",
    )
    return handoff_path


def dispatch_one(repo_root: Path, mission: dict[str, Any]) -> dict[str, Any]:
    """Exact same sync-one subprocess pattern HandoffPRStrategy.remediate()
    uses — same venv, same timeout, same result shape."""
    handoff_path = write_handoff_file(repo_root, mission)
    venv_python = repo_root / "platform-runtime" / ".venv" / "bin" / "python"
    try:
        result = subprocess.run(
            [str(venv_python), "-m", "core.engineering.batch_coding", "sync-one",
             "--handoff", str(handoff_path)],
            cwd=repo_root, capture_output=True, text=True, timeout=180,
        )
    except Exception as exc:
        return {"success": False, "error": f"sync-one subprocess failed: {exc}"}

    if result.returncode != 0:
        return {"success": False, "error": f"sync-one exited {result.returncode}: {result.stderr[-500:]}"}

    try:
        out = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"success": False, "error": f"sync-one produced unparseable output: {result.stdout[-500:]}"}

    if out.get("status") != "delivered":
        return {"success": False, "error": f"sync-one status={out.get('status')}: {out.get('error', '')}"}

    pr_url = out.get("pr_url") or ""
    return {
        "success": True,
        "message": (
            f"Draft PR opened for review: {pr_url}" if pr_url
            else f"Handoff coded (artifact: {out.get('artifact')}) but no PR opened "
                 f"(GitHub not configured or no new files to add) — review the artifact manually."
        ),
    }


def run_cycle(repo_root: Path, data_root: Path, dry_run: bool = False, limit: int = 25) -> dict[str, Any]:
    dispatched_before = load_dispatched_ids(data_root)
    missions = fetch_approved_missions(limit=limit)
    to_dispatch = [m for m in missions if m.get("mission_id") not in dispatched_before]

    results = {"checked": len(missions), "already_dispatched": len(missions) - len(to_dispatch),
               "dispatched": 0, "failed": 0, "dry_run": dry_run}

    for mission in to_dispatch:
        mission_id = mission.get("mission_id")
        if not mission_id:
            continue
        if dry_run:
            log.info(f"[dry-run] would dispatch {mission_id}: {mission.get('title')}")
            results["dispatched"] += 1
            continue

        outcome = dispatch_one(repo_root, mission)
        record_dispatch(data_root, mission_id, outcome["success"], outcome.get("message") or outcome.get("error", ""))
        if outcome["success"]:
            results["dispatched"] += 1
            log.info(f"{mission_id}: {outcome['message']}")
        else:
            results["failed"] += 1
            log.warning(f"{mission_id}: {outcome['error']}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch Approved-for-Engineering Missions to batch_coding.py")
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--data-root", type=Path, default=_REPO_ROOT / "data" / "self-improvement")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    results = run_cycle(args.repo_root, args.data_root, dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
