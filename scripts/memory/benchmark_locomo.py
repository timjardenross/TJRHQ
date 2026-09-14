#!/usr/bin/env python3
"""Stream 6 validation benchmark — USS-TJR-MSN-0378 ("Living Memory Across
the Ship"). A small, private LoCoMo-style eval built from the Captain's
real Command Memory (`decisions` table), per the mission's own instruction
("this is the mission's actual acceptance gate for Streams 3-5, not a
nice-to-have").

Honesty note on scope (read before trusting the numbers below): the
Stream 5 nightly job only ever ingests a trailing 24h window of
`decisions` — it has never run against this mission's real historical
Command Memory (65 rows, oldest from 2026-06-14), and won't, by design.
So this benchmark does its own one-time seed step (`seed_graphiti()`)
that mirrors a sample of real historical decisions into Graphiti via
memory_graph.add_fact() — separate from, and not a substitute for, the
nightly job's ongoing trailing-window behaviour. This is what actually
lets Stream 6 measure something real today instead of waiting on organic
accumulation.

Methodology (deliberately simple, not an LLM-judge pipeline): for each
sampled decision, the question is built from `reasoning` and the expected
answer is `outcome`. A hit is scored when memory_graph.search() returns at
least one fact, among the top `num_results`, sharing >= MIN_SHARED_TOKENS
non-trivial words with the expected outcome. This is a token-overlap
heuristic, not semantic equivalence scoring — documented here so the
score is read as what it is, an approximation, not a rigorous LoCoMo
metric.

Two conditions are scored for comparison:
  1. "graphiti"       — memory_graph.search() after seeding (the Stream
                         3-5 consolidated architecture's actual retrieval
                         path for RELATIONSHIPS).
  2. "command_table"  — unified_memory.recall(COMMAND, query=...) — the
                         PRE-EXISTING architecture. This is expected to
                         score 0%: _recall_table() only supports exact-
                         match `.eq()` filters, and "query" is not a real
                         column on `decisions` — there is no natural-
                         language recall capability on this path at all,
                         confirmed by actually calling it, not assumed.

Run: python3 -m scripts.memory.benchmark_locomo
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from core.platform.configuration_service import load_dotenv_files

load_dotenv_files([_REPO_ROOT / ".env", _REPO_ROOT / "platform-runtime" / ".env"])

log = logging.getLogger(__name__)

_SAMPLE_SIZE = 8
_MIN_SHARED_TOKENS = 3
_GROUP_ID = "command-memory-benchmark"
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for",
    "with", "was", "is", "are", "be", "this", "that", "it", "as", "at",
    "by", "not", "no", "than", "then", "so", "if", "into", "via", "over",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _supabase_raw():
    from tools.supabase.client import CommanderSupabaseClient
    return CommanderSupabaseClient().raw_client


def _fetch_sample() -> list[dict]:
    db = _supabase_raw()
    if db is None:
        return []
    rows = (
        db.table("decisions")
        .select("mission_id,decision_type,reasoning,outcome,timestamp")
        .not_.is_("reasoning", "null")
        .not_.is_("outcome", "null")
        .order("timestamp", desc=True)
        .limit(_SAMPLE_SIZE)
        .execute()
        .data
        or []
    )
    return [r for r in rows if len(r.get("reasoning") or "") > 20 and len(r.get("outcome") or "") > 10]


def _parse_timestamp(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


async def seed_graphiti(rows: list[dict]) -> int:
    """One-time seed: mirror sampled historical decisions into Graphiti so
    there's something real for the RELATIONSHIPS path to retrieve. Uses
    memory_graph.add_fact() directly (not unified_memory.remember(), which
    would also work but this keeps the benchmark independent of that call
    chain so a bug in remember() doesn't mask/inflate the graph's own
    retrieval quality)."""
    from core.platform import memory_graph

    seeded = 0
    for row in rows:
        text = f"{row['reasoning']} -> {row['outcome']}"
        ok = await memory_graph.add_fact(
            text,
            name=f"benchmark-seed:{row.get('mission_id') or 'none'}:{row['timestamp']}",
            group_id=_GROUP_ID,
            workbench="command-memory",
            reference_time=_parse_timestamp(row.get("timestamp")),
        )
        if ok:
            seeded += 1
    return seeded


async def score_graphiti(rows: list[dict]) -> dict:
    from core.platform import memory_graph

    hits = 0
    details = []
    for row in rows:
        question = f"What was decided regarding: {row['reasoning']}"
        expected_tokens = _tokens(row["outcome"])
        results = await memory_graph.search(question, num_results=5, group_ids=[_GROUP_ID])
        hit = any(len(_tokens(r["fact"]) & expected_tokens) >= _MIN_SHARED_TOKENS for r in results)
        hits += int(hit)
        details.append({"question": question, "hit": hit, "results_returned": len(results)})
    return {"hits": hits, "total": len(rows), "rate": hits / len(rows) if rows else 0.0, "details": details}


def score_command_table(rows: list[dict]) -> dict:
    from core.platform.unified_memory import MemoryType, recall

    hits = 0
    for row in rows:
        question = f"What was decided regarding: {row['reasoning']}"
        # This is the actual, real call an caller would make today for a
        # natural-language question against Command Memory — "query" is
        # not a real column, so _recall_table's .eq("query", question)
        # matches nothing. Calling it for real, not asserting the
        # limitation from documentation.
        results = recall(MemoryType.COMMAND, query=question)
        if results:
            hits += 1
    return {"hits": hits, "total": len(rows), "rate": hits / len(rows) if rows else 0.0}


async def run() -> dict:
    rows = _fetch_sample()
    if not rows:
        return {"status": "skipped", "reason": "no eligible decisions rows found"}

    seeded = await seed_graphiti(rows)
    graphiti_result = await score_graphiti(rows)
    command_table_result = score_command_table(rows)

    report = {
        "status": "ok",
        "sample_size": len(rows),
        "seeded_into_graphiti": seeded,
        "graphiti": {"hits": graphiti_result["hits"], "total": graphiti_result["total"], "rate": graphiti_result["rate"]},
        "command_table_baseline": command_table_result,
    }
    log.info("[benchmark-locomo] %s", json.dumps(report, indent=2))
    return {**report, "graphiti_details": graphiti_result["details"]}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(run())
    print(json.dumps(result, indent=2))
