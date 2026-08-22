"""
Persistence layer for the OR Intelligence Agent.
Thin wrapper over the existing Supabase PostgREST pattern used throughout
the platform (mirrors tools/supabase/client.py conventions).
"""

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional

from intelligence.config import SUPABASE_URL, SUPABASE_KEY
from intelligence.models import (
    ClassifiedEvent, RankedEvent, ResilienceBrief,
    SourceRecord, SourceHealth
)

log = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _post(table: str, payload: dict, on_conflict: Optional[str] = None) -> Optional[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase not configured — skipping persist for %s", table)
        return None

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url += f"?on_conflict={on_conflict}"
    headers = _headers()
    prefer = "return=representation,resolution=merge-duplicates"
    headers["Prefer"] = prefer

    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result[0] if isinstance(result, list) else result
    except urllib.error.HTTPError as exc:
        # 2026-08-09: str(exc) alone ("HTTP Error 400: Bad Request") gave no
        # way to diagnose why ~20 events/day were silently failing to
        # persist -- the actual reason (constraint violation, bad column
        # value, etc.) is in the response body, which this was discarding.
        detail = exc.read().decode("utf-8", errors="replace")
        log.error("Supabase insert failed (%s): HTTP %s: %s", table, exc.code, detail)
        return None
    except Exception as exc:
        log.error("Supabase insert failed (%s): %s", table, exc)
        return None


def patch_row(table: str, match: str, payload: dict) -> dict:
    """PATCH (update) rows matching a PostgREST filter (e.g. 'event_id=eq.<uuid>').

    Returns the updated row (representation) or {} on failure/misconfig. Used by
    the Phase A workflow repository (SupabaseRepository)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase not configured — skipping patch for %s", table)
        return {}

    url = f"{SUPABASE_URL}/rest/v1/{table}?{match}"
    headers = _headers()
    headers["Prefer"] = "return=representation"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result[0] if isinstance(result, list) and result else (result or {})
    except Exception as exc:
        log.error("Supabase patch failed (%s): %s", table, exc)
        return {}


def _publish_core_event(event_type: str, **kwargs) -> None:
    """SUOC Wave 3/MSN-0210K: thin-index mirror into the shared Event Bus
    (core_events). Best-effort, non-blocking — never raises, never affects
    intelligence_events/intelligence_briefs persistence, which remains the
    real source of truth for this domain exactly as before."""
    try:
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.platform.event_bus import publish_event
        publish_event(event_type, domain="operational-resilience-intelligence", source="intelligence_store", **kwargs)
    except Exception:
        pass


# Part 2 of the 2026-08-09 Telegram usefulness + outage-alerts design
# (.claude/skills/bot-reviews/fixes-2026-08-09/telegram-usefulness-and-outage-alerts-design.md
# §2.3): live 30-day query against intelligence_events showed rank_score
# never crosses a usable threshold for outage-classified events (max 52.2
# in the sample), so the existing INTERRUPT_NOW path structurally never
# fires for this event type -- real severe outages sat silently with no
# push. customer_impact='high' is the field that actually encodes severity
# (keyword-evidenced critical/severe/widespread language only, 5% of
# events); confidence>=0.65 is a minimum-corroboration floor chosen from
# the same data (11/15 genuine severe events over 30 days would have
# fired at this floor, ~1 push every 2.7 days -- a sustainable cadence).
_OUTAGE_EVENT_TYPES = frozenset({"technology_outage", "telecom_outage"})
_OUTAGE_CUSTOMER_IMPACT_FLOOR = "high"
_OUTAGE_CONFIDENCE_FLOOR = 0.65

# 2026-08-10 fix (XO product review of this feature's first week): the three
# gates above alone let one real misclassification through — a political/
# regulatory story ("Trump wants 'fair treatment' ... Labor's levy on tech
# giants") landed on event_type='technology_outage' (root cause: bare,
# generic keywords in classifier.py's technology_outage rule list — notably
# "platform" and company names like "microsoft" — match any story that
# mentions a tech platform or vendor, not just outage reports; classifier.py
# tightened this exact bare-keyword-collision pattern for four other
# categories on 2026-07-18, but technology_outage itself was never audited).
# Not fixed at the classifier level here: a live check found 152/510
# (30%) of ALL technology_outage-tagged events over the last 30 days rely
# solely on these generic/bare keywords with no genuine incident-language
# signal — evidence the defect is real and pervasive, but also that
# reworking the shared keyword list is a platform-wide classification change
# (it feeds the weekly OSINT roll-up and every other technology_outage
# consumer, not just this push path) that needs its own scoped review, not
# a same-night reactive patch bundled with an unrelated UI fix set.
# This guard is a narrower, additive mitigation scoped to the push-alert
# trigger only: require genuine incident-language in the title/summary
# before pushing. Verified against 90 days of push-eligible
# (event_type in outage types, customer_impact=high, confidence>=0.65)
# events: excludes exactly 2 of 40 — the misclassified political story
# above, and a Telstra opinion/commentary piece written well after that
# outage ("... is a result of prioritising neoliberal 'competition' ...")
# that is analysis ABOUT an outage, not a report OF one occurring — and
# every one of the other 38 genuine live-incident reports still passes.
_OUTAGE_LANGUAGE_KEYWORDS = (
    "outage", "incident", "degrad", "unavailable", "unable to access",
    "service disruption", "system failure", "service interruption",
    "api failure", "latency", "error rate", "elevated error",
    "restored", "resolved", "mitigat", "impacted",
)


def _has_outage_language(event: RankedEvent) -> bool:
    """True if the event's own title/summary contains genuine incident-
    report language, not just an event_type/customer_impact/confidence
    combination the upstream keyword classifier can mis-assign to a story
    that merely mentions a tech platform or vendor. See the dated comment
    above _OUTAGE_LANGUAGE_KEYWORDS for the live-data verification behind
    this list."""
    text = f"{event.raw_title or ''} {event.raw_summary or ''}".lower()
    return any(kw in text for kw in _OUTAGE_LANGUAGE_KEYWORDS)


# 2026-08-10 fix (per .claude/skills/bot-reviews/fixes-2026-08-09/
# outage-scale-detection-proposal.md, Recommendation 1): customer_impact is a
# pure dramatic-adjective keyword match in classifier.py ("critical",
# "significant", "major", "widespread" etc.), not a scale/breadth signal --
# it fires identically on standard vendor status-page incident-report
# boilerplate as it does on a genuine nationwide outage. Confirmed against a
# live 30-day sample: the exact push-eligible bucket (event_type +
# customer_impact=high + confidence>=0.65 + _has_outage_language, i.e. every
# other gate above already satisfied) was 62.5% (5 of 8) single-vendor
# status-page blips -- GitHub "~39% of REST requests failed... in a single
# region", Supabase one-region "stuck state," DigitalOcean "one AI model on
# one product," Notion "one company's own customers" -- sitting alongside
# genuinely nationwide events (3 independently-corroborated ABC News/
# Guardian Australia stories on Telstra's nationwide mobile/triple-zero
# outage). All 8 satisfied every existing gate equally -- none of them
# distinguish blast radius.
#
# source_category/source_name (already on the RankedEvent this function
# receives -- no new join, no new DB read) explain the split: independent
# media coverage (source_category='media') is left as-is, unrestricted --
# that's where the real should-trigger signal lives in the sample. Vendor
# self-reports (source_category in cloud_technology/critical_infrastructure)
# are gated behind a short "foundational infrastructure" allowlist --
# hyperscalers and national carriers whose own outages are inherently
# national/global in blast radius even self-reported. Every other vendor
# status page in the registry (Notion, DocuSign, Canva, Zoom, Adobe, Miro,
# Twilio, Okta, ServiceNow, Salesforce, Slack, Atlassian, DigitalOcean,
# Vercel, Anthropic, OpenAI, GitHub, Oracle Cloud, etc.) is capped at "one
# company's own customers" scale by construction and suppressed here
# regardless of customer_impact wording, matching the Captain's own framing
# ("one company's specific product had a blip"). GitHub deliberately left
# off this allowlist -- a disclosed judgment call in the proposal doc: the
# one GitHub incident in the sample was a single-region API degradation, not
# internet-breaking; narrow-by-default unless redirected.
#
# Matched on substring-in-source_name (not an exact-string list) because the
# registry carries multiple source rows per Tier-A vendor with different
# exact names (e.g. "AWS Service Health", "AWS Service Health Dashboard",
# "AWS Sydney (ap-southeast-2)"; "TPG Service Status", "TPG Telecom Service
# Status") -- an exact-match list would silently miss registry variants.
#
# Known, disclosed residual gap (found during this fix's own verification,
# not by the original proposal): this vendor-identity gate is coarse -- it
# can't distinguish a Tier-A vendor's genuinely broad self-report from a
# narrow one on the same vendor's status page. Live data shows this is a
# real, recurring pattern, not hypothetical: a Google Cloud VMware Engine
# (GCVE) incident -- a niche enterprise product, explicitly named as one of
# the 5 false positives in the proposal's own evidence table -- still passes
# this gate because "Google Cloud" the vendor is Tier-A; likewise a
# single-availability-zone AWS power-outage self-report (ME-SOUTH-1) and
# repeated single-region "Delhi/Chennai/Mumbai" Google Cloud latency
# self-reports found in a 90-day spot check. This gate still closes 4 of the
# 5 documented false positives cleanly (GitHub, Supabase, DigitalOcean,
# Notion) and leaves all genuine Telstra media coverage untouched; the
# residual Tier-A-vendor-narrow-incident case is the exact scenario
# Recommendation 3's per-candidate LLM blast-radius check (not implemented
# here, disclosed as a future fallback) would resolve. Flagged for Captain
# visibility rather than silently expanding this fix's scope to build that
# now.
_FOUNDATIONAL_INFRA_VENDORS = (
    "aws", "amazon web services",
    "azure",
    "google cloud",
    "cloudflare",
    "nbn",
    "telstra",
    "optus",
    "tpg",
)
_VENDOR_SELF_REPORT_CATEGORIES = frozenset({"cloud_technology", "critical_infrastructure"})


def _passes_vendor_tier_gate(event: RankedEvent) -> bool:
    """True if this event is either independent media coverage (unrestricted
    -- current bar unchanged) or a vendor self-report from a Tier-A
    foundational-infrastructure vendor. Vendor self-reports from every other
    source are capped at "one company's own customers" scale by construction
    and excluded here regardless of customer_impact wording. See the dated
    comment above _FOUNDATIONAL_INFRA_VENDORS for the live-data verification
    (and disclosed residual gap) behind this gate."""
    if event.source_category not in _VENDOR_SELF_REPORT_CATEGORIES:
        return True
    name = (event.source_name or "").lower()
    return any(vendor in name for vendor in _FOUNDATIONAL_INFRA_VENDORS)


# 2026-08-10 fix (Captain-approved implementation of Recommendation 3 in
# .claude/skills/bot-reviews/fixes-2026-08-09/outage-scale-detection-proposal.md,
# after outage-scale-gate-implemented.md's own verification confirmed the
# Tier-A vendor allowlist above has a real, recurring residual gap): the
# allowlist gates on vendor IDENTITY, not per-INCIDENT scope -- a Tier-A
# vendor's own narrow self-report (single availability zone, single region)
# still passes because the vendor itself is broad-impact-capable even when
# this specific incident isn't. Confirmed live: the Google Cloud VMware
# Engine (GCVE) "zonal outages ... across multiple regions" incident, a
# single-Availability-Zone AWS ME-SOUTH-1 power outage self-report, and
# repeated single-region "Delhi/Chennai/Mumbai" Google Cloud latency
# self-reports all still pass every gate above despite being narrow --
# reconfirmed recurring (not a one-off) in a 90-day spot check.
#
# This is the 5th and FINAL guard, fired only after event_type,
# customer_impact, confidence, _has_outage_language, and
# _passes_vendor_tier_gate have ALL already passed -- i.e. on the same tiny,
# rare-volume set of candidates the existing gates already narrowed down to
# (roughly 1 event every 2-3 days per the floor documented above
# _OUTAGE_EVENT_TYPES), never per-ingested-item. Mirrors
# intelligence/ingestion/selective_augmentation.py's existing pattern for
# routing ambiguous heuristic output to a single extra LLM call: check cost
# governance, fire one call via the shared core/llm/provider_chain.py
# primitives (same never-raise, try-gemini-then-mistral-then-ollama fallback
# core/platform/infra_narrative.py already uses), log the call either way,
# never raise.
#
# Fail-safe default on total LLM failure (cost-governance denial, or all 3
# providers down/unparseable): ALLOW THROUGH, not suppress. Deliberate
# asymmetry, not an oversight -- this is the LAST guard before a real
# Telegram push, sitting on top of a candidate that has already satisfied
# every heuristic check above (genuine incident-report language, high
# customer_impact, a confidence floor, and either independent media or a
# Tier-A vendor). A false negative here (silently swallowing a genuine
# nationwide outage because every LLM provider happened to be unreachable at
# that moment) is worse than a false positive (one extra push for an
# incident that was already a credible candidate by every other measure) --
# for a system whose whole purpose is not missing real widespread outages,
# erring toward over-alerting on total tool failure is the safer failure
# mode. On failure this simply falls back to the pre-this-fix behaviour
# (Tier-A-gated push), not a new way for a real outage to go unreported.
# 2026-08-10 fix (Downdetector Australia adapter — crowdsourced report-volume
# outage signal, see intelligence/ingestion/downdetector_adapter.py and
# .claude/skills/bot-reviews/fixes-2026-08-09/downdetector-adapter-implemented.md):
# Downdetector-sourced events deliberately BYPASS guard 5
# (_passes_vendor_tier_gate) and guard 6 (_passes_blast_radius_check) below.
# This is a considered, disclosed design choice, not an oversight -- both of
# those guards exist to *approximate* genuine blast radius from vendor
# self-report TEXT (vendor identity allowlist, then an LLM reading title/
# summary prose) precisely because vendor status pages carry no native scale
# signal of their own. The Downdetector adapter already gates on a direct,
# numeric, ground-truth scale signal BEFORE an item is even emitted --
# Downdetector's own top status tier AND a real report-count spike cleared
# against evidence-grounded thresholds (see that adapter's module docstring)
# -- so re-applying vendor-identity or single-company-scoped text heuristics
# on top would be redundant at best.
#
# It would be actively WRONG at worst, for two separate, confirmed reasons:
#   1. Guard 5's Tier-A allowlist (_FOUNDATIONAL_INFRA_VENDORS: AWS/Azure/
#      Google Cloud/Cloudflare/NBN/Telstra/Optus/TPG only) would incorrectly
#      suppress every genuine, Downdetector-CONFIRMED outage for every
#      company this mission exists to add coverage for that isn't already on
#      that hyperscaler/carrier list -- Vodafone, every smaller ISP (iiNet,
#      Dodo, Aussie Broadband, Superloop, Activ8me), all four major banks,
#      and mygov/Centrelink/myID. That would silently defeat the entire
#      point of adding this source.
#   2. Guard 6's LLM prompt explicitly defines "narrow" as "confined to one
#      vendor's own service, product, or customer base (even if that vendor
#      is itself a large hyperscaler or carrier)". A real, Downdetector-
#      confirmed, nationwide outage of e.g. one bank's own banking app --
#      unable-to-access-your-money for millions of Australians, exactly the
#      kind of event this platform's own CPS230/banking_relevance framing
#      treats as first-class -- is still, by the letter of that prompt,
#      "confined to one company's own customer base", so the LLM would very
#      plausibly answer "no" (narrow) and suppress a genuine, materially
#      significant event. That prompt was calibrated for vendor
#      self-report/media text, not for "is this company-wide outage,
#      independently corroborated by real report-volume, big enough to
#      matter" -- a different question this source's own two-layer gate
#      already answers more directly.
#
# Detected via a source_name prefix match (same mechanism guard 5 already
# uses for its own vendor-identity check, for internal consistency), not
# source_category, so this bypass has zero effect on any other source's
# gating -- it only ever matches the 19 sources this mission registers, all
# named "Downdetector AU -- <Company>" (see tools/intelligence/sources_live.csv).
_DOWNDETECTOR_SOURCE_PREFIX = "downdetector au"


def _is_downdetector_source(event: RankedEvent) -> bool:
    return (event.source_name or "").strip().lower().startswith(_DOWNDETECTOR_SOURCE_PREFIX)


_BLAST_RADIUS_TASK_TYPE = "outage-blast-radius-check"

_BLAST_RADIUS_SYSTEM_PROMPT = (
    "You assess a single reported technology/telecom incident for USS "
    "Starship Endeavour's outage-alert pipeline. Answer exactly one "
    "question: does this incident describe a blast radius broader than one "
    "company's own product or customers -- i.e. does it affect multiple "
    "companies, a whole region's or country's general infrastructure, or "
    "the general public, rather than being confined to one vendor's own "
    "service, product, or customer base (even if that vendor is itself a "
    "large hyperscaler or carrier)? "
    "Only use the title, summary, and geography given below -- never "
    "invent, infer, or assume scope information that is not stated in the "
    "text. Do not reason from what you know about the company in general; "
    "reason only from what this specific text says happened. If the text "
    "describes one product, one availability zone, one region, or 'a "
    "subset of customers', that is narrow -- answer no. If the text "
    "describes national infrastructure, emergency services, multiple "
    "unrelated organisations, or explicitly nationwide/general-public "
    "impact, that is broad -- answer yes. "
    "Respond in exactly this format and nothing else:\n"
    "ANSWER: yes|no\n"
    "REASON: <one brief sentence, grounded only in the text given>"
)


def _blast_radius_llm_prompt(event: RankedEvent) -> str:
    return (
        f"Title: {event.raw_title or '(none provided)'}\n"
        f"Summary: {event.raw_summary or '(none provided)'}\n"
        f"Geography: {event.geography or '(not stated)'}"
    )


def _parse_blast_radius_answer(raw: Optional[str]) -> Optional[bool]:
    """Strict parse of the required 'ANSWER: yes|no' line. Returns None
    (treated as a provider failure by the caller, same as a transport error)
    if the model didn't follow the format."""
    if not raw:
        return None
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("ANSWER:"):
            value = line.split(":", 1)[1].strip().lower()
            if value.startswith("yes"):
                return True
            if value.startswith("no"):
                return False
    return None


def _call_blast_radius_llm(
    event: RankedEvent,
) -> tuple[Optional[bool], Optional[str], Optional[str]]:
    """Try the shared provider chain in order -- same fail-through pattern as
    core/platform/infra_narrative.py's _generate(). Returns
    (is_broad_or_None, provider_name_or_None, raw_response_or_None). Never
    raises; a total failure returns (None, None, None)."""
    from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

    prompt = _blast_radius_llm_prompt(event)
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    mistral_key = os.getenv("MISTRAL_API_KEY", "")
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_OUTAGE_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")

    providers = [
        ("gemini-3.5-flash-lite", lambda p: call_gemini(
            _BLAST_RADIUS_SYSTEM_PROMPT, p, api_key=gemini_key, max_output_tokens=200)),
        ("mistral-small", lambda p: call_mistral(
            _BLAST_RADIUS_SYSTEM_PROMPT, p, api_key=mistral_key, max_tokens=200)),
        (ollama_model, lambda p: call_ollama(
            _BLAST_RADIUS_SYSTEM_PROMPT, p, base_url=ollama_base, model=ollama_model, num_predict=150)),
    ]
    for name, fn in providers:
        try:
            raw = fn(prompt)
            answer = _parse_blast_radius_answer(raw)
            if answer is not None:
                return answer, name, raw
            log.warning(
                "[outage-alert] blast-radius LLM (%s) returned unparseable output: %r",
                name, raw,
            )
        except Exception as exc:
            log.warning("[outage-alert] blast-radius LLM provider %s failed: %s", name, exc)
    return None, None, None


def _passes_blast_radius_check(event: RankedEvent, event_id: Optional[str]) -> bool:
    """5th and final push-alert guard. See the dated comment above
    _BLAST_RADIUS_TASK_TYPE for full rationale, including why total LLM
    failure fails OPEN (allows the push through) rather than suppressing.

    Only called after event_type/customer_impact/confidence/
    _has_outage_language/_passes_vendor_tier_gate have all already passed --
    genuinely rare volume, not a per-ingested-item cost. Governed the same
    way selective_augmentation.py governs its own single extra LLM call:
    intelligence.governance.llm_cost_governance.LLMCostGovernance gates the
    call (can_call_llm) and logs it (log_call) under a dedicated task_type,
    so spend/volume for this specific guard is trackable like every other
    governed LLM call site in this codebase."""
    import time as _time

    cost_governor = None
    try:
        from intelligence.governance.llm_cost_governance import LLMCostGovernance
        cost_governor = LLMCostGovernance()
    except Exception as exc:
        log.warning("[outage-alert] cost governor unavailable, proceeding ungoverned: %s", exc)

    if cost_governor is not None:
        check = cost_governor.can_call_llm(_BLAST_RADIUS_TASK_TYPE)
        if not check.allowed:
            log.info(
                "[outage-alert] blast-radius LLM check skipped (cost governance: "
                "%s) -- failing open (allow through) for event %s",
                check.reason, event_id,
            )
            return True

    start = _time.monotonic()
    is_broad, provider, raw = _call_blast_radius_llm(event)
    latency_ms = int((_time.monotonic() - start) * 1000)

    if cost_governor is not None:
        cost_governor.log_call(
            task_type=_BLAST_RADIUS_TASK_TYPE,
            provider=provider or "unknown",
            latency_ms=latency_ms,
            success=is_broad is not None,
            failure_reason=None if is_broad is not None else "all_providers_failed_or_unparseable",
            event_id=event_id,
        )

    if is_broad is None:
        log.warning(
            "[outage-alert] blast-radius LLM check unavailable (all providers "
            "failed or returned unparseable output) -- failing open (allow "
            "through) for event %s",
            event_id,
        )
        return True

    if not is_broad:
        log.info(
            "[outage-alert] suppressed -- blast-radius LLM check (%s) answered "
            "'no' (narrow scope) for event %s: %s",
            provider, event_id, raw,
        )
    return is_broad


def _maybe_push_outage_alert(event: RankedEvent, event_id: Optional[str]) -> None:
    """Push a Telegram alert for a newly-saved event that crosses the
    outage-severity threshold above.

    Domain-owned check living in save_event() (the single choke point every
    ranked event passes through, regardless of which scheduler job found
    it) rather than in core/platform/attention_engine.py -- the Attention
    Engine's own docstring states it is "a thin, pure routing table, not a
    rule engine that guesses at domain semantics"; adding outage-specific
    customer_impact logic there would violate that stated boundary and is
    a platform-wide-shared-module change requiring its own separate
    sign-off. Reuses the platform's one canonical
    core.platform.notification_service.notify() sender -- no new sender is
    introduced, per this platform's documented history of notification-
    sender duplication.

    Best-effort and non-blocking: any failure here (import, network,
    malformed data) is caught and logged, never raised -- it must not
    affect the caller's own event-persistence success/failure, matching
    every other post-persist side effect in this module (see
    _publish_core_event above).
    """
    try:
        if event.event_type not in _OUTAGE_EVENT_TYPES:
            return
        if event.customer_impact != _OUTAGE_CUSTOMER_IMPACT_FLOOR:
            return
        if event.confidence is None or float(event.confidence) < _OUTAGE_CONFIDENCE_FLOOR:
            return
        if not _has_outage_language(event):
            log.info(
                "[outage-alert] suppressed — %s/%s crossed the severity "
                "threshold but title/summary has no genuine incident "
                "language (event %s)",
                event.event_type, event.customer_impact, event_id,
            )
            return
        if _is_downdetector_source(event):
            # Guards 5/6 deliberately skipped here — see the dated comment
            # above _DOWNDETECTOR_SOURCE_PREFIX for the full, disclosed
            # reasoning (Downdetector's own two-layer report-volume gate
            # already is this source's scale signal).
            log.info(
                "[outage-alert] Downdetector-sourced event %s passed its own "
                "adapter-level two-layer gate — skipping vendor-tier and "
                "blast-radius guards (not applicable to this source shape)",
                event_id,
            )
        else:
            if not _passes_vendor_tier_gate(event):
                log.info(
                    "[outage-alert] suppressed — %s/%s from vendor self-report "
                    "%s (%s) is not on the foundational-infrastructure "
                    "allowlist (event %s)",
                    event.event_type, event.customer_impact, event.source_name,
                    event.source_category, event_id,
                )
                return
            if not _passes_blast_radius_check(event, event_id):
                return

        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.platform.notification_service import notify, Severity, Transport

        ref = event.canonical_url or (f"event_id={event_id}" if event_id else "no reference available")
        body = (
            f"Triggered: customer_impact={event.customer_impact}, "
            f"confidence={float(event.confidence):.2f}\n"
            f"Ref: {ref}"
        )
        result = notify(
            body,
            title=f"Outage — {event.event_type.replace('_', ' ')}: {event.raw_title}",
            severity=Severity.ALERT,
            template="alert",
            transport=Transport.TELEGRAM,
        )
        _log_outage_alert_fired(event, event_id, result)
    except Exception as exc:
        log.warning("[outage-alert] push check failed for event %s: %s", event_id, exc)


def _log_outage_alert_fired(event: RankedEvent, event_id: Optional[str], result) -> None:
    """Durable record of this push firing (2026-08-10 fix, XO product review
    of this feature's first night, finding #5): notification_service.notify()'s
    only bookkeeping is an in-process `_CALL_LOG` list (core/platform/
    notification_service.py) that doesn't survive a process restart and isn't
    queryable -- there was no way to answer "how many outage alerts fired this
    week, and did the sends actually succeed" without re-running this exact
    intelligence_events filter by hand.

    Reuses the existing generic audit_events table (migration 0054,
    core/platform/audit_service.py) rather than adding a new table --
    audit_service.py's own docstring names 'notification activity' as
    exactly the kind of event this table exists for, and it's already the
    established pattern for this exact call (record_audit_event) at three
    other call sites in this codebase (intelligence/governance/
    workflow_gate.py's log_mutation, core/coordination/
    telegram_build_executor.py, platform-runtime/lib/comms/pipeline.py).

    Best-effort and non-blocking, matching this module's own contract (see
    _maybe_push_outage_alert's docstring) -- a failure here must never affect
    the alert that already fired or the caller's own persistence result."""
    try:
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from core.platform.audit_service import record_audit_event

        record_audit_event(
            category="notification",
            actor="outage-alert-service",
            action="outage_alert_push",
            outcome="sent" if result.ok else "failed",
            details={
                "event_id": event_id,
                "event_title": event.raw_title,
                "event_type": event.event_type,
                "customer_impact": event.customer_impact,
                "confidence": float(event.confidence) if event.confidence is not None else None,
                "transport": result.transport.value,
                "error": result.error,
            },
        )
    except Exception as exc:
        log.warning(
            "[outage-alert] audit log write failed (non-blocking) for event %s: %s",
            event_id, exc,
        )


def _get(path: str) -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.error("Supabase query failed (%s): %s", path, exc)
        return []


# ─── Source Registry ──────────────────────────────────────────────────────────

def load_source_registry() -> list[SourceRecord]:
    rows = _get("intelligence_source_registry?active=eq.true&order=priority_rank.asc")
    sources = []
    for r in rows:
        sources.append(SourceRecord(
            source_id=r["source_id"],
            source_name=r["source_name"],
            category=r["category"],
            priority_rank=r["priority_rank"],
            url=r["url"],
            source_type=r["source_type"],
            jurisdiction=r["jurisdiction"],
            confidence_weight=float(r.get("confidence_weight", 0.8)),
            active=r.get("active", True),
            rss_url=r.get("rss_url"),
            api_endpoint=r.get("api_endpoint"),
            notes=r.get("notes"),
            content_expectation=r.get("content_expectation") or "continuous",
        ))
    return sources


def load_source_registry_all() -> list[dict]:
    """Return raw dicts for API responses."""
    return _get("intelligence_source_registry?order=priority_rank.asc,category.asc")


def get_source_reliability_scores() -> list[dict]:
    """
    Fetch SRS (Source Reliability Scores) for all active sources.
    Returns: [{"source_id": "...", "reliability_score": 0.75, ...}]
    Used by ranker.py to weight events by source reliability.
    """
    return _get("intelligence_source_registry?select=source_id,source_name,reliability_score,reliability_tier&active=eq.true")


# ─── Source Health ────────────────────────────────────────────────────────────

def save_source_health(health: SourceHealth) -> None:
    _post("intelligence_source_health", {
        "source_id": health.source_id,
        "checked_at": health.checked_at.isoformat(),
        "status": health.status,
        "items_retrieved": health.items_retrieved,
        "latency_ms": health.latency_ms,
        "error_message": health.error_message,
        "http_status": health.http_status,
        "content_valid": health.content_valid,
        "content_validity_reason": health.content_validity_reason,
    })
    if health.status == "failed":
        _publish_core_event(
            "intelligence.source.failed",
            linked_entities=[health.source_id],
            recommended_action=health.error_message,
        )


def load_latest_source_health() -> list[dict]:
    """Return most recent health row per source for dashboard display."""
    rows = _get(
        "intelligence_source_health"
        "?order=checked_at.desc&limit=500"
    )
    seen: dict[str, dict] = {}
    for row in rows:
        sid = row["source_id"]
        if sid not in seen:
            seen[sid] = row
    return list(seen.values())


# ─── Events ───────────────────────────────────────────────────────────────────

def event_hash_exists(dedup_hash: str) -> bool:
    rows = _get(f"intelligence_events?dedup_hash=eq.{dedup_hash}&limit=1")
    return len(rows) > 0


def event_canonical_url_exists(canonical_url: str) -> bool:
    """Check if any persisted event already has this canonical URL (cross-run dedup)."""
    import urllib.parse
    encoded = urllib.parse.quote(canonical_url, safe="")
    rows = _get(f"intelligence_events?canonical_url=eq.{encoded}&limit=1")
    return len(rows) > 0


def event_title_date_exists(normalised_title: str, date_str: str) -> bool:
    """Fallback cross-run dedup when canonical_url is null — match on title+date."""
    import urllib.parse
    enc_title = urllib.parse.quote(normalised_title, safe="")
    rows = _get(
        f"intelligence_events"
        f"?raw_title=ilike.{enc_title}"
        f"&published_at=gte.{date_str}T00:00:00"
        f"&published_at=lt.{date_str}T23:59:59"
        f"&limit=1"
    )
    return len(rows) > 0


_PHASE_A_FIELDS = (
    "source_tier", "signal_status", "score_breakdown", "relevance_score",
    "risk_rating", "canonical_signal_id", "cluster_similarity",
    "analysis_summary", "services_affected", "customers_affected",
    "confidence_level", "verified_against", "signal_owner",
)


def save_event(event: RankedEvent, ori: Optional[dict] = None,
               phase_a: Optional[dict] = None) -> Optional[str]:
    """Persist a ranked event. Returns event_id or None on failure.

    `ori` optionally supplies the WP4 enrichment columns for digest-sourced
    events (source_document_id, source_ref, brief_date, organisation,
    regulatory_topic, resilience_themes, watch_item_status, executive_relevance).
    `phase_a` optionally supplies the Phase A workflow columns (migration 0077:
    source_tier, signal_status, score_breakdown, risk_rating, canonical_signal_id,
    cluster_similarity, ...). Existing callers pass neither and behaviour is
    unchanged.
    """
    row = {
        "source_id": event.source_id,
        "raw_title": event.raw_title,
        "raw_summary": event.raw_summary,
        "canonical_url": event.canonical_url,
        "published_at": event.published_at.isoformat() if event.published_at else None,
        "collected_at": event.collected_at.isoformat(),
        "event_type": event.event_type,
        "geography": event.geography,
        "sector": event.sector,
        "operational_relevance": float(event.operational_relevance),
        "customer_impact": event.customer_impact,
        "banking_relevance": event.banking_relevance,
        "cps230_relevance": event.cps230_relevance,
        "dependency_risk": event.dependency_risk,
        "confidence": float(event.confidence),
        "rank_score": float(event.rank_score),
        "dedup_hash": event.dedup_hash,
        "suppressed": event.suppressed,
        "suppression_reason": event.suppression_reason,
        "affected_cves": event.affected_cves or None,
    }
    if ori:
        bd = ori.get("brief_date")
        row.update({
            "source_document_id":  ori.get("source_document_id"),
            "source_ref":          ori.get("source_ref"),
            "brief_date":          bd.isoformat() if hasattr(bd, "isoformat") else bd,
            "organisation":        ori.get("organisation"),
            "regulatory_topic":    ori.get("regulatory_topic"),
            "resilience_themes":   ori.get("resilience_themes"),
            "watch_item_status":   ori.get("watch_item_status"),
            "executive_relevance": ori.get("executive_relevance"),
        })
    if phase_a:
        row.update({k: phase_a[k] for k in _PHASE_A_FIELDS if k in phase_a})
    result = _post("intelligence_events", row, on_conflict="dedup_hash")
    if result:
        event_id = result.get("event_id")
        _publish_core_event(
            "intelligence.signal.ranked",
            importance=round(row["rank_score"]),
            confidence=round(row["confidence"] * 100),
            relevance=round(row["operational_relevance"] * 100),
            linked_entities=[event_id] if event_id else [],
            # USS-TJR-MSN-0339 WP2: without this, a dispatched INTERRUPT_NOW
            # push had no readable content — the Attention Engine's own
            # `reason` field is a scoring formula ("importance=X >= Y AND
            # confidence=Z >= W"), not what actually happened. This is the
            # same real title WP1 already validated as genuine content, not
            # new judgment about the signal's meaning.
            recommended_action=row["raw_title"],
        )
        _maybe_push_outage_alert(event, event_id)
        return event_id
    return None


# ─── ORI Source Documents (WP3/WP5 — preserve raw briefs) ──────────────────────

def document_version_exists(file_path: str, content_sha: str) -> bool:
    """Dedup Gate 1: has this exact file version already been imported?"""
    if not content_sha:
        return False
    rows = _get(
        f"ori_source_documents?file_path=eq.{file_path}"
        f"&content_sha=eq.{content_sha}&limit=1"
    )
    return len(rows) > 0


def save_source_document(doc: dict) -> Optional[str]:
    """Persist a raw brief document. Returns document_id or None on failure.

    Expects keys: source_id, file_name, file_path, blob_url, brief_date,
    content_sha, format_version, region, classification, raw_front_matter,
    raw_markdown, parse_warnings.
    """
    bd = doc.get("brief_date")
    row = dict(doc)
    if hasattr(bd, "isoformat"):
        row["brief_date"] = bd.isoformat()
    result = _post("ori_source_documents", row, on_conflict="file_path,content_sha")
    if result:
        return result.get("document_id")
    return None


def link_events_to_brief(event_ids: list[str], brief_id: str) -> None:
    """Update brief_id on included events. Uses individual PATCH calls."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    for eid in event_ids:
        url = f"{SUPABASE_URL}/rest/v1/intelligence_events?event_id=eq.{eid}"
        headers = {**_headers(), "Prefer": "return=minimal"}
        body = json.dumps({"brief_id": brief_id}).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as exc:
            log.warning("Could not link event %s to brief %s: %s", eid, brief_id, exc)


def load_recent_events(days: int = 14, limit: int = 200) -> list[dict]:
    """2026-08-13: ranking used to be pure rank_score.desc within the window,
    so a 6-day-old 0.98 always beat a 1-hour-old 0.90 — the window bounded
    how far back staleness could reach, but did nothing to weight recency
    inside it. Over-fetches the window (up to 3x limit) then re-sorts by a
    score decayed with a 3-day half-life, so genuinely fresh events can
    outrank older-but-higher-scored ones without discarding real severity —
    a 0.98 from yesterday still beats a 0.50 from an hour ago."""
    from datetime import timezone, timedelta
    from math import exp

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    fetch_limit = min(limit * 3, 600)
    rows = _get(
        f"intelligence_events"
        f"?collected_at=gte.{since}"
        f"&suppressed=eq.false"
        f"&signal_status=neq.DUPLICATE"
        f"&order=rank_score.desc"
        f"&limit={fetch_limit}"
    )
    if not rows:
        return rows

    half_life_days = 3.0
    now = datetime.now(timezone.utc)

    def _effective_score(row: dict) -> float:
        raw = row.get("rank_score") or 0.0
        collected = row.get("collected_at")
        if not collected:
            return raw
        try:
            ts = datetime.fromisoformat(collected.replace("Z", "+00:00"))
        except ValueError:
            return raw
        age_days = max(0.0, (now - ts).total_seconds() / 86_400)
        return raw * exp(-age_days / half_life_days * 0.6931471805599453)  # ln(2)

    rows.sort(key=_effective_score, reverse=True)
    return rows[:limit]


# ─── Briefs ───────────────────────────────────────────────────────────────────

def save_brief(brief: ResilienceBrief) -> Optional[str]:
    """Persist a ResilienceBrief. Returns brief_id or None on failure."""
    import dataclasses

    def _serialise(obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    top_events_json = [
        {
            "event_id": e.event_id,
            "title": e.title,
            "location": e.location,
            "event_type": e.event_type,
            "risk_rating": e.risk_rating,
            "summary": e.summary,
            "operational_impact": e.operational_impact,
            "so_what": e.so_what,
            "status": e.status,
            "source_name": e.source_name,
            "canonical_url": e.canonical_url,
            "rank_score": e.rank_score,
        }
        for e in brief.top_events
    ]

    row = {
        "brief_id": brief.brief_id,
        "generated_at": brief.generated_at.isoformat(),
        "period_start": brief.period_start.strftime("%Y-%m-%d"),
        "period_end": brief.period_end.strftime("%Y-%m-%d"),
        "sources_checked": brief.sources_checked,
        "sources_available": brief.sources_available,
        "sources_failed": brief.sources_failed,
        "sources_stale": brief.sources_stale,
        "events_evaluated": brief.events_evaluated,
        "events_included": brief.events_included,
        "events_suppressed": brief.events_suppressed,
        "executive_snapshot": brief.executive_snapshot,
        "emerging_themes": brief.emerging_themes,
        "forward_watch": brief.forward_watch,
        "cps230_implications": brief.cps230_implications,
        "bottom_line": brief.bottom_line,
        "top_events": top_events_json,
        "overall_risk": brief.overall_risk,
        "llm_used": brief.llm_used,
        "provider_used": brief.provider_used,
        "confidence": float(brief.confidence) if brief.confidence else None,
        "narrative_available": brief.narrative_available,
        "trigger_type": brief.trigger_type,
        # 2026-08-22: this is a single-user platform — the IN_REVIEW /
        # QA_PASSED / PUBLISHED approval chain (intelligence/workflow/
        # service.py) was built for a multi-reviewer newsroom and had no
        # reachable "publish" action anywhere in the portal for this daily
        # path, so briefs piled up IN_REVIEW forever (26/28 rows, confirmed
        # live 2026-08-22). Auto-publish at generation time instead. The
        # workflow module itself is left in place, just unused by this path.
        "approval_status": "PUBLISHED",
        "published_at": brief.generated_at.isoformat(),
    }
    result = _post("intelligence_briefs", row)
    if result:
        brief_id = result.get("brief_id")
        _publish_core_event(
            "intelligence.brief.generated",
            confidence=round(brief.confidence * 100) if brief.confidence else None,
            linked_documents=[brief_id] if brief_id else [],
            # MSN-0328 Wave 3: Telegram's /brief reads this brief's rich
            # content (bottom_line/overall_risk/themes) directly from
            # intelligence_briefs today. Attaching it here means the
            # canonical pipeline's event carries the same substance,
            # not just "a brief exists" -- required for Telegram to
            # converge without losing what it currently shows.
            metrics={
                "overall_risk": brief.overall_risk,
                "bottom_line": brief.bottom_line,
                "emerging_themes": brief.emerging_themes,
                "forward_watch": brief.forward_watch,
                "brief_id": brief_id,
            },
        )
        return brief_id
    return None


def load_latest_brief() -> Optional[dict]:
    rows = _get("intelligence_briefs?order=generated_at.desc&limit=1")
    return rows[0] if rows else None


def load_brief_archive(limit: int = 20, offset: int = 0) -> list[dict]:
    return _get(
        f"intelligence_briefs"
        f"?order=generated_at.desc"
        f"&limit={limit}"
        f"&offset={offset}"
    )


# ─── Downdetector baseline history / learned thresholds (migration 0121) ──────
# See intelligence/ingestion/downdetector_adapter.py (writes observations on
# every real fetch) and intelligence/ingestion/downdetector_thresholds.py
# (reads history, writes the recomputed per-source threshold nightly).

def save_downdetector_observation(
    source_name: str, sector: str, status: str, report_count: Optional[int],
) -> None:
    """Log one real Downdetector fetch's parsed (status, report_count) —
    called from DowndetectorAdapter.collect() on EVERY real fetch, not just
    ones that pass the two-layer push-alert gate. This is the accumulation
    ledger downdetector_thresholds.py::recompute_all() reasons over.
    Best-effort: _post() already logs and returns None on any failure
    rather than raising, so a Supabase hiccup here can never break the
    calling collect()."""
    _post("downdetector_baseline_history", {
        "source_name": source_name,
        "sector": sector,
        "status": status,
        "report_count": report_count,
    })


def load_downdetector_history(source_name: str, since_iso: str) -> list[dict]:
    """Real observation history for one source, oldest-first, since
    `since_iso` (an ISO-8601 timestamp). Used by recompute_all() to build
    the quiet-baseline distribution + known spike events the LLM reasons
    over. Returns [] (not an exception) on any read failure — the caller
    treats an empty/short history as insufficient, which is the correct,
    safe behaviour (falls back to the bootstrap default) either way."""
    import urllib.parse
    encoded_name = urllib.parse.quote(source_name, safe="")
    encoded_since = urllib.parse.quote(since_iso, safe="")
    return _get(
        f"downdetector_baseline_history"
        f"?source_name=eq.{encoded_name}"
        f"&observed_at=gte.{encoded_since}"
        f"&order=observed_at.asc"
        f"&limit=5000"
    )


def save_downdetector_threshold(
    source_name: str,
    sector: str,
    threshold_value: int,
    threshold_source: str,
    reasoning: Optional[str],
    history_days_used: int,
    llm_provider: Optional[str] = None,
) -> None:
    """Upsert the current threshold in force for one source. threshold_source
    always records HOW this value was reached (bootstrap vs. LLM-learned vs.
    a bootstrap fallback after an LLM failure/sanity-guard rejection) — see
    migration 0121's table comment. Called once per source per nightly
    recompute run."""
    from datetime import datetime, timezone
    _post(
        "downdetector_learned_thresholds",
        {
            "source_name": source_name,
            "sector": sector,
            "threshold_value": threshold_value,
            "threshold_source": threshold_source,
            "reasoning": reasoning,
            "history_days_used": history_days_used,
            "llm_provider": llm_provider,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="source_name",
    )


def load_all_downdetector_thresholds() -> dict[str, dict]:
    """Bulk read of every source's current learned/bootstrap threshold, keyed
    by source_name — used by downdetector_adapter.py's short-TTL in-process
    cache so a per-fetch gate check never needs its own live Supabase round
    trip (relevant now that the 6 tiered-cadence priority sources can be
    checked up to ~12x/day, see scheduler.py's _priority_tiered_collection_job).
    Returns {} (not an exception) on any read failure — callers fall back to
    the sector bootstrap default, which is the safe behaviour."""
    rows = _get("downdetector_learned_thresholds?select=*")
    return {row["source_name"]: row for row in rows}
