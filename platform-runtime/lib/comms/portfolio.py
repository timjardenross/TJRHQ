"""Reputation Portfolio + content lifecycle store (COMMS-001 WP7/WP1/WP8).

A single consolidated, additive store (``comms_content``) for the content
lifecycle: opportunity → draft → approved → published. The published slice IS the
professional reputation portfolio (WP7). Reuses the graceful CommanderSupabaseClient
— no separate content system. All writes are non-blocking; reads degrade to empty.

Captain-as-publisher: recording an item as ``published`` is a record of what the
Captain chose to publish — the system never publishes anything itself.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

CONTENT_TABLE = "comms_content"
PIPELINE_VIEW = "comms_pipeline"
PORTFOLIO_VIEW = "comms_portfolio"

STATUSES = ("opportunity", "draft", "approved", "published", "archived")


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() else None
    except Exception as exc:  # pragma: no cover
        log.warning("[comms.portfolio] Supabase unavailable: %s", exc)
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_content(*, content_id: str, title: str, pillar: str | None = None,
                   source_kind: str | None = None, source_ref: str | None = None,
                   classification: str = "publishable", status: str = "opportunity",
                   fmt: str | None = None, strategic_domain: str | None = None,
                   notes: str | None = None) -> bool:
    """Persist/advance a content item in its lifecycle. Non-blocking.

    Returns False (without raising) when the store is unavailable."""
    c = _client()
    if c is None:
        return False
    status = status if status in STATUSES else "opportunity"
    payload = {
        "content_id": content_id, "title": title[:300], "pillar": pillar,
        "source_kind": source_kind, "source_ref": source_ref,
        "classification": classification, "status": status, "format": fmt,
        "strategic_domain": strategic_domain, "notes": (notes or None),
        "updated_at": _now(),
    }
    try:
        result = c.insert(CONTENT_TABLE, payload)
        ok = bool(getattr(result, "ok", False))
        if ok:
            # MSN-0328 Wave 2: canonical Captain Brief pipeline event.
            # domain='content-intelligence' — already mapped to the
            # 'opportunities' section (captain_brief_orchestrator.py),
            # no new mapping needed. Non-blocking.
            try:
                from core.platform.event_bus import publish_event
                publish_event(
                    "comms.content_recorded", domain="content-intelligence",
                    source="comms-portfolio", recommended_action=title,
                )
            except Exception:
                pass
        return ok
    except Exception as exc:  # pragma: no cover
        log.warning("[comms.portfolio] record_content failed: %s", exc)
        return False


@dataclass
class PortfolioItem:
    title: str
    pillar: str | None
    status: str
    strategic_domain: str | None


def fetch_portfolio(*, status: str = "published", limit: int = 50) -> list[PortfolioItem]:
    """WP7: published reputation items (or any lifecycle status). Empty when offline."""
    c = _client()
    if c is None or c.raw_client is None:
        return []
    try:
        res = (c.raw_client.table(CONTENT_TABLE)
               .select("title,pillar,status,strategic_domain")
               .eq("status", status).limit(limit).execute())
        return [PortfolioItem(title=str(r.get("title") or ""), pillar=r.get("pillar"),
                              status=str(r.get("status") or ""),
                              strategic_domain=r.get("strategic_domain"))
                for r in (res.data or [])]
    except Exception as exc:  # pragma: no cover
        log.warning("[comms.portfolio] fetch_portfolio failed: %s", exc)
        return []


def pipeline_summary() -> dict[str, int]:
    """Counts by lifecycle status (WP5 presence dashboard). Empty when offline."""
    c = _client()
    if c is None or c.raw_client is None:
        return {}
    try:
        res = c.raw_client.table(CONTENT_TABLE).select("status").limit(1000).execute()
        counts: dict[str, int] = {}
        for r in (res.data or []):
            s = str(r.get("status") or "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts
    except Exception as exc:  # pragma: no cover
        log.warning("[comms.portfolio] pipeline_summary failed: %s", exc)
        return {}
