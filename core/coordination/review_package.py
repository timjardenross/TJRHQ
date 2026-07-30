"""MSN-0066 Increment 2 — Review Package generator (Automation Point 5).

The Lifecycle Reconciler (Increment 1) finds the items parked at the REVIEW
stage — the dominant dead zone (draft PRs nobody merges). This module turns each
one into a *review package*: the evidence a human needs to sign off, plus the QA
Validation Officer's advisory verdict, assembled automatically so the Captain /
Number One no longer has to gather it by hand.

REUSE-FIRST (ADR-020):
  * Review items come from `lifecycle_reconciler.build_recommendations()`.
  * Evidence parsing reuses `delivery_reconciler._parse_md` and its HANDOFF_DIR.
  * The QA verdict reuses the existing `lib.mistral_agents.call_qa_validation_officer`
    — the same agent the /mission-close flow already uses — imported defensively
    and treated as fail-open (None → "advisory unavailable"), exactly as the
    closure path treats it. No new agent, no new model wiring.

GOVERNANCE (ADR-013): a review package is preparation, not a decision. This
module collects evidence and an *advisory* QA verdict; it performs no closure, no
approval, no merge, and runs no code. The human still decides at Gate 2.

CLI (run with a venv that can reach the QA agent, e.g. platform-runtime/.venv):
    python -m core.coordination.review_package report      # live QA advisory
    python -m core.coordination.review_package report --no-qa
    python -m core.coordination.review_package write       # persist snapshot
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from core.coordination import delivery_reconciler as dr
from core.coordination.lifecycle_reconciler import build_recommendations
from core.coordination.lifecycle_status_map import LifecycleStage

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_PKG_DIR = REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "review-packages"

# Sentinel: caller didn't pass a qa_fn, so load the real (defensive) officer.
_DEFAULT_QA = object()

# A QA function takes (mission_id, dossier_text) and returns advisory text or None.
QaFn = Callable[[str, str], Optional[str]]


def _load_qa_officer() -> Optional[QaFn]:
    """Import the existing QA Validation Officer, fail-open to None.

    Mirrors how platform-runtime/commands/mission_lifecycle.py reaches it: put
    `platform-runtime` on the path, then `from lib.mistral_agents import ...`. Any
    failure (missing dep, no agent configured) degrades to None — advisory
    simply reads "unavailable", never blocking.
    """
    try:
        bot_dir = str(REPO_ROOT / "platform-runtime")
        if bot_dir not in sys.path:
            sys.path.insert(0, bot_dir)
        from lib.mistral_agents import call_qa_validation_officer

        def _call(mission_id: str, dossier: str) -> Optional[str]:
            try:
                return call_qa_validation_officer(mission_id, dossier)
            except Exception:  # noqa: BLE001 - advisory must never raise
                return None

        return _call
    except Exception:  # noqa: BLE001
        return None


def collect_evidence(item: dict) -> dict[str, Any]:
    """Gather the review evidence for one Review-stage ledger item.

    Reads the engineering handoff file (when the item is a handoff) for the PR
    URL, code artifact, decision id and mission id — reusing the delivery
    reconciler's markdown parser. Missing files/fields degrade gracefully; the
    ledger's own evidence string is always retained.
    """
    ev: dict[str, Any] = {
        "kind": item.get("kind", ""),
        "title": item.get("title", ""),
        "claimed": item.get("claimed", ""),
        "ledger_evidence": item.get("evidence", ""),
        "pr_url": "",
        "artifact": "",
        "handoff_file": "",
        "decision_id": "",
        "mission_id": "",
    }
    if item.get("kind") == "handoff" and item.get("id"):
        path = dr.HANDOFF_DIR / f"{item['id']}.md"
        if path.is_file():
            ev["handoff_file"] = str(path.relative_to(REPO_ROOT))
            meta = dr._parse_md(path, ("PR URL", "Batch Artifact", "Decision ID", "Mission ID"))
            ev["pr_url"] = meta.get("PR URL", "")
            ev["artifact"] = meta.get("Batch Artifact", "")
            ev["decision_id"] = meta.get("Decision ID", "")
            ev["mission_id"] = meta.get("Mission ID", "")
    if not ev["mission_id"]:
        ev["mission_id"] = str(item.get("id", ""))
    return ev


def _format_review_dossier(item: dict, ev: dict[str, Any]) -> str:
    """Structured dossier text for the QA officer prompt (acceptance-criteria framed)."""
    lines = [
        "=== REVIEW PACKAGE DOSSIER ===",
        f"Item        : {item.get('id', '')}",
        f"Title       : {ev['title'] or '(none)'}",
        "Lifecycle   : Review — delivered, awaiting human sign-off",
        f"Claimed     : {ev['claimed'] or '(none)'}",
        f"Delivery    : {ev['ledger_evidence'] or '(none)'}",
        f"PR          : {ev['pr_url'] or 'n/a'}",
        f"Artifact    : {ev['artifact'] or 'n/a'}",
        f"Handoff     : {ev['handoff_file'] or 'n/a'}",
        f"Decision ID : {ev['decision_id'] or 'n/a'}",
        "",
        "Assess whether this delivered change is ready to review/merge: confirm the "
        "evidence above substantiates the work, call out missing validation, and give "
        "a clear APPROVE-TO-REVIEW or FLAG recommendation. Do not approve closure.",
    ]
    return "\n".join(lines)


def build_review_packages(
    report: Optional[dict[str, Any]] = None,
    qa_fn: "QaFn | object | None" = _DEFAULT_QA,
) -> dict[str, Any]:
    """Assemble a review package per Review-stage item.

    Read-only/advisory. `report` may be injected (tests); otherwise the live
    Lifecycle Reconciler is run. `qa_fn` is injectable: omit it for the real QA
    officer, pass a callable in tests, or pass None to skip QA entirely.
    """
    if report is None:
        report = build_recommendations()
    if qa_fn is _DEFAULT_QA:
        qa_fn = _load_qa_officer()

    review_items = [r for r in report.get("recommendations", [])
                    if r.get("stage") == LifecycleStage.REVIEW.value]

    packages: list[dict[str, Any]] = []
    for item in review_items:
        ev = collect_evidence(item)
        dossier = _format_review_dossier(item, ev)
        advisory: Optional[str] = None
        if callable(qa_fn):
            advisory = qa_fn(ev["mission_id"], dossier)
        packages.append({
            "id": item.get("id"),
            "title": ev["title"],
            "stage": LifecycleStage.REVIEW.value,
            "mission_id": ev["mission_id"],
            "next_actor": item.get("next_actor", "Captain — review/merge the PR"),
            "evidence": ev,
            "qa_advisory": advisory,
            "qa_available": advisory is not None,
        })

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(packages),
        "packages": packages,
        "source": report.get("source", {}),
    }


def format_review_packages(report: dict[str, Any]) -> str:
    """Render review packages for a Slack/Telegram post (advisory only)."""
    pkgs = report.get("packages", [])
    if not pkgs:
        return "Review packages — nothing at the Review stage. ✅"
    lines = [f"Review packages — {len(pkgs)} item(s) awaiting sign-off"]
    for p in pkgs:
        ev = p["evidence"]
        t = f" — {p['title']}" if p["title"] else ""
        lines.append(f"\n• {p['id']}{t}")
        lines.append(f"   next: {p['next_actor']}")
        if ev["pr_url"]:
            lines.append(f"   PR: {ev['pr_url']}")
        elif ev["artifact"]:
            lines.append(f"   artifact: {ev['artifact']}")
        if p["qa_available"]:
            lines.append(f"   QA Validation Officer: {p['qa_advisory']}")
        else:
            lines.append("   QA Validation Officer: advisory unavailable")
    return "\n".join(lines)


def write_review_packages(report: dict[str, Any]) -> Optional[Path]:
    """Persist an advisory JSON snapshot. NOT a closure/approval write. Never raises."""
    try:
        REVIEW_PKG_DIR.mkdir(parents=True, exist_ok=True)
        ts = report.get("generated_at", "").replace(":", "").replace("-", "")[:15] or "snapshot"
        path = REVIEW_PKG_DIR / f"REVIEW-PKG-{ts}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


if __name__ == "__main__":
    args = sys.argv[1:]
    qa = None if "--no-qa" in args else _DEFAULT_QA
    report = build_review_packages(qa_fn=qa)
    print(format_review_packages(report))
    if "write" in args:
        p = write_review_packages(report)
        print(f"\nSnapshot: {p}" if p else "\n(Snapshot write failed.)")
