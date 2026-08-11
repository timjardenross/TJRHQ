"""Captain Operating Picture — USS-TJR-MSN-0098 WP2.

Proactive *personal* operating intelligence across workload, priorities, energy,
recovery, focus and capacity — answering:

    * What has changed?       * What deserves attention?     * What may become a risk?

Reuse-only: missions (mission registry adapter), open advisory loops (outcomes),
recent decisions (timeline/temporal), wellness (wellness.py), and attention/risk
(triggers + signals). No new store. Advisory, non-authoritative.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
# Repo root must be importable so `core.coordination.*` package imports inside the
# mission registry adapter resolve regardless of how we were invoked (script vs -c).
for _p in (str(_HERE), str(_REPO_ROOT), str(_REPO_ROOT / "core" / "coordination")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
_outcomes = _import_sibling("outcomes")
import temporal as _temporal
import triggers as _triggers
import signals as _signals
import wellness as _wellness

_TERMINAL = {"COMPLETED", "CANCELLED", "CLOSED", "ARCHIVED", "DONE", "COMPLETE"}


def _load_missions() -> list[dict[str, Any]]:
    # Use the adapter's deterministic *file* loader directly. The default
    # _load_missions() takes an environment-dependent registry branch that can
    # return [] under some sys.path/cwd conditions; _load_from_files() always
    # reads the canonical mission-index regardless of how we were invoked.
    try:
        from mission_registry_memory_adapter import MissionRegistryMemoryAdapter  # noqa: PLC0415
        return MissionRegistryMemoryAdapter()._load_from_files()
    except Exception:  # noqa: BLE001
        return []


def captain_operating_picture() -> dict[str, Any]:
    missions = _load_missions()
    statuses = {str(m.get("status", "")).upper() for m in missions}
    status_known = statuses - {"UNKNOWN", ""}
    active = [m for m in missions if str(m.get("status", "")).upper() not in _TERMINAL]

    records = _outcomes.load_records()
    open_loops = [r for r in records if not r.get("outcome")]

    # Workload = active missions + open advisory loops. When the registry exposes
    # no usable status (offline), report the total honestly rather than claiming
    # everything is "active".
    workload = {
        "active_missions": len(active) if status_known else None,
        "missions_on_record": len(missions),
        "status_available": bool(status_known),
        "open_advisory_loops": len(open_loops),
        "total_missions": len(missions),
    }

    # Priorities = most recent decisions (what the Captain has been deciding).
    recent_decisions = _temporal.what_preceded("priority decision mission", limit=5)

    # Energy / recovery / focus / capacity — from wellness (degrades gracefully).
    win = _wellness.wellness_intelligence()

    # What changed / what deserves attention / what may become a risk.
    changed = _temporal.what_changed(days=14)
    trigs = _triggers.evaluate_triggers()
    sigs = _signals.emerging_signals()
    attention = [t.to_dict() for t in trigs if t.level in ("concern", "escalation")]
    risks = [s.to_dict() for s in sigs if s.severity == "concern"]

    return {
        "workload": workload,
        "priorities": recent_decisions.get("preceding_decisions", []),
        "wellness": {
            "available": win.get("available", False),
            "worsening": win.get("worsening", []),
            "recovery_priorities": win.get("recovery_priorities", []),
            "narrative": win.get("narrative", ""),
        },
        "what_changed": changed.get("narrative", ""),
        "deserves_attention": attention,
        "becoming_risk": risks,
        "headline": _headline(workload, attention, risks, win),
        "note": "Personal operating intelligence — advisory only; the Captain decides.",
    }


def _headline(workload, attention, risks, win) -> str:
    if workload["status_available"]:
        bits = [f"{workload['active_missions']} active mission(s)"]
    else:
        bits = [f"{workload['missions_on_record']} mission(s) on record (status n/a)"]
    bits.append(f"{workload['open_advisory_loops']} open loop(s)")
    if attention:
        bits.append(f"{len(attention)} item(s) deserve attention")
    if risks:
        bits.append(f"{len(risks)} emerging risk(s)")
    if win.get("worsening"):
        bits.append("wellness: " + ", ".join(win["worsening"]))
    return "Operating picture — " + "; ".join(bits) + "."


def to_markdown() -> str:
    p = captain_operating_picture()
    L = ["# Captain Operating Picture", "", p["headline"], ""]
    wl = p["workload"]
    workload_str = (f"{wl['active_missions']} active mission(s)" if wl["status_available"]
                    else f"{wl['missions_on_record']} mission(s) on record")
    L.append(f"*Workload:* {workload_str}, {wl['open_advisory_loops']} open advisory loop(s).")
    L.append(f"*What changed:* {p['what_changed']}")
    if p["deserves_attention"]:
        L.append("\n## Deserves Attention")
        for a in p["deserves_attention"]:
            L.append(f"- [{a['level']}] {a['trigger_type']}: {a['message']}")
    if p["becoming_risk"]:
        L.append("\n## May Become a Risk")
        for r in p["becoming_risk"]:
            L.append(f"- {r['name']}: {r['detail']}")
    L.append(f"\n*Wellness:* {p['wellness']['narrative']}")
    L.append(f"\n_{p['note']}_")
    return "\n".join(L)
