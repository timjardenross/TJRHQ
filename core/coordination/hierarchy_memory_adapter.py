"""
Hierarchy memory adapter — enriches Commander runtime context with
structural hierarchy information when available.

Follows the CommanderMemoryAdapter pattern. Additive only: when the
hierarchy graph is empty or the entity is untagged, returns an empty
context and leaves existing behaviour unchanged.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@dataclass
class HierarchyContext:
    found: bool = False
    summary: str = ""
    context_block: str = ""
    entity_ids_found: list[str] = None

    def __post_init__(self):
        if self.entity_ids_found is None:
            self.entity_ids_found = []


class HierarchyMemoryAdapter:
    """
    Thin adapter that builds hierarchy context for the Commander runtime.

    Usage:
        adapter = HierarchyMemoryAdapter()
        ctx = adapter.build_hierarchy_note(text=user_text)
        if ctx.found:
            system_prompt += ctx.context_block
    """

    def __init__(self) -> None:
        self._available: Optional[bool] = None

    def _check_available(self) -> bool:
        if self._available is None:
            try:
                from core.knowledge_navigation.index import get_graph
                g = get_graph()
                self._available = g.node_count() > 0
            except Exception as exc:
                log.debug("[hierarchy-adapter] Navigation module not available: %s", exc)
                self._available = False
        return self._available

    def build_hierarchy_note(self, *, text: str) -> HierarchyContext:
        """
        Scan `text` for entity IDs and return hierarchy context block.

        Returns HierarchyContext(found=False) if:
        - The hierarchy module is unavailable
        - The graph is empty (sync has not run yet)
        - No recognised entity IDs appear in the text
        - All found IDs are untagged in the hierarchy
        """
        if not self._check_available():
            return HierarchyContext()

        try:
            from core.knowledge_navigation.context_bridge import build_hierarchy_context, _extract_ids
            entity_ids = _extract_ids(text, limit=5)
            if not entity_ids:
                return HierarchyContext()

            block = build_hierarchy_context(text)
            if not block:
                return HierarchyContext()

            return HierarchyContext(
                found=True,
                summary=f"Hierarchy context for: {', '.join(entity_ids)}",
                context_block=f"\n\n{block}",
                entity_ids_found=entity_ids,
            )
        except Exception as exc:
            log.warning("[hierarchy-adapter] build_hierarchy_note failed: %s", exc)
            return HierarchyContext()

    def invalidate(self) -> None:
        """Force re-check of availability on next call (e.g. after a sync run)."""
        self._available = None
