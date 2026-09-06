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

from intelligence.brief import morning_cycle
from intelligence.brief.comparison import compute_comparison
from intelligence.brief.domain_picture import compute_domain_picture
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

        # ── 0. Morning cycle readiness (informational only — never blocks or
        # waits here; the scheduler's own poll job decides WHEN to call
        # generate(), this just records what it found so the brief can be
        # honest about its own coverage). Never allowed to break generation.
        try:
            cycle_status = morning_cycle.get_status()
        except Exception as exc:
            log.warning("Morning cycle status check failed (non-fatal): %s", exc)
            cycle_status = None

        # ── 1. Collection ─────────────────────────────────────────────────────
        items, health_records = collect_all(sources=sources)
        sources_checked   = len(health_records)
        sources_available = sum(1 for h in health_records if h.status in ("ok", "degraded"))
        sources_failed    = sum(1 for h in health_records if h.status == "failed")
        sources_stale     = sum(1 for h in health_records if h.status in ("stale", "degraded"))
        missing_sources    = [h.source_name for h in health_records if h.status == "failed"]
        latest_included_at = max((i.collected_at for i in items), default=None)

        log.info("Collected %d items from %d sources", len(items), sources_checked)

        # ── 2. Classify ───────────────────────────────────────────────────────
        classified: list[ClassifiedEvent] = []
        dedup_hashes_seen: set[str] = set()
        dedup_urls_seen: set[str] = set()

        for item in items:
            event = classify(item)

            # Skip duplicates already in this collection run (by hash)
            if event.dedup_hash in dedup_hashes_seen:
                continue
            dedup_hashes_seen.add(event.dedup_hash)

            # Skip if same canonical URL already seen this run (cross-source dedup)
            if event.canonical_url and event.canonical_url in dedup_urls_seen:
                continue
            if event.canonical_url:
                dedup_urls_seen.add(event.canonical_url)

            # Skip if already persisted by hash (previous run, same source)
            if store.event_hash_exists(event.dedup_hash):
                continue

            # Cross-run canonical URL dedup — same article from different source in prior run
            if event.canonical_url and store.event_canonical_url_exists(event.canonical_url):
                continue

            # Fallback: no canonical URL — dedup by normalised title + publication date
            if not event.canonical_url and event.published_at:
                from intelligence.classification.deduplicator import _normalise
                date_str = event.published_at.strftime("%Y-%m-%d")
                if store.event_title_date_exists(_normalise(event.raw_title), date_str):
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

        # ── 7b. Generate per-event So What (LLM, may fall back to template) ───
        so_whats = self._generate_so_whats(top5)
        for be, sw in zip(brief_events, so_whats):
            if sw:
                be.so_what = sw

        # ── 8. Generate narrative (LLM, may fail) ─────────────────────────────
        (executive_snapshot, emerging_themes, forward_watch,
         cps230_implications, bottom_line, known_unknowns, llm_used, provider_used) = \
            self._generate_narrative(top5, brief_events, period_start, period_end,
                                     sources_available, sources_failed)

        # ── 8b. QA Validation Officer — non-blocking sanity check ─────────────
        # 2026-08-22: real LLM check for forced/mismatched framing (the bug
        # found live this session — general world news getting manufactured
        # "operational resilience"/"compliance" language). Logs only, never
        # withholds or alters the brief — this is a single-user platform with
        # auto-publish (see intelligence/persistence/intelligence_store.py:
        # save_brief()), not a review gate.
        if executive_snapshot or bottom_line:
            brief_text_for_checks = f"Executive snapshot: {executive_snapshot}\nBottom line: {bottom_line}"
            try:
                qa_note = self.llm.check_brief_quality(brief_text_for_checks)
                if qa_note:
                    log.info("[qa-validation] %s", qa_note)
            except Exception as exc:
                log.warning("[qa-validation] check errored: %s", exc)
            try:
                risk_note = self.llm.check_risk_rating(brief_text_for_checks, overall_risk)
                if risk_note:
                    log.info("[risk-challenge] %s", risk_note)
            except Exception as exc:
                log.warning("[risk-challenge] check errored: %s", exc)

        # ── 8c. Coverage / comparison / domain picture (Sections 6, 11-13) ─────
        # Deterministic post-processing — no re-reasoning, no invented
        # history (Section 26). Never allowed to break brief generation.
        import dataclasses
        top_events_dicts = [dataclasses.asdict(be) for be in brief_events]

        coverage: dict = {
            "expected": sources_checked,
            "completed": sources_available,
            "failed": sources_failed,
            "stale": sources_stale,
            "missing_sources": missing_sources[:10],
            "latest_included_at": latest_included_at.isoformat() if latest_included_at else None,
        }
        if cycle_status is not None:
            coverage.update(cycle_status.to_dict())
            coverage["degraded"] = bool(cycle_status.degraded or sources_failed > 0)
        else:
            coverage["degraded"] = sources_failed > 0

        try:
            prior_brief = store.load_latest_brief()
        except Exception as exc:
            log.warning("Could not fetch prior brief for comparison (non-fatal): %s", exc)
            prior_brief = None
        comparison = None
        try:
            prior_top_events = (prior_brief or {}).get("top_events")
            comparison = compute_comparison(top_events_dicts, prior_top_events)
        except Exception as exc:
            log.warning("Prior-brief comparison failed (non-fatal): %s", exc)

        domain_picture = None
        try:
            domain_picture = compute_domain_picture(top_events_dicts)
        except Exception as exc:
            log.warning("Domain picture computation failed (non-fatal): %s", exc)

        morning_cycle_id = cycle_status.cycle_id if cycle_status is not None else morning_cycle.cycle_id_for()

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
            morning_cycle_id=morning_cycle_id,
            coverage=coverage,
            comparison=comparison,
            domain_picture=domain_picture,
            known_unknowns=known_unknowns,
        )

        # ── 10. Persist brief and link events ────────────────────────────────
        saved_id = store.save_brief(brief)
        if saved_id and persisted_ids:
            store.link_events_to_brief(persisted_ids[:events_included], saved_id)

        log.info(
            "Brief %s generated: risk=%s, events=%d, narrative=%s, provider=%s, "
            "cycle=%s, coverage_degraded=%s",
            brief_id[:8], overall_risk, events_included, llm_used, provider_used,
            morning_cycle_id, coverage.get("degraded"),
        )
        return brief

    # ─── Private helpers ──────────────────────────────────────────────────────

    _RISK_ORDER = {"GREEN": 0, "AMBER": 1, "RED": 2}

    def _event_risk_rating(self, event: RankedEvent) -> str:
        if event.customer_impact == "high" or event.banking_relevance == "high":
            return "RED"
        if event.customer_impact == "medium" or event.banking_relevance == "medium":
            return "AMBER"
        return "GREEN"

    def _compute_risk(self, top: list[RankedEvent]) -> str:
        if not top:
            return "UNKNOWN"
        high_count = sum(1 for e in top if e.customer_impact == "high" or e.banking_relevance == "high")
        if high_count >= 2 or any(e.cps230_relevance and e.customer_impact == "high" for e in top):
            aggregate = "RED"
        elif high_count >= 1 or any(e.customer_impact == "medium" for e in top):
            aggregate = "AMBER"
        else:
            aggregate = "GREEN"

        # Floor at the worst individual event rating — the aggregate escalation
        # rules above require 2+ high-severity events to reach RED, which let a
        # single genuinely RED-rated event (_event_risk_rating) sit under an
        # AMBER/GREEN overall_risk. brief_qa_agent's risk_accuracy_score check
        # (and brief_coherence's overall_risk_justified) both correctly flag
        # that as a mismatch — a brief must never rate itself below its own
        # worst included event. Confirmed live: this was the single biggest
        # driver of "0 passed" every nightly QA run since 2026-06-20.
        worst_event = max((self._event_risk_rating(e) for e in top), key=self._RISK_ORDER.get)
        if self._RISK_ORDER[worst_event] > self._RISK_ORDER[aggregate]:
            return worst_event
        return aggregate

    def _to_brief_event(self, event: RankedEvent) -> BriefEvent:
        risk = self._event_risk_rating(event)

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
        """Fallback template — only used if LLM So What generation fails."""
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

    def _generate_so_whats(self, top: list[RankedEvent]) -> list[str]:
        """
        Generate one actionable So What sentence per top event using the LLM.
        Batches all events in a single call. Falls back to template per-event on failure.
        Returns list of strings aligned to input list (same length, same order).
        """
        if not top:
            return []

        lines = []
        for i, e in enumerate(top):
            cps = " CPS 230 relevant." if e.cps230_relevance else ""
            banking = f" Banking relevance: {e.banking_relevance}." if e.banking_relevance != "low" else ""
            summary_text = f" Summary: {e.raw_summary[:200]}" if e.raw_summary else ""
            lines.append(
                f"{i+1}. [{e.event_type.upper()}] {e.raw_title} "
                f"(Source: {e.source_name}, Geography: {e.geography})"
                f"{cps}{banking}{summary_text}"
            )

        prompt = (
            "You are the Operational Resilience Intelligence Officer for an Australian bank.\n\n"
            "For each of the following events, write exactly ONE sentence answering:\n"
            "\"What should a Head of Operational Resilience do or consider because of this event?\"\n\n"
            "Rules:\n"
            "- Be specific to the event content — do not use generic phrases\n"
            "- Focus on Australian banking and CPS 230 obligations where relevant\n"
            "- One sentence only per event\n"
            "- Return a JSON array of strings, one per event, in the same order\n\n"
            "EVENTS:\n" + "\n".join(lines) + "\n\n"
            "Return ONLY a JSON array like: [\"sentence 1\", \"sentence 2\", ...]"
        )

        try:
            raw, _ = self.llm.generate(prompt)
            if not raw:
                raise ValueError("empty LLM response")

            import re, json
            raw_clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            raw_clean = re.sub(r"\s*```\s*$", "", raw_clean)
            match = re.search(r"\[.*\]", raw_clean, re.DOTALL)
            if match:
                result = json.loads(match.group())
                if isinstance(result, list) and len(result) == len(top):
                    log.info("LLM So What generated for %d events", len(result))
                    return [str(s).strip() for s in result]
        except Exception as exc:
            log.warning("LLM So What generation failed (%s) — using templates", exc)

        # Fallback: template per event
        return [self._infer_so_what(e) for e in top]

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
        Generate LLM narrative sections. Returns 8-tuple:
        (snapshot, themes, forward_watch, cps230, bottom_line, known_unknowns,
        llm_used, provider). All sections default to None (not fabricated
        placeholders) if LLM unavailable.
        """
        if not top:
            return None, None, None, None, None, None, False, None

        event_summaries = "\n".join([
            f"- [{e.risk_rating}] {e.title} ({e.event_type}, {e.location}): {e.summary}"
            for e in brief_events
        ])

        # 2026-08-22: generalized from a forced "Operational Resilience
        # Intelligence Brief" framing to a plain educational daily-digest
        # framing — this collection still only carries OSINT/world events
        # (health/engineering/learning/opportunities are merged in separately
        # by intelligence/brief/daily_digest.py), but the narrative itself
        # should read as "what happened in the world today", not manufacture
        # a banking angle on every story. cps230_implications stays in the
        # schema (it's a persisted DB column) but is only populated when the
        # events actually warrant it.
        prompt = f"""Generate a daily world-news digest for Captain TJR, in plain educational language.
