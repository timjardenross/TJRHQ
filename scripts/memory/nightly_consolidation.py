#!/usr/bin/env python3
"""Nightly memory consolidation — USS-TJR-MSN-0378 Stream 5.

Reflection/consolidation pattern (Generative-Agents-style write-back), not a
raw-history dump: reads recent conversation_turns (Stream 2) and Command
Memory (`decisions`), asks an LLM to distil each into a short list of
standalone facts worth remembering long-term, and writes each fact into
Graphiti via core/platform/unified_memory.py's remember() (Stream 5's
required write path — only exists because of the RELATIONSHIPS write-path
fix landed alongside this script, see memory_graph.add_fact()).

Idempotency:
- conversation_turns rows are marked via `consolidated_at` (added in
  migration 0208 specifically for this job) once processed, so a turn is
  never re-distilled on a later run.
- `decisions` (Command Memory) has no such marker column — this job reads a
  trailing 24h window each run instead. Running this nightly means at most
  one night's overlap if the job is skipped a night; it does NOT dedup
  against facts already written to Graphiti from a previous night. This is
  a known, accepted limitation (documented here and in the mission's
  knowledge record) rather than a silent gap — adding real dedup would mean
  either a decisions.consolidated_at column (a real schema change to a
  table this mission didn't scope touching) or content-hash comparison
  against existing Graphiti episodes, neither of which this Stream commits
  to building.

Run manually: python3 -m scripts.memory.nightly_consolidation
Scheduled via a cron entry (see the mission's knowledge record for the
exact schedule) — this script is a single batch pass, not a long-running
service.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from core.platform.configuration_service import load_dotenv_files

load_dotenv_files([_REPO_ROOT / ".env", _REPO_ROOT / "platform-runtime" / ".env"])

log = logging.getLogger(__name__)

_TURNS_BATCH_LIMIT = 500
_DECISIONS_WINDOW_HOURS = 24

_DISTILL_SYSTEM_PROMPT = (
    "You distil a raw transcript into a short list of standalone facts worth "
    "remembering long-term about the Captain's situation, decisions, or "
    "context. Each fact must stand alone (no 'he said' / 'as mentioned "
    "above' — write it as a fact a reader with no other context could use). "
    "Skip small talk, acknowledgements, and anything not worth recalling "
    "days or weeks from now. Return ONLY a JSON array of strings, no other "
    "text. If nothing is worth keeping, return []."
)


def _supabase_raw():
    from tools.supabase.client import CommanderSupabaseClient
    return CommanderSupabaseClient().raw_client


async def _distill(transcript: str) -> list[str]:
    """Ask the LLM for a JSON array of standalone facts. Returns [] on any
    failure — a consolidation miss is never worse than the raw turns
    simply staying unconsolidated until the next run."""
    if not transcript.strip():
        return []
    from telegram_bots.llm import generate_async

    try:
        reply = await generate_async(transcript, _DISTILL_SYSTEM_PROMPT)
    except Exception as exc:  # noqa: BLE001 - LLM call surface is unpredictable, already logged
        log.warning("[nightly-consolidation] LLM distillation call failed: %s", exc)
        return []
    if not reply:
        return []
    try:
        facts = json.loads(reply)
    except json.JSONDecodeError:
        log.warning("[nightly-consolidation] LLM reply wasn't valid JSON, skipping: %r", reply[:200])
        return []
    if not isinstance(facts, list):
        return []
    return [str(f).strip() for f in facts if str(f).strip()]


async def consolidate_conversation_turns(db) -> dict[str, int]:
    """Distil unconsolidated conversation_turns (per chat_id) into Graphiti facts."""
    from core.platform.unified_memory import MemoryType, remember

    rows = (
        db.table("conversation_turns")
        .select("id,chat_id,role,text,created_at")
        .is_("consolidated_at", "null")
        .order("chat_id")
        .order("created_at")
        .limit(_TURNS_BATCH_LIMIT)
        .execute()
        .data
        or []
    )
    if not rows:
        return {"turns_read": 0, "facts_written": 0}

    by_chat: dict[int, list[dict]] = {}
    for row in rows:
        by_chat.setdefault(row["chat_id"], []).append(row)

    facts_written = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for chat_id, turns in by_chat.items():
        transcript = "\n".join(f"{t['role']}: {t['text']}" for t in turns)
        facts = await _distill(transcript)
        for fact in facts:
            result = remember(
                MemoryType.RELATIONSHIPS, fact, user_id="captain",
                metadata={"workbench": "xo"},
            )
            if result:
                facts_written += 1
        ids = [t["id"] for t in turns]
        try:
            db.table("conversation_turns").update({"consolidated_at": now_iso}).in_("id", ids).execute()
        except Exception as exc:  # noqa: BLE001 - marking-done failure shouldn't crash the batch; worst case these turns get re-distilled next run
            log.warning("[nightly-consolidation] failed to mark %d turns consolidated for chat_id=%s: %s", len(ids), chat_id, exc)

    return {"turns_read": len(rows), "facts_written": facts_written}


async def consolidate_command_memory(db) -> dict[str, int]:
    """Distil the last _DECISIONS_WINDOW_HOURS of Command Memory (`decisions`)
    into Graphiti facts. See module docstring for the no-dedup limitation."""
    from core.platform.unified_memory import MemoryType, remember

    since = (datetime.now(timezone.utc) - timedelta(hours=_DECISIONS_WINDOW_HOURS)).isoformat()
    rows = (
        db.table("decisions")
        .select("mission_id,decision_type,reasoning,outcome,timestamp")
        .gte("timestamp", since)
        .order("timestamp")
        .execute()
        .data
        or []
    )
    if not rows:
        return {"decisions_read": 0, "facts_written": 0}

    transcript = "\n".join(
        f"[{d.get('mission_id')}] {d.get('decision_type')}: {d.get('reasoning')} -> {d.get('outcome')}"
        for d in rows
    )
    facts = await _distill(transcript)
    facts_written = 0
    for fact in facts:
        result = remember(
            MemoryType.RELATIONSHIPS, fact, user_id="captain",
            metadata={"workbench": "command-memory"},
        )
        if result:
            facts_written += 1

    return {"decisions_read": len(rows), "facts_written": facts_written}


async def run() -> dict[str, Any]:
    db = _supabase_raw()
    if db is None:
        log.warning("[nightly-consolidation] Supabase unavailable — nothing to do")
        return {"status": "skipped", "reason": "supabase unavailable"}

    turns_result = await consolidate_conversation_turns(db)
    decisions_result = await consolidate_command_memory(db)
    result = {"status": "ok", "turns": turns_result, "decisions": decisions_result}
    log.info("[nightly-consolidation] %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
