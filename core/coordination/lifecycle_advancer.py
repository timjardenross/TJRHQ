"""MSN-0066 Increment 6 — Lifecycle Advancer (write-side, stops AT the gate).

This is the one piece that *moves* an item rather than only observing it: once a
Capture-stage item has been enriched (its triage package generated), the advancer
transitions it to **Triage Ready** — "triaged, awaiting the Captain's decision" —
so it advances on the board up to Gate 1 and then STOPS. It never crosses the
gate: it cannot record `approved`, cannot assign, cannot run engineering.

WHY IT IS SAFE (the design that keeps a write-side governance-clean):
  * It writes to an ORCHESTRATION OVERLAY ledger
    (USS-TJR-Control/logs/missions/triage-ready/ledger.json) — NOT the missions
    table, NOT the BREQ markdown the executor parses, NOT the build_request_inbox
    approval rows. So it cannot disturb the `/approve` path (which resolves a
    request by file + a blind marker INSERT, never by status) or the executor.
  * It is fully reversible — delete a ledger entry and the move is undone.
  * Target stage is hard-pinned to "Triage Ready" and asserted to be OUTSIDE a
    forbidden set of post-gate / execution states. Approval stays 100% human
    (ADR-013: Number One recommends, XO decides).
  * Advancement is GATED ON ENRICHMENT: an item is only moved once its triage
    package (duplicates/risk/complexity) exists — preparation before the gate.
  * Dry-run by default; `apply=True` writes the overlay + an audit record.
  * Idempotent: an item already Triage Ready is never re-advanced.

CLI:
    python -m core.coordination.lifecycle_advancer report   # dry-run, no writes
    python -m core.coordination.lifecycle_advancer apply     # write the overlay
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.coordination import triage_package as tp

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEDGER_DIR = REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "triage-ready"
_AUDIT_DIR = REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "transitions"

# The ONLY stage this module may assign. Pinned + guarded so the write-side can
# never be widened into crossing the approval gate.
TRIAGE_READY = "Triage Ready"

# States the advancer must NEVER write — crossing the gate or executing. The
# module-load assertion below makes a regression here fail fast and loud.
_FORBIDDEN_TARGETS = {
    "approved", "engineering_running", "engineering_delivered", "Assigned",
    "Validated", "Awaiting XO Approval", "Closed", "Completed", "Archived",
}
assert TRIAGE_READY not in _FORBIDDEN_TARGETS, "advancer target must stop before the gate"


def _ledger_path(ledger_dir: Optional[Path] = None) -> Path:
    return (ledger_dir or _LEDGER_DIR) / "ledger.json"


def load_ledger(ledger_dir: Optional[Path] = None) -> dict[str, Any]:
    """Load the triage-ready overlay (item_id -> entry). Empty on any failure."""
    try:
        return json.loads(_ledger_path(ledger_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_ledger(ledger: dict[str, Any], ledger_dir: Optional[Path] = None) -> None:
    path = _ledger_path(ledger_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def list_triage_ready(ledger_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """The items currently parked at Triage Ready (awaiting the Captain)."""
    return list(load_ledger(ledger_dir).values())


def _audit(advanced: list[dict[str, Any]], ledger_dir: Optional[Path] = None) -> None:
    """Append a transition audit record (reuses the mission-transition log tree)."""
    try:
        audit_dir = (ledger_dir.parent / "transitions") if ledger_dir else _AUDIT_DIR
        audit_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        rec = {
            "transition": f"Capture -> {TRIAGE_READY}",
            "transitioned_by": "lifecycle_advancer (MSN-0066)",
            "transitioned_at": datetime.utcnow().isoformat() + "Z",
            "note": "Auto-advanced to the approval gate after triage enrichment; "
                    "NOT approved — awaiting Captain/XO/Number One decision.",
            "items": [a["id"] for a in advanced],
        }
        (audit_dir / f"TRIAGE-READY-ADVANCE-{ts}.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
    except OSError:
        pass


def advance(
    triage_report: Optional[dict[str, Any]] = None,
    apply: bool = False,
    ledger_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Advance enriched Capture items to Triage Ready. Dry-run unless apply=True.

    `triage_report` (triage_package.build_triage_packages output) is injectable;
    by default it is generated cheaply (no GLM). Each triaged item that is not
    already Triage Ready is advanced — recorded in the overlay with its risk /
    suggested priority / duplicate flag — and STOPS there for the human gate.
    """
    if triage_report is None:
        # Cheap enrichment for the gating decision: risk is local, GLM stays off.
        triage_report = tp.build_triage_packages(glm_fn=None)

    ledger = load_ledger(ledger_dir)
    results: list[dict[str, Any]] = []
    newly: list[dict[str, Any]] = []

    for pkg in triage_report.get("packages", []):
        item_id = str(pkg.get("id", ""))
        if not item_id:
            continue
        if item_id in ledger:
            results.append({"id": item_id, "action": "already_triage_ready"})
            continue
        entry = {
            "id": item_id,
            "title": pkg.get("title", ""),
            "kind": pkg.get("kind", ""),
            "stage": TRIAGE_READY,
            "advanced_at": datetime.utcnow().isoformat() + "Z",
            "suggested_priority": pkg.get("suggested_priority", ""),
            "risk_band": (pkg.get("risk") or {}).get("band", ""),
            "is_likely_duplicate": pkg.get("is_likely_duplicate", False),
            "next_actor": "Captain/XO/Number One — approve, defer, or request clarification",
        }
        # Defence-in-depth: never let a malformed entry carry a forbidden stage.
        assert entry["stage"] not in _FORBIDDEN_TARGETS
        results.append({"id": item_id, "action": "advanced" if apply else "would_advance",
                        "entry": entry})
        newly.append(entry)
        if apply:
            ledger[item_id] = entry

    if apply and newly:
        _save_ledger(ledger, ledger_dir)
        _audit(newly, ledger_dir)

    return {
        "apply": apply,
        "advanced": len(newly),
        "already_ready": sum(1 for r in results if r["action"] == "already_triage_ready"),
        "results": results,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def format_advance(report: dict[str, Any]) -> str:
    """Render the advancer result for a Slack/Telegram post or CLI."""
    verb = "Advanced" if report.get("apply") else "Would advance"
    newly = [r for r in report.get("results", []) if r["action"] in ("advanced", "would_advance")]
    if not newly:
        return f"Lifecycle advancer — nothing to advance ({report.get('already_ready', 0)} already Triage Ready)."
    lines = [f"Lifecycle advancer — {verb} {len(newly)} item(s) to *Triage Ready* "
             f"(awaiting Captain approval; NOT approved):"]
    for r in newly:
        e = r["entry"]
        t = f" — {e['title']}" if e["title"] else ""
        dup = " ⚠dup" if e["is_likely_duplicate"] else ""
        lines.append(f"  • {e['id']}{t}  [{e['risk_band'] or 'risk n/a'} → {e['suggested_priority']}]{dup}")
    if not report.get("apply"):
        lines.append("  (dry-run — re-run with `apply` to record the advancement)")
    return "\n".join(lines)


if __name__ == "__main__":
    do_apply = len(sys.argv) > 1 and sys.argv[1] == "apply"
    print(format_advance(advance(apply=do_apply)))
