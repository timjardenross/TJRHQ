"""Commander-facing advisory memory presentation helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.coordination.advisory_memory_formatter import format_memory_block

log = logging.getLogger(__name__)

try:
    from core.coordination.number_one_memory_adapter import NumberOneMemoryAdapter
except Exception:  # pragma: no cover - advisory fallback
    NumberOneMemoryAdapter = None


@dataclass
class CommanderMemoryContext:
    found: bool = False
    summary: str = ""
    confidence: float = 0.0
    note: str = ""


class CommanderMemoryAdapter:
    """Thin presentation-layer adapter over existing memory sources."""

    def __init__(self):
        self.number_one_memory = NumberOneMemoryAdapter() if NumberOneMemoryAdapter else None

    def build_memory_note(
        self,
        *,
        text: str,
        intent: str,
        research_summary: str = "",
        mission_context: Any | None = None,
        decision_context: Any | None = None,
        routing_results: dict[str, Any] | None = None,
    ) -> CommanderMemoryContext:
        routing_results = routing_results or {}
        blocks: list[str] = []
        confidence = 0.0
        related_counts: list[str] = []

        memory_context = self._retrieve_number_one_context(text, intent, routing_results)
        mission_context = mission_context or None
        decision_context = decision_context or None
        if memory_context and getattr(memory_context, "found", False):
            confidence = max(confidence, float(getattr(memory_context, "confidence", 0.0) or 0.0))
            if getattr(memory_context, "summary", ""):
                blocks.append(
                    format_memory_block(
                        label="Historical context",
                        items=[
                            {"summary": item.get("summary", "")}
                            for item in getattr(memory_context, "sources", [])[:3]
                        ],
                        source_types=[
                            item.get("source_type", "").replace("_", " ")
                            for item in getattr(memory_context, "sources", [])
                            if item.get("source_type")
                        ],
                        summary=getattr(memory_context, "summary", ""),
                        confidence=getattr(memory_context, "confidence", 0.0),
                    )
                )
            related_counts.append(f"{len(getattr(memory_context, 'sources', []) or [])} related references")

        if mission_context and getattr(mission_context, "found", False):
            related_counts.append(f"{len(getattr(mission_context, 'related_missions', []) or [])} related missions")
        if decision_context and getattr(decision_context, "found", False):
            related_counts.append(f"{len(getattr(decision_context, 'related_decisions', []) or [])} related decisions")

        if not blocks:
            return CommanderMemoryContext()

        note_parts = ["*Historical Insight:*"]
        note_parts.extend(blocks[:2])
        if related_counts:
            if confidence >= 0.8:
                note_parts.append(
                    f"Memory Confidence: {'HIGH' if confidence >= 0.8 else 'LOW'}"
                )
            note_parts.append(
                f"Reason: {', '.join(related_counts[:3])}"
            )
        return CommanderMemoryContext(
            found=True,
            confidence=min(confidence, 1.0),
            summary=" | ".join(related_counts),
            note="\n\n".join(note_parts),
        )

    def _retrieve_number_one_context(self, text: str, intent: str, routing_results: dict[str, Any]) -> Any:
        if not self.number_one_memory:
            return None
        try:
            return self.number_one_memory.retrieve_context(
                missions=[{"title": text, "description": text, "status": "ACTIVE", "mission_id": intent or "commander"}],
                routing_results=routing_results,
            )
        except Exception as exc:
            log.warning("[commander-memory] number-one memory lookup failed: %s", exc)
            return None
