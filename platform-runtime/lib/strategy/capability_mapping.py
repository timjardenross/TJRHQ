"""Capability Mapping Engine (EXEC-009 WP2).

Maps relationships between strategic layers:

    Objectives → Capabilities → Systems → Processes → Outcomes

Identifies:
  - Orphan capabilities (no objective linkage)
  - Unsupported objectives (no capabilities)
  - Duplicate capabilities (similar name/type)
  - Missing capability coverage

No new tables. Reads capabilities (WP1) and reuses initiative_alignment
patterns for orphan/duplicate detection.

Public API:
    CapabilityMap
    build_capability_map()           -> CapabilityMap
    find_orphan_capabilities()       -> list[Capability]
    find_unsupported_objectives()    -> list[str]
    find_duplicate_capabilities()    -> list[tuple[Capability, Capability]]
    format_capability_map(cm)        -> str
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

from lib.strategy.capabilities import Capability, list_capabilities, get_capabilities_for_objective


@dataclass
class CapabilityMap:
    """Full capability map across the strategic layers."""
    objective_coverage: dict[str, list[str]] = field(default_factory=dict)   # obj_id → [cap_id]
    capability_systems: dict[str, list[str]] = field(default_factory=dict)   # cap_id → [system_id]
    capability_initiatives: dict[str, list[str]] = field(default_factory=dict)  # cap_id → [init_id]
    orphan_cap_ids: list[str] = field(default_factory=list)
    unsupported_obj_ids: list[str] = field(default_factory=list)
    duplicate_pairs: list[tuple[str, str]] = field(default_factory=list)
    total_capabilities: int = 0
    total_objectives_covered: int = 0
    coverage_pct: float = 0.0


def build_capability_map() -> CapabilityMap:
    """Build the full capability map across all strategic layers."""
    cm = CapabilityMap()

    caps = list_capabilities()
    cm.total_capabilities = len(caps)
    if not caps:
        return cm

    # Objectives with at least one capability
    for cap in caps:
        if cap.objective_id:
            cm.objective_coverage.setdefault(cap.objective_id, []).append(cap.capability_id)
        if cap.system_id:
            cm.capability_systems.setdefault(cap.capability_id, []).append(cap.system_id)
        if cap.initiative_id:
            cm.capability_initiatives.setdefault(cap.capability_id, []).append(cap.initiative_id)

    cm.orphan_cap_ids = [c.capability_id for c in caps if not c.objective_id]

    # Pull all strategic objectives to find unsupported ones
    try:
        from lib.strategy.outcomes import list_objectives
        objectives = list_objectives()
        obj_ids = {o.objective_id for o in objectives}
        covered_obj_ids = set(cm.objective_coverage.keys())
        cm.unsupported_obj_ids = list(obj_ids - covered_obj_ids)
        total = len(obj_ids)
        cm.total_objectives_covered = len(covered_obj_ids & obj_ids)
        cm.coverage_pct = cm.total_objectives_covered / total if total else 0.0
    except Exception as exc:
        log.debug("[capability_mapping] objectives unavailable: %s", exc)

    cm.duplicate_pairs = _find_duplicate_pairs(caps)

    log.info(
        "[capability_mapping] %d caps | %d orphans | %d unsupported objectives | coverage %.0f%%",
        cm.total_capabilities, len(cm.orphan_cap_ids), len(cm.unsupported_obj_ids),
        cm.coverage_pct * 100,
    )
    return cm


def find_orphan_capabilities() -> list[Capability]:
    """Return capabilities with no strategic objective linkage."""
    return [c for c in list_capabilities() if not c.objective_id]


def find_unsupported_objectives() -> list[str]:
    """Return objective IDs that have no capabilities mapped to them."""
    cm = build_capability_map()
    return cm.unsupported_obj_ids


def find_duplicate_capabilities() -> list[tuple[Capability, Capability]]:
    """Return pairs of capabilities that appear to be duplicates."""
    caps = list_capabilities()
    pairs = _find_duplicate_pairs(caps)
    cap_index = {c.capability_id: c for c in caps}
    return [(cap_index[a], cap_index[b]) for a, b in pairs if a in cap_index and b in cap_index]


def _find_duplicate_pairs(caps: list[Capability]) -> list[tuple[str, str]]:
    """Identify likely-duplicate capabilities by name+type similarity."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(caps):
        for b in caps[i + 1:]:
            if a.cap_type != b.cap_type:
                continue
            ratio = SequenceMatcher(None, a.name.lower(), b.name.lower()).ratio()
            if ratio >= 0.80:
                key = tuple(sorted([a.capability_id, b.capability_id]))
                if key not in seen:
                    seen.add(key)
                    pairs.append((a.capability_id, b.capability_id))
    return pairs


def format_capability_map(cm: CapabilityMap) -> str:
    if cm.total_capabilities == 0:
        return "_No capabilities registered._"
    lines = ["*Capability Map:*"]
    lines.append(f"  Total: {cm.total_capabilities} | Objectives covered: {cm.total_objectives_covered} ({cm.coverage_pct:.0%})")
    if cm.orphan_cap_ids:
        lines.append(f"  :warning: Orphan capabilities (no objective): {len(cm.orphan_cap_ids)}")
    if cm.unsupported_obj_ids:
        lines.append(f"  :warning: Unsupported objectives: {len(cm.unsupported_obj_ids)}")
    if cm.duplicate_pairs:
        lines.append(f"  :warning: Potential duplicates: {len(cm.duplicate_pairs)} pair(s)")
    return "\n".join(lines)


__all__ = [
    "CapabilityMap",
    "build_capability_map",
    "find_orphan_capabilities",
    "find_unsupported_objectives",
    "find_duplicate_capabilities",
    "format_capability_map",
]
