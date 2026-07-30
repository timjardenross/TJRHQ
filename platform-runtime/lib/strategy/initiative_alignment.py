"""Strategic Alignment Engine (EXEC-006 WP4).

Ensures all work can explain why it exists:

    Mission → Initiative → Strategic Objective

Detects:
  - orphan missions      (no initiative link)
  - orphan improvements  ([IMPROVE] missions with no initiative)
  - orphan investigations(investigations with no initiative/objective context)
  - orphan initiatives   (no objective linkage)
  - duplicate initiatives(same objective + near-identical title)
  - conflicting initiatives (contradictory targets on the same objective)

Reuse: missions table, strategic_orphan_missions view, initiatives (decisions),
investigation registry. No new tables. All detection is read-only.

Public API:
    AlignmentReport
    run_alignment_scan()          -> AlignmentReport
    traceability_for_mission(id)  -> dict
    format_alignment(report)      -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.initiatives import (
    Initiative, list_initiatives, get_linked_missions, INITIATIVE_OWNER_PREFIX,
)

_IMPROVE_PREFIX = "[IMPROVE]"
_ACTIVE_MISSION = frozenset({
    "active", "designed", "implemented", "tested", "in_progress",
    "awaiting xo approval", "awaiting number one review", "blocked",
})
_TITLE_SIMILARITY_THRESHOLD = 0.82


@dataclass
class AlignmentReport:
    orphan_missions: list[str] = field(default_factory=list)
    orphan_improvements: list[str] = field(default_factory=list)
    orphan_investigations: list[str] = field(default_factory=list)
    orphan_initiatives: list[str] = field(default_factory=list)
    duplicate_initiatives: list[tuple[str, str]] = field(default_factory=list)
    conflicting_initiatives: list[tuple[str, str]] = field(default_factory=list)
    total_missions: int = 0
    linked_missions: int = 0

    @property
    def coverage_pct(self) -> float:
        if self.total_missions <= 0:
            return 0.0
        return round(self.linked_missions / self.total_missions, 3)

    @property
    def has_findings(self) -> bool:
        return any([
            self.orphan_missions, self.orphan_improvements, self.orphan_investigations,
            self.orphan_initiatives, self.duplicate_initiatives, self.conflicting_initiatives,
        ])


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception:
        return None


def _all_linked_mission_ids(initiatives: list[Initiative]) -> set[str]:
    linked: set[str] = set()
    for init in initiatives:
        linked.update(get_linked_missions(init.initiative_id))
    return linked


# ── Scan ──────────────────────────────────────────────────────────────────────

def run_alignment_scan() -> AlignmentReport:
    """Scan the portfolio for traceability gaps and initiative conflicts."""
    report = AlignmentReport()
    c = _client()
    if c is None:
        return report

    initiatives = list_initiatives(include_closed=False)
    linked_mission_ids = _all_linked_mission_ids(initiatives)

    # Orphan + duplicate + conflicting initiatives
    by_objective: dict[str, list[Initiative]] = {}
    for init in initiatives:
        if init.is_orphan:
            report.orphan_initiatives.append(init.initiative_id)
        else:
            by_objective.setdefault(init.objective_id, []).append(init)

    for obj_id, group in by_objective.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                sim = SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio()
                if sim >= _TITLE_SIMILARITY_THRESHOLD:
                    report.duplicate_initiatives.append((a.initiative_id, b.initiative_id))
                elif _targets_conflict(a, b):
                    report.conflicting_initiatives.append((a.initiative_id, b.initiative_id))

    # Mission traceability
    try:
        res = c.raw_client.table("missions").select("id,title,status").limit(500).execute()
        for row in res.data or []:
            mid = str(row.get("id") or "")
            status = str(row.get("status") or "").lower()
            title = str(row.get("title") or "")
            if status not in _ACTIVE_MISSION:
                continue
            report.total_missions += 1
            if mid in linked_mission_ids:
                report.linked_missions += 1
            else:
                if title.startswith(_IMPROVE_PREFIX):
                    report.orphan_improvements.append(mid)
                else:
                    report.orphan_missions.append(mid)
    except Exception as exc:
        log.debug("[strategy.alignment] mission scan failed: %s", exc)

    # Orphan investigations (open investigations with no initiative context)
    try:
        ires = (
            c.raw_client.table("decisions")
            .select("owner,rationale")
            .like("owner", "investigation:%")
            .limit(100)
            .execute()
        )
        for row in ires.data or []:
            rationale = str(row.get("rationale") or "")
            if "STATUS: closed" in rationale:
                continue
            owner = str(row.get("owner") or "")
            inv_id = owner.split(":", 1)[1] if ":" in owner else owner
            # Investigation is "aligned" if its context references an initiative/objective
            if "initiative" not in rationale.lower() and "objective" not in rationale.lower():
                report.orphan_investigations.append(inv_id)
    except Exception as exc:
        log.debug("[strategy.alignment] investigation scan failed: %s", exc)

    log.info(
        "[strategy.alignment] coverage %.0f%% (%d/%d) | orphans: %dm/%di/%dinv | dup: %d | conflict: %d",
        report.coverage_pct * 100, report.linked_missions, report.total_missions,
        len(report.orphan_missions), len(report.orphan_improvements),
        len(report.orphan_investigations), len(report.duplicate_initiatives),
        len(report.conflicting_initiatives),
    )
    return report


def _targets_conflict(a: Initiative, b: Initiative) -> bool:
    """Heuristic: two initiatives on the same objective conflict if one pursues
    a reduction and the other a growth of the same underlying metric."""
    import re
    def _num(s: str):
        m = re.search(r"-?\d+(?:\.\d+)?", s or "")
        return float(m.group()) if m else None
    ab, at = _num(a.baseline), _num(a.target)
    bb, bt = _num(b.baseline), _num(b.target)
    if None in (ab, at, bb, bt):
        return False
    a_dir = "reduction" if at < ab else "growth"
    b_dir = "reduction" if bt < bb else "growth"
    return a_dir != b_dir


def traceability_for_mission(mission_id: str) -> dict[str, Any]:
    """Return the full traceability chain for a mission: initiative + objective."""
    chain: dict[str, Any] = {"mission_id": mission_id, "initiative_id": None, "objective_id": None, "aligned": False}
    for init in list_initiatives(include_closed=True):
        if mission_id in get_linked_missions(init.initiative_id):
            chain["initiative_id"] = init.initiative_id
            chain["objective_id"] = init.objective_id
            chain["aligned"] = bool(init.objective_id)
            break
    return chain


def format_alignment(report: AlignmentReport) -> str:
    if not report.has_findings and report.total_missions == 0:
        return "_Strategic alignment: no data available._"
    lines = [f"*Strategic Alignment:* {report.coverage_pct:.0%} mission coverage "
             f"({report.linked_missions}/{report.total_missions} traced to initiatives)"]
    if report.orphan_missions:
        lines.append(f"  :warning: {len(report.orphan_missions)} orphan mission(s)")
    if report.orphan_improvements:
        lines.append(f"  :warning: {len(report.orphan_improvements)} orphan improvement(s)")
    if report.orphan_investigations:
        lines.append(f"  :warning: {len(report.orphan_investigations)} orphan investigation(s)")
    if report.orphan_initiatives:
        lines.append(f"  :rotating_light: {len(report.orphan_initiatives)} initiative(s) with no objective")
    if report.duplicate_initiatives:
        lines.append(f"  :twisted_rightwards_arrows: {len(report.duplicate_initiatives)} possible duplicate initiative(s)")
    if report.conflicting_initiatives:
        lines.append(f"  :crossed_swords: {len(report.conflicting_initiatives)} conflicting initiative(s)")
    return "\n".join(lines)


__all__ = [
    "AlignmentReport",
    "run_alignment_scan",
    "traceability_for_mission",
    "format_alignment",
]
