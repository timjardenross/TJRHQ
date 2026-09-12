"""
/map — Tag an entity into the knowledge hierarchy (gap-fill interface).

Writes the mapping to knowledge/hierarchy/overrides.yaml and triggers a
partial sync to update the graph. Captain reviews are not required for
/map — it is a direct declaration, not an AI suggestion.

Usage:
  /map msn-0045 ini-002          Tag a mission to an initiative
  /map adr-009 obj-002           Link an ADR to an objective (cross-level)
  /map ll-023 dec-20260613-001   Link a lesson to a decision
  /map                           Show usage + unmapped missions count

Public API:
    handle_map(text, user_id, channel_id) -> str
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_OVERRIDES_PATH = _REPO_ROOT / "knowledge" / "hierarchy" / "overrides.yaml"

_USAGE = """\
*Map* — tag an entity into the knowledge hierarchy.

```
/map msn-0045 ini-002              Tag mission → initiative
/map adr-009 obj-002               Link ADR to objective
/map ll-023 dec-20260613-001       Link lesson to decision
```

Writes to `knowledge/hierarchy/overrides.yaml` and updates the graph immediately.
"""

_RE_MSN = re.compile(r"^(?:USS-TJR-)?MSN-(\d{4}[A-Z]?)$", re.IGNORECASE)
_RE_INI = re.compile(r"^INI-(\d+)$", re.IGNORECASE)
_RE_OBJ = re.compile(r"^OBJ-(\d+)$", re.IGNORECASE)
_RE_ADR = re.compile(r"^ADR-(\d{1,3})$", re.IGNORECASE)
_RE_LL  = re.compile(r"^LL-(\d{1,3})$", re.IGNORECASE)
_RE_DEC = re.compile(r"^DEC-(\d{8}-[\d]+)$", re.IGNORECASE)


def handle_map(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    text = (text or "").strip()

    if not text:
        return _USAGE + "\n" + _unmapped_count()

    parts = text.split()
    if len(parts) != 2:
        return _USAGE

    source_raw, target_raw = parts[0].upper(), parts[1].upper()

    # Determine mapping type
    source_m = _classify(source_raw)
    target_m = _classify(target_raw)

    if not source_m or not target_m:
        return (
            f":warning: Unrecognised ID format: `{source_raw}` or `{target_raw}`.\n\n"
            + _USAGE
        )

    source_type, source_id = source_m
    target_type, target_id = target_m

    # Determine relationship type and overrides section
    section, rel = _resolve_mapping(source_type, target_type)
    if not section:
        return (
            f":warning: Unsupported mapping: `{source_type}` → `{target_type}`.\n"
            "Supported: mission→initiative, adr→objective, lesson→decision."
        )

    # Write to overrides.yaml
    try:
        _write_override(section, source_id, target_id)
    except Exception as exc:
        log.error("[map] Failed to write override: %s", exc)
        return f":warning: Could not write to overrides.yaml: `{type(exc).__name__}`"

    # Trigger partial sync to update the graph
    try:
        from core.knowledge_navigation.sync import run_sync
        sync_result = run_sync(source="overrides")
        sync_note = f"Graph updated: {sync_result.edges_upserted} edges"
        if sync_result.errors:
            sync_note += f" (warnings: {', '.join(sync_result.errors)})"
    except Exception as exc:
        log.warning("[map] Sync after map failed: %s", exc)
        sync_note = "Graph sync pending — run `sync.py` to apply"

    return (
        f":white_check_mark: *Mapped: `{source_id}` → `{target_id}`*\n\n"
        f"Relationship: `{rel}`\n"
        f"Written to: `knowledge/hierarchy/overrides.yaml`\n"
        f"{sync_note}\n\n"
        f"_Commit the overrides file to make this permanent._"
    )


def _classify(raw: str) -> tuple[str, str] | None:
    if _RE_MSN.match(raw):
        m = _RE_MSN.match(raw)
        return "mission", f"MSN-{m.group(1).zfill(4)}"
    if _RE_INI.match(raw):
        m = _RE_INI.match(raw)
        return "initiative", f"INI-{m.group(1).zfill(3)}"
    if _RE_OBJ.match(raw):
        m = _RE_OBJ.match(raw)
        return "objective", f"OBJ-{m.group(1).zfill(3)}"
    if _RE_ADR.match(raw):
        m = _RE_ADR.match(raw)
        return "adr", f"ADR-{m.group(1).zfill(3)}"
    if _RE_LL.match(raw):
        m = _RE_LL.match(raw)
        return "lesson", f"LL-{m.group(1).zfill(3)}"
    if _RE_DEC.match(raw):
        m = _RE_DEC.match(raw)
        return "decision", f"DEC-{m.group(1).upper()}"
    return None


def _resolve_mapping(source_type: str, target_type: str) -> tuple[str, str]:
    """Return (overrides_section, relationship_type) or ('', '') if unsupported."""
    mapping = {
        ("mission", "initiative"): ("mission_initiatives", "contains"),
        ("lesson", "decision"):    ("lesson_decisions", "informed_by"),
        ("adr", "objective"):      ("adr_objectives", "governed_by"),
    }
    return mapping.get((source_type, target_type), ("", ""))


def _write_override(section: str, source_id: str, target_id: str) -> None:
    """Append or update an entry in overrides.yaml."""
    _OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)

    content = _OVERRIDES_PATH.read_text(encoding="utf-8") if _OVERRIDES_PATH.exists() else ""

    # Check if section exists
    section_header = f"{section}:"
    entry_line = f"  {source_id}: {target_id}"

    if entry_line in content:
        return  # Already mapped

    if section_header in content:
        # Insert under existing section
        lines = content.splitlines()
        new_lines: list[str] = []
        in_section = False
        inserted = False
        for line in lines:
            new_lines.append(line)
            if line.strip().startswith(section_header):
                in_section = True
            elif in_section and not line.startswith(" ") and not line.startswith("\t") and line.strip():
                if not inserted:
                    new_lines.insert(-1, entry_line)
                    inserted = True
                in_section = False
        if in_section and not inserted:
            new_lines.append(entry_line)
        content = "\n".join(new_lines)
    else:
        # Append new section
        content = content.rstrip("\n") + f"\n\n{section_header}\n{entry_line}\n"

    _OVERRIDES_PATH.write_text(content, encoding="utf-8")


def _unmapped_count() -> str:
    try:
        from core.knowledge_navigation.index import get_graph
        g = get_graph()
        missions = g.get_nodes(node_type="mission")
        unmapped = [
            n for n in missions
            if not any(
                e.relationship_type == "contains"
                for e in g.in_edges(n.node_id)
            )
        ]
        if not unmapped:
            return ":white_check_mark: All missions are mapped to an initiative."
        ids = ", ".join(f"`{n.node_id}`" for n in unmapped[:5])
        suffix = f" (+{len(unmapped) - 5} more)" if len(unmapped) > 5 else ""
        return f":information_source: {len(unmapped)} unmapped mission(s): {ids}{suffix}"
    except Exception:
        return ""
