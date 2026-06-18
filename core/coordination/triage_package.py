"""MSN-0066 Increment 3 — Triage Recommendation packages (Automation Points 1-2).

For every work item parked at the CAPTURE stage (freshly-captured ideas and raw
build requests awaiting triage), this builds a Triage Recommendation Package: the
analysis the Captain / XO / Number One need at Gate 1 — duplicates, related prior
work, a risk score with a suggested priority, and a complexity/dependency read.

REUSE-FIRST (ADR-020): every analysis input is an existing capability, composed
here, none rebuilt:
  * Capture items            — `lifecycle_reconciler.items_at_stage(CAPTURE)`.
  * Duplicate / related work — `command_memory_integration.search_memory`.
  * Risk + band              — `mission_risk.calculate_mission_risk_score`.
  * Complexity / dependency  — GLM-5.2 via `core.engineering.providers.glm.call`
                               (the cheap read-only analysis seam of WP5).
All three are imported defensively and are injectable, so the module is fully
testable without Supabase, Mistral, GLM or the network.

GOVERNANCE (ADR-013): a triage package is a RECOMMENDATION, not a decision. It
assigns no status, makes no assignment, performs no approval. Gate 1 stays human:
Number One recommends, the XO decides. Suggested priority/owner are advisory.

CLI (run with a venv that can reach Supabase/GLM, e.g. slack-bot/.venv):
    python -m core.coordination.triage_package report          # full analysis
    python -m core.coordination.triage_package report --no-llm # skip GLM
    python -m core.coordination.triage_package write
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from core.coordination.lifecycle_reconciler import items_at_stage
from core.coordination.lifecycle_status_map import LifecycleStage

REPO_ROOT = Path(__file__).resolve().parents[2]
TRIAGE_PKG_DIR = REPO_ROOT / "USS-TJR-Control" / "logs" / "missions" / "triage-packages"

_DEFAULT = object()  # sentinel: "load the real defensive implementation"

# Risk band → suggested priority (advisory). Reuses mission_risk's band labels.
_BAND_TO_PRIORITY = {"Critical": "P0", "High": "P1", "Moderate": "P2", "Low": "P3"}

SearchFn = Callable[[str], dict]
RiskFn = Callable[[dict], dict]
GlmFn = Callable[[str, str], Optional[str]]  # (title, description) -> analysis text|None


def _slack_path() -> None:
    bot_dir = str(REPO_ROOT / "slack-bot")
    if bot_dir not in sys.path:
        sys.path.insert(0, bot_dir)


def _load_search() -> Optional[SearchFn]:
    """`command_memory_integration.search_memory`, fail-open to None."""
    try:
        _slack_path()
        from command_memory_integration import search_memory

        def _fn(query: str) -> dict:
            try:
                return search_memory(query) or {}
            except Exception:  # noqa: BLE001
                return {}
        return _fn
    except Exception:  # noqa: BLE001
        return None


def _load_risk() -> Optional[RiskFn]:
    """`mission_risk.calculate_mission_risk_score`, fail-open to None."""
    try:
        _slack_path()
        from mission_risk import calculate_mission_risk_score

        def _fn(mission: dict) -> dict:
            try:
                return calculate_mission_risk_score(mission) or {}
            except Exception:  # noqa: BLE001
                return {}
        return _fn
    except Exception:  # noqa: BLE001
        return None


def _load_glm() -> Optional[GlmFn]:
    """GLM-5.2 complexity/dependency analysis, fail-open to None.

    Wraps `glm.call`, which raises RuntimeError when unconfigured — caught here so
    triage degrades to "analysis unavailable" rather than failing.
    """
    try:
        from core.engineering.providers import glm

        def _fn(title: str, description: str) -> Optional[str]:
            prompt = (
                f"Mission: {title}\n"
                f"Description: {description or '(none provided)'}\n\n"
                "In at most 4 short bullet points, assess for engineering triage: "
                "(1) implementation complexity (Low/Medium/High), (2) likely "
                "dependencies, (3) existing USS TJR components worth reusing before "
                "building. Advisory only; do not assign or approve."
            )
            try:
                text, _model = glm.call(
                    prompt, system="You are the USS TJR engineering triage analyst. Be concise."
                )
                return text.strip() or None
            except Exception:  # noqa: BLE001 - includes RuntimeError when unconfigured
                return None
        return _fn
    except Exception:  # noqa: BLE001
        return None


def _mission_dict(item: dict) -> dict:
    """Shape a Capture ledger item into the dict mission_risk expects."""
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "status": item.get("claimed", "") or "Idea",
        "priority": "",            # unknown — triage is what suggests it
        "description": item.get("evidence", ""),
    }


def _duplicates(search_fn: Optional[SearchFn], item: dict) -> tuple[list[dict], list[dict]]:
    """Return (candidate duplicate/related missions, related decisions).

    Excludes the item itself. Empty title (e.g. a build request) → no search.
    """
    title = (item.get("title") or "").strip()
    if not search_fn or not title:
        return [], []
    res = search_fn(title) or {}
    self_id = str(item.get("id", ""))
    missions = [m for m in (res.get("missions") or []) if str(m.get("id", "")) != self_id]
    decisions = list(res.get("decisions") or [])
    return missions, decisions


def build_triage_packages(
    ledger: Optional[dict[str, Any]] = None,
    search_fn: "SearchFn | object | None" = _DEFAULT,
    risk_fn: "RiskFn | object | None" = _DEFAULT,
    glm_fn: "GlmFn | object | None" = _DEFAULT,
) -> dict[str, Any]:
    """Assemble a triage package per Capture-stage item.

    Read-only/advisory. `ledger` may be injected (tests); otherwise the live
    reconciler runs. Each analysis fn is injectable: omit for the real defensive
    implementation, pass a callable in tests, or pass None to skip that input.
    """
    if search_fn is _DEFAULT:
        search_fn = _load_search()
    if risk_fn is _DEFAULT:
        risk_fn = _load_risk()
    if glm_fn is _DEFAULT:
        glm_fn = _load_glm()

    items = items_at_stage(LifecycleStage.CAPTURE, ledger)
    packages: list[dict[str, Any]] = []

    for item in items:
        mission = _mission_dict(item)
        dup_missions, related_decisions = _duplicates(
            search_fn if callable(search_fn) else None, item)

        risk: dict = {}
        if callable(risk_fn):
            risk = risk_fn(mission) or {}
        band = risk.get("band", "")
        suggested_priority = _BAND_TO_PRIORITY.get(band, "P2 (default)")

        complexity = None
        if callable(glm_fn):
            complexity = glm_fn(mission["title"], mission["description"])

        packages.append({
            "id": item.get("id"),
            "title": item.get("title", ""),
            "kind": item.get("kind", ""),
            "stage": LifecycleStage.CAPTURE.value,
            "next_actor": item.get("next_actor", "Captain/XO/Number One — triage"),
            "risk": {
                "score": risk.get("score"),
                "band": band,
                "reasons": risk.get("reasons", []),
            },
            "suggested_priority": suggested_priority,
            "duplicate_candidates": dup_missions,
            "related_decisions": related_decisions,
            "is_likely_duplicate": bool(dup_missions),
            "complexity_analysis": complexity,
            "complexity_available": complexity is not None,
        })

    # Most-urgent first: by risk score desc (None last), then id for determinism.
    packages.sort(key=lambda p: (-(p["risk"]["score"] or 0), str(p["id"])))

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(packages),
        "packages": packages,
    }


def format_triage_packages(report: dict[str, Any]) -> str:
    """Render triage packages for a Slack/Telegram post (advisory only)."""
    pkgs = report.get("packages", [])
    if not pkgs:
        return "Triage packages — nothing at the Capture stage. ✅"
    lines = [f"Triage packages — {len(pkgs)} item(s) awaiting triage (Gate 1)"]
    for p in pkgs:
        t = f" — {p['title']}" if p["title"] else ""
        lines.append(f"\n• {p['id']}{t}")
        r = p["risk"]
        band = f"{r['band']} ({r['score']})" if r["band"] else "n/a"
        lines.append(f"   risk: {band}  →  suggested priority: {p['suggested_priority']}")
        if p["is_likely_duplicate"]:
            dups = ", ".join(str(m.get("id")) for m in p["duplicate_candidates"][:3])
            lines.append(f"   ⚠ possible duplicate/related: {dups}")
        if p["complexity_available"]:
            lines.append(f"   complexity: {p['complexity_analysis']}")
        else:
            lines.append("   complexity: analysis unavailable")
    return "\n".join(lines)


def write_triage_packages(report: dict[str, Any]) -> Optional[Path]:
    """Persist an advisory JSON snapshot. NOT a triage decision. Never raises."""
    try:
        TRIAGE_PKG_DIR.mkdir(parents=True, exist_ok=True)
        ts = report.get("generated_at", "").replace(":", "").replace("-", "")[:15] or "snapshot"
        path = TRIAGE_PKG_DIR / f"TRIAGE-PKG-{ts}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


if __name__ == "__main__":
    args = sys.argv[1:]
    glm = None if "--no-llm" in args else _DEFAULT
    report = build_triage_packages(glm_fn=glm)
    print(format_triage_packages(report))
    if "write" in args:
        p = write_triage_packages(report)
        print(f"\nSnapshot: {p}" if p else "\n(Snapshot write failed.)")
