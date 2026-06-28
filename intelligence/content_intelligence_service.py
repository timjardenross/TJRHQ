"""
Content Intelligence Service (USS-TJR-MSN-0202)

Interpretation layer over existing intelligence and communications architecture.
Asks: "Given what we collected today, what should the Captain write about?"

This module:
  1. Reads recent intelligence_events from Supabase (already collected by ORI pipeline)
  2. Scores each event for content relevance via content_classifier
  3. Ranks with type-adjusted recency decay via content_ranker
  4. Persists content_signals overlay rows (idempotent — safe to re-run)
  5. Returns structured ContentSignalBundle for the portal API

NOT a new ingestion system. No new HTTP calls. Pure interpretation.

Usage:
    from intelligence.content_intelligence_service import ContentIntelligenceService
    svc = ContentIntelligenceService()
    bundle = svc.get_ranked_signals(days=7, limit=10)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from intelligence.classification.content_classifier import ContentScore, score_for_content
from intelligence.ranking.content_ranker import rank_batch

log = logging.getLogger(__name__)

# ── Supabase client (mirrors intelligence_store.py pattern) ──────────────────

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str) -> list:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        log.warning("Supabase not configured — content_intelligence_service returning empty")
        return []
    url = f"{_SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.error("Supabase query failed (%s): %s", path, exc)
        return []


def _post(table: str, payload: dict, on_conflict: Optional[str] = None) -> Optional[dict]:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return None
    url = f"{_SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url += f"?on_conflict={urllib.parse.quote(on_conflict)}"
    headers = _headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result[0] if isinstance(result, list) else result
    except Exception as exc:
        log.error("Supabase insert failed (%s): %s", table, exc)
        return None


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ContentSignal:
    """A single ranked content signal for portal display."""
    event_id: str
    raw_title: str
    source_name: str
    canonical_url: Optional[str]
    pillar_key: str
    pillar_name: str
    content_relevance: float
    rank_score: float
    captain_focus: bool
    suggested_angle: str
    collected_at: str
    useful_life_days: int


@dataclass
class PillarSummary:
    pillar_key: str
    pillar_name: str
    signal_count: int
    top_signal_title: str
    avg_relevance: float


@dataclass
class ContentSignalBundle:
    """Full response for the portal Content Signals tab."""
    generated_at: str
    period_days: int
    total_events_evaluated: int
    total_signals_scored: int
    signals: list[ContentSignal]               # top N, sorted by rank_score
    by_pillar: list[PillarSummary]             # grouped by pillar, for the pillar cards
    captain_focus_count: int


# ── Source registry lookup ────────────────────────────────────────────────────

def _load_source_useful_life() -> dict[str, int]:
    """Returns {source_id: useful_life_days} from intelligence_source_registry."""
    rows = _get(
        "intelligence_source_registry"
        "?select=source_id,useful_life_days,terms_reviewed,content_source"
        "&active=eq.true"
    )
    result: dict[str, int] = {}
    for r in rows:
        life = r.get("useful_life_days")
        result[r["source_id"]] = int(life) if life else 14
    return result


def _load_approved_source_ids() -> set[str]:
    """Returns source_ids where terms_reviewed=true (source governance gate)."""
    rows = _get(
        "intelligence_source_registry"
        "?select=source_id"
        "&active=eq.true"
        "&terms_reviewed=eq.true"
    )
    return {r["source_id"] for r in rows}


def _load_active_mission_keywords() -> list[str]:
    """
    Pulls mission titles and tags from Supabase missions table.
    Returns a flat list of keywords for captain_focus scoring.
    Falls back to empty list gracefully.
    """
    rows = _get("missions?select=title&status=eq.active&limit=20")
    keywords: list[str] = []
    for r in rows:
        if r.get("title"):
            import re
            words = re.findall(r"\w{4,}", r["title"].lower())
            keywords.extend(words)
    return list(set(keywords))


# ── Core service ──────────────────────────────────────────────────────────────

class ContentIntelligenceService:
    """
    Scores recent intelligence_events for content relevance and
    returns a ranked ContentSignalBundle for the portal.

    All Supabase calls are non-blocking — if the DB is unavailable,
    returns an empty bundle rather than raising.
    """

    def score_and_persist(self, days: int = 7) -> int:
        """
        Score recent intelligence_events and persist content_signals overlay rows.
        Idempotent — existing rows are upserted on event_id_text conflict.

        Returns count of signals written.
        """
        since = urllib.parse.quote((datetime.now(timezone.utc) - timedelta(days=days)).isoformat())
        events = _get(
            f"intelligence_events"
            f"?collected_at=gte.{since}"
            f"&suppressed=eq.false"
            f"&order=collected_at.desc"
            f"&limit=500"
        )
        if not events:
            log.info("content_intelligence_service: no events found for last %d days", days)
            return 0

        source_useful_life = _load_source_useful_life()
        approved_sources = _load_approved_source_ids()
        mission_keywords = _load_active_mission_keywords()

        scored: list[tuple[ContentScore, float]] = []
        ori_rank_map: dict[str, float] = {}
        scoreable: list[ContentScore] = []

        for event in events:
            source_id = event.get("source_id", "")
            # Source governance gate: only score events from terms_reviewed sources
            # (all existing ORI sources default to terms_reviewed=false until reviewed)
            # In MVP, we score all non-suppressed events; governance gate applies to
            # future content-specific sources only.
            useful_life = source_useful_life.get(source_id, 14)
            result = score_for_content(event, mission_keywords, useful_life)
            if result is not None:
                scoreable.append(result)
                ori_rank_map[result.event_id_text] = float(event.get("rank_score") or 0.0)

        if not scoreable:
            return 0

        ranked = rank_batch(scoreable, ori_rank_map)
        written = 0
        for cs, rs in ranked:
            row = {
                "event_id": str(uuid.uuid4()),
                "event_id_text": cs.event_id_text,
                "source_name": cs.source_name,
                "pillar_key": cs.pillar_key,
                "pillar_name": cs.pillar_name,
                "content_relevance": cs.content_relevance,
                "captain_focus": cs.captain_focus,
                "rank_score": rs,
                "suggested_angle": cs.suggested_angle,
            }
            result = _post("content_signals", row, on_conflict="event_id_text")
            if result:
                written += 1

        log.info(
            "content_intelligence_service: scored %d events → %d signals written",
            len(events), written,
        )
        return written

    def get_ranked_signals(
        self,
        days: int = 7,
        pillar: Optional[str] = None,
        limit: int = 10,
    ) -> ContentSignalBundle:
        """
        Return a ranked ContentSignalBundle for the portal Content Signals tab.

        Joins content_signals with intelligence_events for title/url/source.
        Falls back gracefully if DB unavailable.
        """
        since = urllib.parse.quote((datetime.now(timezone.utc) - timedelta(days=days)).isoformat())

        # Build filter
        filters = (
            f"scored_at=gte.{since}"
            f"&suppressed=eq.false"
            f"&order=rank_score.desc"
            f"&limit={limit * 3}"  # fetch extra for pillar filtering
        )
        if pillar:
            encoded_pillar = urllib.parse.quote(pillar)
            filters += f"&pillar_key=eq.{encoded_pillar}"

        signal_rows = _get(f"content_signals?{filters}")

        if not signal_rows:
            return ContentSignalBundle(
                generated_at=datetime.now(timezone.utc).isoformat(),
                period_days=days,
                total_events_evaluated=0,
                total_signals_scored=0,
                signals=[],
                by_pillar=[],
                captain_focus_count=0,
            )

        # Fetch corresponding intelligence_events for title/summary/url
        event_ids = [r["event_id_text"] for r in signal_rows if r.get("event_id_text")]
        event_map: dict[str, dict] = {}
        if event_ids:
            # Supabase IN filter with text array
            id_list = ",".join(event_ids)
            events = _get(
                f"intelligence_events"
                f"?event_id=in.({id_list})"
                f"&select=event_id,raw_title,raw_summary,canonical_url,collected_at"
            )
            for e in events:
                event_map[e["event_id"]] = e

        # Total events evaluated this period (for the summary header)
        total_rows = _get(
            f"intelligence_events"
            f"?collected_at=gte.{since}"
            f"&suppressed=eq.false"
            f"&select=event_id"
            f"&limit=1000"
        )  # since is already URL-encoded
        total_evaluated = len(total_rows)

        # Build signal objects
        signals: list[ContentSignal] = []
        for r in signal_rows:
            eid = r.get("event_id_text", "")
            ev = event_map.get(eid, {})
            signals.append(ContentSignal(
                event_id=eid,
                raw_title=ev.get("raw_title") or r.get("raw_title") or "(no title)",
                source_name=r.get("source_name", ""),
                canonical_url=ev.get("canonical_url"),
                pillar_key=r.get("pillar_key", ""),
                pillar_name=r.get("pillar_name", ""),
                content_relevance=float(r.get("content_relevance") or 0.0),
                rank_score=float(r.get("rank_score") or 0.0),
                captain_focus=bool(r.get("captain_focus", False)),
                suggested_angle=r.get("suggested_angle", ""),
                collected_at=ev.get("collected_at") or r.get("scored_at", ""),
                useful_life_days=14,
            ))

        signals = signals[:limit]

        # Build pillar summary
        by_pillar = _summarise_by_pillar(signal_rows, event_map)

        return ContentSignalBundle(
            generated_at=datetime.now(timezone.utc).isoformat(),
            period_days=days,
            total_events_evaluated=total_evaluated,
            total_signals_scored=len(signal_rows),
            signals=signals,
            by_pillar=by_pillar,
            captain_focus_count=sum(1 for s in signals if s.captain_focus),
        )


def _summarise_by_pillar(
    signal_rows: list[dict],
    event_map: dict[str, dict],
) -> list[PillarSummary]:
    pillar_groups: dict[str, list[dict]] = {}
    for r in signal_rows:
        pk = r.get("pillar_key", "unknown")
        pillar_groups.setdefault(pk, []).append(r)

    summaries: list[PillarSummary] = []
    for pk, rows in pillar_groups.items():
        top = max(rows, key=lambda r: float(r.get("rank_score") or 0.0))
        top_ev = event_map.get(top.get("event_id_text", ""), {})
        summaries.append(PillarSummary(
            pillar_key=pk,
            pillar_name=rows[0].get("pillar_name", pk),
            signal_count=len(rows),
            top_signal_title=top_ev.get("raw_title") or top.get("raw_title") or "",
            avg_relevance=round(
                sum(float(r.get("content_relevance") or 0.0) for r in rows) / len(rows), 3
            ),
        ))

    summaries.sort(key=lambda s: s.signal_count, reverse=True)
    return summaries
