"""
/nav — Hierarchical knowledge navigation command.

Traverses the knowledge hierarchy without search — structural graph traversal.

Usage:
  /nav msn-0053 up          → Context chain (why does this exist?)
  /nav obj-001 down         → Implementation status (what missions pursue this?)
  /nav adr-009 impact       → Impact analysis (what depends on this?)
  /nav ini-002 lessons      → Lessons from this initiative
  /nav msn-0053 siblings    → Other missions in the same initiative
  /nav msn-0053 governance  → ADRs and principles governing this entity
  /nav msn-0053 adr-009     → Reasoning path between two entities
  /nav status               → Graph stats (node/edge counts)
  /nav                      → Usage help

Public API:
    handle_navigate(text, user_id, channel_id) -> str
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

_USAGE = """\
*Navigation* — traverse the knowledge hierarchy without search.

```
/nav <id> up           Context chain: why does this entity exist?
/nav <id> down         What missions implement this objective/initiative?
/nav <id> impact       What is downstream of this entity?
/nav <id> lessons      Lessons learned from this entity and descendants
/nav <id> siblings     Other missions in the same initiative
/nav <id> governance   ADRs and principles governing this entity
/nav <from> <to>       Reasoning path between two entities
/nav status            Graph health (node + edge counts)
```

IDs: `MSN-0053` `OBJ-001` `INI-002` `ADR-009` `LL-023` `DEC-20260613-001`
"""

_ID_RE = re.compile(
    r"^((?:USS-TJR-)?MSN-\d{4}[A-Z]?|OBJ-\d+|INI-\d+|ADR-\d{1,3}|LL-\d{1,3}|DEC-\d{8}-[\d]+)$",
    re.IGNORECASE,
)

_VERBS = {"up", "down", "impact", "lessons", "siblings", "governance"}


def handle_navigate(
    text: str,
    user_id: str | None = None,
    channel_id: str | None = None,
) -> str:
    text = (text or "").strip()

    if not text:
        return _USAGE

    parts = text.split()

    # /nav status
    if len(parts) == 1 and parts[0].lower() == "status":
        return _graph_status()

    # /nav <id> <verb> or /nav <id1> <id2>
    if len(parts) == 1:
        if _ID_RE.match(parts[0]):
            return _USAGE + f"\nMissing verb after `{parts[0].upper()}`."
        return _USAGE

    if len(parts) >= 2:
        first = parts[0].upper()
        second = parts[1].lower()

        # /nav <id> <verb>
        if _ID_RE.match(first) and second in _VERBS:
            return _nav_verb(first, second)

        # /nav <id1> <id2>  — reasoning path
        if _ID_RE.match(first) and _ID_RE.match(parts[1].upper()):
            return _nav_path(first, parts[1].upper())

    return _USAGE


def _nav_verb(entity_id: str, verb: str) -> str:
    try:
        from core.knowledge_navigation.context_bridge import format_nav_response
        return format_nav_response(entity_id, verb)
    except Exception as exc:
        log.error("[navigate] %s %s failed: %s", entity_id, verb, exc)
        return f":warning: Navigation error: `{type(exc).__name__}` — check runtime logs."


def _nav_path(from_id: str, to_id: str) -> str:
    try:
        from core.knowledge_navigation.context_bridge import format_path_response
        return format_path_response(from_id, to_id)
    except Exception as exc:
        log.error("[navigate] path %s→%s failed: %s", from_id, to_id, exc)
        return f":warning: Navigation error: `{type(exc).__name__}` — check runtime logs."


def _graph_status() -> str:
    try:
        from core.knowledge_navigation.index import get_graph
        g = get_graph()
        node_count = g.node_count()
        edge_count = g.edge_count()

        if node_count == 0:
            return (
                "*Hierarchy Graph — Empty*\n\n"
                "The graph has not been populated yet.\n"
                "Run `python3 -m core.knowledge_navigation.sync` to populate it, "
                "or complete Part 2 (taxonomy + classifier) first."
            )

        # Count by type
        from core.knowledge_navigation.models import NODE_LEVELS
        type_counts: dict[str, int] = {}
        for node in g.get_nodes():
            type_counts[node.node_type] = type_counts.get(node.node_type, 0) + 1

        lines = ["*Hierarchy Graph Status*", ""]
        for node_type in sorted(NODE_LEVELS, key=lambda t: NODE_LEVELS[t]):
            count = type_counts.get(node_type, 0)
            lines.append(f"  {node_type}s: {count}")
        lines.append(f"\n  Total nodes: {node_count}")
        lines.append(f"  Total edges: {edge_count}")
        return "\n".join(lines)

    except Exception as exc:
        log.error("[navigate] status failed: %s", exc)
        return f":warning: Graph status unavailable: `{type(exc).__name__}`"
