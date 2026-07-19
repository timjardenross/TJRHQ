"""Captain's Inbox — Processing Orchestrator (WP3B)

Async, best-effort enrichment pipeline. Called after an item is captured.
Capture is mandatory; this pipeline is optional — failures never surface to
the user and never block storage.

Pipeline (all steps best-effort):
  1. Classify (research / decision / mission / reference / personal)
  2. Rate importance (low / medium / high / critical)
  3. Generate summary (truncation for MVP; upgrade to LLM later)
  4. Detect duplicates (check existing source_url)
  5. Governance assessment (via GovernanceContextService, cached in DB)
  6. Mark processing_status = 'completed'
  7. Research (Mistral agents) — async, non-blocking; fires for research/mission/decision
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase R/W helper (shared with governance_integration)
# ---------------------------------------------------------------------------

class _DB:
    """Minimal read/write Supabase wrapper."""

    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self._client = None
        if self.url and self.key:
            try:
                from supabase import create_client
                self._client = create_client(self.url, self.key)
            except Exception:
                pass

    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def get(self, table: str, item_id: str) -> dict | None:
        if not self._client:
            return None
        try:
            result = self._client.table(table).select("*").eq("id", item_id).limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as exc:
            log.warning("[inbox-orchestrator] get failed on %s id=%s: %s", table, item_id, exc)
            return None

    def update(self, table: str, item_id: str, payload: dict) -> bool:
        if not self._client:
            return False
        try:
            self._client.table(table).update(payload).eq("id", item_id).execute()
            return True
        except Exception as exc:
            log.warning("[inbox-orchestrator] update failed on %s id=%s: %s", table, item_id, exc)
            return False

    def exists_url(self, source_url: str, exclude_id: str) -> str | None:
        """Return id of existing non-duplicate with same URL, or None."""
        if not self._client or not source_url:
            return None
        try:
            result = (
                self._client.table("captured_items")
                .select("id")
                .eq("source_url", source_url)
                .eq("duplicate_detected", False)
                .neq("id", exclude_id)
                .limit(1)
                .execute()
            )
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None


_db = _DB()

# ---------------------------------------------------------------------------
# Classification (keyword-based, MVP)
# ---------------------------------------------------------------------------

_CLASSIFICATION_RULES: list[tuple[str, list[str]]] = [
    ("decision", ["decide", "decision", "should we", "option", "trade-off", "tradeoff", "adr", "approved", "rejected"]),
    ("mission", ["mission", "objective", "goal", "initiative", "sprint", "milestone", "roadmap"]),
    ("research", ["research", "paper", "study", "analysis", "findings", "benchmark", "survey", "report", "article"]),
    ("reference", ["docs", "documentation", "guide", "tutorial", "how to", "reference", "api", "spec", "specification"]),
    ("personal", ["meeting", "call", "note", "reminder", "follow up", "todo", "action item"]),
]

_IMPORTANCE_RULES: list[tuple[str, list[str]]] = [
    ("critical", ["critical", "urgent", "blocker", "security", "vulnerability", "breach", "outage", "incident"]),
    ("high", ["important", "priority", "deadline", "production", "release", "launch", "compliance", "risk"]),
    ("medium", ["consider", "review", "worth", "interesting", "useful", "relevant"]),
    ("low", ["fyi", "for your information", "optional", "minor", "nice to have"]),
]


def _classify(text: str) -> str:
    lower = text.lower()
    scores: dict[str, int] = {}
    for label, keywords in _CLASSIFICATION_RULES:
        score = sum(1 for kw in keywords if kw in lower)
        if score:
            scores[label] = score
    if not scores:
        return "unclassified"
    return max(scores, key=lambda k: scores[k])


def _rate_importance(text: str) -> str:
    lower = text.lower()
    for label, keywords in _IMPORTANCE_RULES:
        if any(kw in lower for kw in keywords):
            return label
    return "medium"


def _summarize(item: dict) -> tuple[str, str]:
    """Return (summary_text, summary_source)."""
    raw = (item.get("raw_text") or "").strip()
    title = item.get("title", "")
    url = item.get("source_url", "")

    # For URL captures without meaningful body text, use title + url
    if not raw or len(raw) < 20:
        parts = [p for p in [title, url] if p]
        return " — ".join(parts)[:500], "auto_truncated"

    # Truncate to first 400 chars, ending on a word boundary
    if len(raw) <= 400:
        return raw, "auto_truncated"
    truncated = raw[:400].rsplit(" ", 1)[0]
    return truncated + "…", "auto_truncated"


# ---------------------------------------------------------------------------
# Research (Mistral agents) — step 7, fires async after pipeline completes
# ---------------------------------------------------------------------------

# Classifications that warrant autonomous research
_RESEARCH_CLASSIFICATIONS = {"research", "mission", "decision", "unclassified"}


def _build_research_topic(item: dict) -> str:
    """Compose a research topic string from the captured item (10–1000 chars)."""
    title = (item.get("title") or "").strip()
    raw = (item.get("raw_text") or "").strip()
    topic = f"{title} — {raw}" if (title and raw) else title or raw
    topic = topic.strip(" —")
    if len(topic) < 10:
        topic = topic + " — provide an overview and key considerations"
    return topic[:1000]


def _run_research(item_id: str, item: dict) -> None:
    """
    Background thread: call ResearchOrchestrator then persist results.
    All failures are non-blocking — sets research_status='failed' and logs.
    """
    try:
        from core.coordination.research_orchestration import ResearchOrchestrator
    except Exception as exc:
        log.warning("[inbox-orchestrator] ResearchOrchestrator import failed (skipping research): %s", exc)
        _db.update("captured_items", item_id, {"research_status": "failed"})
        return

    _db.update("captured_items", item_id, {"research_status": "running"})
    try:
        topic = _build_research_topic(item)
        result = ResearchOrchestrator().run_research_mission(
            research_topic=topic,
            mission_id=item_id,
        )
        _db.update("captured_items", item_id, {
            "research_status": "completed" if result.status in ("success", "partial") else "failed",
            "research_findings": result.consolidated_findings or "",
            "research_brief": result.captains_brief or "",
            "research_mission_id": result.mission_id,
            "research_confidence": result.confidence,
        })
        log.info(
            "[inbox-orchestrator] Research complete item_id=%s status=%s confidence=%.2f provider=%s",
            item_id, result.status, result.confidence, result.primary_provider,
        )
    except Exception as exc:
        log.error("[inbox-orchestrator] Research failed for %s: %s", item_id, exc)
        _db.update("captured_items", item_id, {"research_status": "failed"})


# ---------------------------------------------------------------------------
# Main orchestration entry point
# ---------------------------------------------------------------------------

def process_captured_item(item_id: str) -> None:
    """
    Enrich a captured item. Best-effort — any failure is logged and
    processing_status is set to 'failed' so the item can be retried.
    Never raises.
    """
    if not _db.enabled():
        log.warning("[inbox-orchestrator] Supabase not configured — skipping processing for %s", item_id)
        return

    try:
        _db.update("captured_items", item_id, {"processing_status": "in_progress"})
        item = _db.get("captured_items", item_id)
        if not item:
            log.warning("[inbox-orchestrator] Item not found: %s", item_id)
            return

        updates: dict[str, Any] = {}

        # 1. Classify
        text = f"{item.get('title', '')} {item.get('raw_text', '')} {item.get('source_url', '')}"
        updates["classification"] = _classify(text)

        # 2. Rate importance
        updates["importance"] = _rate_importance(text)

        # 3. Summarize
        summary, summary_source = _summarize(item)
        updates["summary"] = summary
        updates["summary_source"] = summary_source

        # 4. Duplicate detection
        if item.get("source_url"):
            existing_id = _db.exists_url(item["source_url"], item_id)
            if existing_id:
                updates["duplicate_detected"] = True
                updates["duplicate_of"] = existing_id
                log.info("[inbox-orchestrator] Duplicate detected: %s → %s", item_id, existing_id)

        # 5. Governance assessment (via governance_integration)
        try:
            from core.inbox.governance_integration import apply_governance_assessment
            gov_updates = apply_governance_assessment(item)
            updates.update(gov_updates)
        except Exception as gov_exc:
            log.warning("[inbox-orchestrator] Governance assessment failed (non-blocking): %s", gov_exc)
            updates["governance_status"] = "failed"

        # 6. Mark complete
        updates["processing_status"] = "completed"
        updates["last_processed_at"] = datetime.now(timezone.utc).isoformat()
        updates["processing_confidence"] = 0.7  # rule-based baseline

        # 7. Queue research for actionable classifications (non-blocking)
        classification = updates.get("classification", "")
        is_duplicate = updates.get("duplicate_detected", False)
        if classification in _RESEARCH_CLASSIFICATIONS and not is_duplicate:
            updates["research_status"] = "pending"

        _db.update("captured_items", item_id, updates)
        log.info(
            "[inbox-orchestrator] Processed item_id=%s classification=%s importance=%s governance=%s",
            item_id,
            updates.get("classification"),
            updates.get("importance"),
            updates.get("governance_status"),
        )

        # Fire research in a daemon thread so it never blocks the capture response
        if classification in _RESEARCH_CLASSIFICATIONS and not is_duplicate:
            t = threading.Thread(
                target=_run_research,
                args=(item_id, item),
                daemon=True,
                name=f"inbox-research-{item_id[:8]}",
            )
            t.start()
            log.info("[inbox-orchestrator] Research thread launched for item_id=%s topic=%s", item_id, _build_research_topic(item)[:80])

    except Exception as exc:
        log.error("[inbox-orchestrator] Processing failed for %s: %s", item_id, exc)
        try:
            _db.update("captured_items", item_id, {
                "processing_status": "failed",
                "processing_errors": [str(exc)],
            })
        except Exception:
            pass
