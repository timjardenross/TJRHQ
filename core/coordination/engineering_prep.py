"""MSN-0066 Increment 4 — Ready-for-Engineering prep + linkage surfacing (AP3/AP4).

When a handoff is approved but still pending engineering, the Captain currently
has to hand-write the implementation plan, acceptance criteria and test plan.
This module (AP3) generates that prep advisory for every approved-pending handoff,
and (AP4) surfaces mission↔handoff linkage gaps so nothing is silently orphaned.

REUSE-FIRST (ADR-020):
  * Build-stage handoffs   — `lifecycle_reconciler.items_at_stage(BUILD)`.
  * Handoff context        — `delivery_reconciler._parse_md` + the engineering
                             handoff file already on disk.
  * Plan generation        — GLM-5.2 via `core.engineering.providers.glm.call`
                             (the engineering_router's own GLM backend, the cheap
                             read-only planning seam of WP5). Injectable + fail-open.

GOVERNANCE (ADR-013) — and a deliberate scope boundary for this increment:
This module is READ-ONLY. AP3 produces an advisory plan; it neither approves nor
runs engineering. AP4 only *surfaces* linkage gaps (handoff not tied to a mission)
— it does NOT write the linkage. The write-side linkage fix and `work_queue.json`
update are mechanical-reconciliation steps deferred to the apply/wiring stage,
mirroring how `delivery_reconciler` separates report from apply. Nothing here
mutates a status, a mission, a build record, or the queue.

CLI (run with a venv that can reach GLM, e.g. slack-bot/.venv):
    python -m core.coordination.engineering_prep report
    python -m core.coordination.engineering_prep report --no-llm
    python -m core.coordination.engineering_prep write
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from core.coordination import delivery_reconciler as dr
from core.coordination.lifecycle_reconciler import items_at_stage
from core.coordination.lifecycle_status_map import LifecycleStage

REPO_ROOT = Path(__file__).resolve().parents[2]
PREP_PKG_DIR = REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "engineering-prep"

_DEFAULT = object()  # sentinel: "load the real defensive planner"

# A planner takes (title, context_text) and returns the prep advisory or None.
PlanFn = Callable[[str, str], Optional[str]]

# Handoff Mission ID values that mean "not actually linked to a mission".
_UNLINKED = {"", "unassigned", "unknown", "n/a", "none"}


def _load_planner() -> Optional[PlanFn]:
    """GLM-5.2 ready-for-engineering planner, fail-open to None.

    One call returns the four AP3 outputs as labelled sections. `glm.call` raises
    when unconfigured; caught here so prep degrades to "plan unavailable".
    """
    try:
        from core.engineering.providers import glm

        def _fn(title: str, context: str) -> Optional[str]:
            prompt = (
                f"Approved engineering handoff: {title}\n\n"
                f"Handoff context:\n{context or '(none provided)'}\n\n"
                "Produce a concise ready-for-engineering plan with exactly these four "
                "labelled sections:\n"
                "1. IMPLEMENTATION PLAN — ordered steps.\n"
                "2. ACCEPTANCE CRITERIA — testable bullet points.\n"
                "3. TEST PLAN — how each criterion is verified.\n"
                "4. AFFECTED COMPONENTS — files/modules likely touched and existing "
                "USS TJR components to reuse first.\n"
                "Advisory only; do not write code, approve, or run anything."
            )
            try:
                text, _model = glm.call(
                    prompt, system="You are the USS TJR engineering planner. Be concise and concrete."
                )
                return text.strip() or None
            except Exception:  # noqa: BLE001 - includes RuntimeError when unconfigured
                return None
        return _fn
    except Exception:  # noqa: BLE001
        return None


def _handoff_context(item: dict) -> dict[str, Any]:
    """Read the handoff file for planning context + linkage fields. Read-only."""
    ctx: dict[str, Any] = {"handoff_file": "", "mission_id": "", "decision_id": "",
                           "batch_status": "", "summary": ""}
    if item.get("kind") != "handoff" or not item.get("id"):
        return ctx
    path = dr.HANDOFF_DIR / f"{item['id']}.md"
    if not path.is_file():
        return ctx
    ctx["handoff_file"] = str(path.relative_to(REPO_ROOT))
    meta = dr._parse_md(path, ("Mission ID", "Decision ID", "Batch Status", "Summary"))
    ctx["mission_id"] = meta.get("Mission ID", "")
    ctx["decision_id"] = meta.get("Decision ID", "")
    ctx["batch_status"] = meta.get("Batch Status", "")
    ctx["summary"] = meta.get("Summary", "")
    return ctx


def _linkage(item: dict, ctx: dict[str, Any]) -> dict[str, Any]:
    """Surface (do not fix) the mission↔handoff linkage state. Read-only (AP4)."""
    mission_id = (ctx.get("mission_id") or "").strip()
    linked = mission_id.lower() not in _UNLINKED
    return {
        "mission_id": mission_id,
        "decision_id": ctx.get("decision_id", ""),
        "linked": linked,
        "gap": "" if linked else "Handoff is not linked to a mission id (orphan risk).",
    }


def build_prep_packages(
    ledger: Optional[dict[str, Any]] = None,
    plan_fn: "PlanFn | object | None" = _DEFAULT,
) -> dict[str, Any]:
    """Assemble a ready-for-engineering prep package per Build-stage handoff.

    Read-only/advisory. `ledger` injectable (tests). `plan_fn` injectable: omit
    for the real GLM planner, pass a callable in tests, or None to skip planning.
    """
    if plan_fn is _DEFAULT:
        plan_fn = _load_planner()

    # Approved-but-pending engineering work = handoffs at the Build stage (a
    # delivered handoff would be at Review, a closed one at Closed).
    items = [it for it in items_at_stage(LifecycleStage.BUILD, ledger)
             if it.get("kind") == "handoff"]

    packages: list[dict[str, Any]] = []
    linkage_gaps = 0
    for item in items:
        ctx = _handoff_context(item)
        context_text = "\n".join(filter(None, [
            f"Summary: {ctx['summary']}" if ctx["summary"] else "",
            f"Batch Status: {ctx['batch_status']}" if ctx["batch_status"] else "",
            f"Ledger: {item.get('evidence', '')}",
        ]))
        advisory = plan_fn(item.get("title", "") or item.get("id", ""), context_text) \
            if callable(plan_fn) else None
        linkage = _linkage(item, ctx)
        if not linkage["linked"]:
            linkage_gaps += 1
        packages.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "stage": LifecycleStage.BUILD.value,
            "handoff_file": ctx["handoff_file"],
            "prep_advisory": advisory,
            "prep_available": advisory is not None,
            "linkage": linkage,
        })

    packages.sort(key=lambda p: str(p["id"]))
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(packages),
        "linkage_gaps": linkage_gaps,
        "packages": packages,
    }


def format_prep_packages(report: dict[str, Any]) -> str:
    """Render prep packages for a Slack/Telegram post (advisory only)."""
    pkgs = report.get("packages", [])
    if not pkgs:
        return "Engineering prep — no approved-pending handoffs at the Build stage. ✅"
    lines = [f"Engineering prep — {len(pkgs)} handoff(s) ready for engineering"
             f"  ({report.get('linkage_gaps', 0)} linkage gap(s))"]
    for p in pkgs:
        t = f" — {p['title']}" if p["title"] else ""
        lines.append(f"\n• {p['id']}{t}")
        if not p["linkage"]["linked"]:
            lines.append(f"   ⚠ {p['linkage']['gap']}")
        else:
            lines.append(f"   mission: {p['linkage']['mission_id']}")
        lines.append("   plan: " + ("generated below" if p["prep_available"]
                                    else "plan unavailable"))
        if p["prep_available"]:
            lines.append("   " + p["prep_advisory"].replace("\n", "\n   "))
    return "\n".join(lines)


def write_prep_packages(report: dict[str, Any]) -> Optional[Path]:
    """Persist an advisory JSON snapshot. NOT an engineering run. Never raises."""
    try:
        PREP_PKG_DIR.mkdir(parents=True, exist_ok=True)
        ts = report.get("generated_at", "").replace(":", "").replace("-", "")[:15] or "snapshot"
        path = PREP_PKG_DIR / f"ENG-PREP-{ts}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


if __name__ == "__main__":
    args = sys.argv[1:]
    planner = None if "--no-llm" in args else _DEFAULT
    report = build_prep_packages(plan_fn=planner)
    print(format_prep_packages(report))
    if "write" in args:
        p = write_prep_packages(report)
        print(f"\nSnapshot: {p}" if p else "\n(Snapshot write failed.)")
