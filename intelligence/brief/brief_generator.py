"""
Brief generation service.

Assembles a ResilienceBrief from ranked events.
Structural content (events, scores, metadata) is always present.
Narrative sections use LLM; degrade gracefully if all providers fail.

The generator does NOT fabricate events. All content is derived from
collected, classified, and ranked IntelligenceItems.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from intelligence.brief.llm_provider import LLMProvider
from intelligence.classification.classifier import classify
from intelligence.classification.filter import apply_filter
from intelligence.config import BRIEF_PERIOD_DAYS, TOP_EVENTS_LIMIT
from intelligence.ingestion.collection_engine import collect_all
from intelligence.models import (
    BriefEvent, ClassifiedEvent, RankedEvent, ResilienceBrief, SourceHealth
)
from intelligence.persistence import intelligence_store as store
from intelligence.ranking.ranker import rank, top_events

log = logging.getLogger(__name__)

_RISK_LABELS = {
    "RED":     "🔴 RED",
    "AMBER":   "🟡 AMBER",
    "GREEN":   "🟢 GREEN",
    "UNKNOWN": "⚪ UNKNOWN",
}


class BriefGenerator:

    def __init__(self, trigger_type: str = "on_demand"):
        self.trigger_type = trigger_type
        self.llm = LLMProvider()

    def generate(
        self,
        period_days: int = BRIEF_PERIOD_DAYS,
        sources=None,
    ) -> ResilienceBrief:
        """
        Full pipeline: collect → classify → filter → rank → generate brief.
        Always returns a ResilienceBrief, even in degraded state.
        """
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)
        period_end   = now

        log.info("Starting brief generation: period=%d days, trigger=%s",
                 period_days, self.trigger_type)

        # ── 1. Collection ─────────────────────────────────────────────────────
        items, health_records = collect_all(sources=sources)
        sources_checked   = len(health_records)
        sources_available = sum(1 for h in health_records if h.status in ("ok", "degraded"))
        sources_failed    = sum(1 for h in health_records if h.status == "failed")
        sources_stale     = sum(1 for h in health_records if h.status in ("stale", "degraded"))

        log.info("Collected %d items from %d sources", len(items), sources_checked)

        # ── 2. Classify ───────────────────────────────────────────────────────
        classified: list[ClassifiedEvent] = []
        dedup_hashes_seen: set[str] = set()

        for item in items:
            event = classify(item)

            # Skip duplicates already in this collection run
            if event.dedup_hash in dedup_hashes_seen:
                continue
            dedup_hashes_seen.add(event.dedup_hash)

            # Skip if already persisted (previous run)
            if store.event_hash_exists(event.dedup_hash):
                continue

            classified.append(event)

        events_evaluated = len(classified)
        log.info("Classified %d new events", events_evaluated)

        # ── 3. Filter ─────────────────────────────────────────────────────────
        apply_filter(classified)
        events_suppressed = sum(1 for e in classified if e.suppressed)

        # ── 4. Rank ───────────────────────────────────────────────────────────
        ranked = rank(classified, period_start=period_start)
        top5   = top_events(ranked, limit=TOP_EVENTS_LIMIT)
        events_included = len(top5)

        # ── 5. Persist events ─────────────────────────────────────────────────
        persisted_ids: list[str] = []
        for event in ranked:
            eid = store.save_event(event)
            if eid and not event.suppressed:
                persisted_ids.append(eid)

        # ── 6. Determine overall risk ─────────────────────────────────────────
        overall_risk = self._compute_risk(top5)

        # ── 7. Build BriefEvent snapshots ─────────────────────────────────────
        brief_events = [self._to_brief_event(e) for e in top5]

        # ── 8. Generate narrative (LLM, may fail) ─────────────────────────────
        (executive_snapshot, emerging_themes, forward_watch,
         cps230_implications, bottom_line, llm_used, provider_used) = \
            self._generate_narrative(top5, brief_events, period_start, period_end,
                                     sources_available, sources_failed)

        # ── 9. Assemble brief ─────────────────────────────────────────────────
        brief_id = str(uuid.uuid4())
        confidence = round(
            sum(e.confidence for e in top5) / len(top5) if top5 else 0.0, 2
        )

        brief = ResilienceBrief(
            brief_id=brief_id,
            generated_at=now,
            period_start=period_start,
            period_end=period_end,
            sources_checked=sources_checked,
            sources_available=sources_available,
            sources_failed=sources_failed,
            sources_stale=sources_stale,
            events_evaluated=events_evaluated,
            events_included=events_included,
            events_suppressed=events_suppressed,
            top_events=brief_events,
            overall_risk=overall_risk,
            executive_snapshot=executive_snapshot,
            emerging_themes=emerging_themes,
            forward_watch=forward_watch,
            cps230_implications=cps230_implications,
            bottom_line=bottom_line,
            narrative_available=llm_used,
            llm_used=llm_used,
            provider_used=provider_used,
            confidence=confidence,
            trigger_type=self.trigger_type,
        )

        # ── 10. Persist brief and link events ────────────────────────────────
        saved_id = store.save_brief(brief)
        if saved_id and persisted_ids:
            store.link_events_to_brief(persisted_ids[:events_included], saved_id)

        log.info(
            "Brief %s generated: risk=%s, events=%d, narrative=%s, provider=%s",
            brief_id[:8], overall_risk, events_included, llm_used, provider_used
        )
        return brief

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _compute_risk(self, top: list[RankedEvent]) -> str:
        if not top:
            return "UNKNOWN"
        high_count = sum(1 for e in top if e.customer_impact == "high" or e.banking_relevance == "high")
        if high_count >= 2 or any(e.cps230_relevance and e.customer_impact == "high" for e in top):
            return "RED"
        if high_count >= 1 or any(e.customer_impact == "medium" for e in top):
            return "AMBER"
        return "GREEN"

    def _to_brief_event(self, event: RankedEvent) -> BriefEvent:
        risk = "GREEN"
        if event.customer_impact == "high" or event.banking_relevance == "high":
            risk = "RED"
        elif event.customer_impact == "medium" or event.banking_relevance == "medium":
            risk = "AMBER"

        status = "Ongoing"
        title_lower = event.raw_title.lower()
        if any(w in title_lower for w in ["resolved", "restored", "closed", "cleared"]):
            status = "Resolved"
        elif any(w in title_lower for w in ["monitoring", "watch", "advisory"]):
            status = "Monitoring"

        location = {
            "AU": "Australia",
            "APAC": "Asia Pacific",
            "GLOBAL": "Global",
        }.get(event.geography, event.geography)

        summary = event.raw_summary or event.raw_title
        if len(summary) > 400:
            summary = summary[:397] + "..."

        op_impact = self._infer_op_impact(event)
        so_what   = self._infer_so_what(event)

        return BriefEvent(
            event_id=event.event_id,
            title=event.raw_title,
            location=location,
            event_type=event.event_type.replace("_", " ").title(),
            risk_rating=risk,
            summary=summary,
            operational_impact=op_impact,
            so_what=so_what,
            status=status,
            source_name=event.source_name,
            canonical_url=event.canonical_url,
            rank_score=event.rank_score,
        )

    def _infer_op_impact(self, event: RankedEvent) -> str:
        parts = []
        if event.dependency_risk:
            parts.append("third-party dependency implications")
        if event.cps230_relevance:
            parts.append("CPS 230 operational resilience relevance")
        if event.banking_relevance in ("medium", "high"):
            parts.append(f"{event.banking_relevance} banking sector impact")
        if event.customer_impact in ("medium", "high"):
            parts.append(f"{event.customer_impact} customer impact likelihood")
        return "; ".join(parts) if parts else "Monitor for escalation"

    def _infer_so_what(self, event: RankedEvent) -> str:
        if event.event_type == "regulatory":
            return "Review regulatory obligations and assess compliance posture"
        if event.event_type == "cyber":
            return "Assess exposure, review controls, monitor ACSC advisories"
        if event.event_type == "technology_outage":
            return "Assess dependency on affected platform; activate contingency if critical"
        if event.event_type == "payments_disruption":
            return "Assess payment channel availability; prepare customer communications"
        if event.event_type == "severe_weather":
            return "Review site and workforce continuity plans for affected regions"
        if event.event_type == "telecom_outage":
            return "Assess connectivity dependencies; activate backup channels if available"
        if event.event_type == "energy_disruption":
            return "Review UPS and backup power; assess data centre resilience"
        return "Monitor situation; assess operational exposure and escalate if conditions worsen"

    def _generate_narrative(
        self,
        top: list[RankedEvent],
        brief_events: list[BriefEvent],
        period_start: datetime,
        period_end: datetime,
        sources_available: int,
        sources_failed: int,
    ) -> tuple:
        """
        Generate LLM narrative sections. Returns 7-tuple:
        (snapshot, themes, forward_watch, cps230, bottom_line, llm_used, provider)
        All sections default to None (not fabricated placeholders) if LLM unavailable.
        """
        if not top:
            return None, None, None, None, None, False, None

        event_summaries = "\n".join([
            f"- [{e.risk_rating}] {e.title} ({e.event_type}, {e.location}): {e.summary}"
            for e in brief_events
        ])

        prompt = f"""Generate the following sections of an Operational Resilience Intelligence Brief.
