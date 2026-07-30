"""Shared compact formatting helpers for advisory memory output."""

from __future__ import annotations

from typing import Any


def format_memory_block(
    *,
    label: str,
    items: list[dict[str, Any]] | list[Any],
    source_types: list[str],
    summary: str = "",
    confidence: float | None = None,
    max_items: int = 3,
) -> str:
    """Render a compact advisory-only memory block."""
    rendered_items: list[str] = []
    for item in items[:max_items]:
        if isinstance(item, dict):
            identifier = str(item.get("mission_id") or item.get("decision_id") or item.get("source_id") or item.get("id") or "")
            status = str(item.get("status") or item.get("source_status") or "").strip()
            reason = str(item.get("reason") or item.get("summary") or "").strip()
            parts = [part for part in [identifier, status, reason] if part]
            rendered_items.append(" - ".join(parts) if parts else str(item))
        else:
            rendered_items.append(str(item))

    lines: list[str] = []
    header = f"{label}:"
    if confidence is not None:
        header = f"{header} {int(max(0.0, min(confidence, 1.0)) * 100)}%"
    lines.append(header)

    if summary:
        lines.append(summary[:220])

    if rendered_items:
        lines.extend(f"- {item}" for item in rendered_items)

    if source_types:
        lines.append("Sources: " + ", ".join(source_types[:4]))

    return "\n".join(lines).strip()

