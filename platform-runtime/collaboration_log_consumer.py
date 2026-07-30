"""
Collaboration Log Consumer
Owner: Knowledge Officer
Date: 2026-06-13
Purpose: Log collaboration outputs to disk and surface coordination context
         to the Knowledge Officer retrieval path.

Two responsibilities:
1. log_collaboration_output() — called after each collaboration run to persist
   the multi-specialist response to slack-bot/logs/collaboration.jsonl
2. surface_collaboration_context() — retrieve recent collaboration outputs
   relevant to a topic query, for surfacing in KO responses.

Public API:
    log_collaboration_output(user_text, response, specialists, mission_id) -> None
    surface_collaboration_context(topic, limit) -> str
    get_recent_collaboration_entries(limit) -> list[dict]
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


_BOT_DIR = Path(__file__).resolve().parent
_LOG_FILE = _BOT_DIR / "logs" / "collaboration.jsonl"


def log_collaboration_output(
    user_text: str,
    response: str,
    specialists: list[str] | None = None,
    mission_id: str | None = None,
) -> None:
    """Append a collaboration session to the JSONL log. Non-blocking — failures are silent."""
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "mission_id": mission_id or "",
            "user_text": user_text[:500],
            "specialists": specialists or [],
            "response_preview": response[:800],
        }
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def get_recent_collaboration_entries(limit: int = 20) -> list[dict]:
    """Return the most recent collaboration log entries."""
    if not _LOG_FILE.exists():
        return []
    entries: list[dict] = []
    try:
        lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries) >= limit:
                break
    except OSError:
        pass
    return entries


def surface_collaboration_context(topic: str, limit: int = 3) -> str:
    """Find recent collaboration entries relevant to a topic and return a formatted summary."""
    keywords = set(re.sub(r"[^a-z0-9 ]", " ", topic.lower()).split())
    keywords -= {"the", "a", "an", "to", "for", "and", "or", "of", "in", "is"}
    if not keywords:
        return ""

    entries = get_recent_collaboration_entries(limit=50)
    matches: list[dict] = []
    for entry in entries:
        text = (entry.get("user_text", "") + " " + entry.get("response_preview", "")).lower()
        overlap = sum(1 for kw in keywords if kw in text)
        if overlap >= 2:
            matches.append({**entry, "_overlap": overlap})

    if not matches:
        return ""

    matches.sort(key=lambda e: e["_overlap"], reverse=True)
    matches = matches[:limit]

    lines = [":speech_balloon: *Prior coordination on this topic:*"]
    for m in matches:
        ts = m.get("timestamp", "")[:10]
        text_preview = m.get("user_text", "")[:60]
        specialists = ", ".join(m.get("specialists", []))
        lines.append(f"  • `{ts}` — {text_preview}... (specialists: {specialists or 'unknown'})")

    return "\n".join(lines)