Period: {period_start.strftime('%d %b %Y')} to {period_end.strftime('%d %b %Y')}
Sources available: {sources_available} ({sources_failed} failed)

TOP EVENTS THIS PERIOD:
{event_summaries}

Respond with a JSON object containing exactly these keys:
{{
  "executive_snapshot": "<2-3 sentence overall summary of the period — must explicitly name or closely paraphrase at least one of the TOP EVENTS titles above, not a generic summary. Explain why it matters, not just what happened>",
  "emerging_themes": ["<theme 1>", "<theme 2>", "<theme 3>"],
  "forward_watch": ["<upcoming item to watch 1>", "<upcoming item to watch 2>"],
  "cps230_implications": ["<operational-resilience/regulatory implication, ONLY if these events actually touch Australian banking/CPS230 — empty list otherwise, do not force one>"],
  "bottom_line": "<one paragraph, what Captain TJR should know today>",
  "known_unknowns": ["<a genuine evidence gap or uncertainty about one of the TOP EVENTS above — e.g. unconfirmed reports, missing timestamps, conflicting sources. Empty list if there is nothing genuinely uncertain — do not invent a gap to fill this>"]
}}

Only use information from the TOP EVENTS provided. Do not invent incidents."""

        raw, provider = self.llm.generate(prompt)

        if not raw:
            return None, None, None, None, None, None, False, None

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
                data.get("known_unknowns"),
                True,
                provider,
            )
        except Exception as exc:
            log.warning("Failed to parse LLM JSON response: %s\nRaw: %s", exc, raw[:200])
            return None, None, None, None, None, None, True, provider