Period: {period_start.strftime('%d %b %Y')} to {period_end.strftime('%d %b %Y')}
Sources available: {sources_available} ({sources_failed} failed)

TOP EVENTS THIS PERIOD:
{event_summaries}

Respond with a JSON object containing exactly these keys:
{{
  "executive_snapshot": "<2-3 sentence overall summary of the intelligence period>",
  "emerging_themes": ["<theme 1>", "<theme 2>", "<theme 3>"],
  "forward_watch": ["<upcoming risk or watch item 1>", "<upcoming risk or watch item 2>"],
  "cps230_implications": ["<implication 1>", "<implication 2>"],
  "bottom_line": "<one paragraph, what Captain TJR should know and do>"
}}

Only use information from the TOP EVENTS provided. Do not invent incidents."""

        raw, provider = self.llm.generate(prompt)

        if not raw:
            return None, None, None, None, None, False, None

        try:
            import re, json
            # Strip markdown code fences (```json ... ``` or ``` ... ```)
            raw_clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            raw_clean = re.sub(r"\s*```\s*$", "", raw_clean)
            # Extract JSON object — greedy match from first { to last }
            json_match = re.search(r"\{.*\}", raw_clean, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(raw_clean)

            return (
                data.get("executive_snapshot"),
                data.get("emerging_themes"),
                data.get("forward_watch"),
                data.get("cps230_implications"),
                data.get("bottom_line"),
                True,
                provider,
            )
        except Exception as exc:
            log.warning("Failed to parse LLM JSON response: %s\nRaw: %s", exc, raw[:200])
            return None, None, None, None, None, True, provider
