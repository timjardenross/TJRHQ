"""
Downdetector Australia — LLM-learned per-source report-count threshold.

Captain's direction 2026-08-10, replacing downdetector_adapter.py's flat
`_REPORT_COUNT_FLOOR = 150` constant: "it needs to be learned on the LLM
... as it's hard to set a floor per provider" — see
.claude/skills/bot-reviews/fixes-2026-08-09/cadence-tiering-and-learned-threshold.md
for the full design writeup and
.claude/skills/bot-reviews/fixes-2026-08-09/chief-engineer-intelligence-pipeline-review.md
Finding 4 for why a single global constant was flagged as a real risk
(banking/government quiet-day baselines are 5-10x lower in absolute terms
than telecom's, so a telecom-derived floor may be too high to ever fire for
a genuine, proportionally severe bank/government outage).

Pipeline (see intelligence/scheduler.py::_downdetector_threshold_recompute_job,
nightly):
  1. Pull real observation history for a source from downdetector_baseline_history
     (every real Downdetector fetch logs there — see
     DowndetectorAdapter.collect()/_log_observation() — regardless of
     whether the push-alert gate passed).
  2. Cold-start / bootstrap: fewer than _MIN_HISTORY_DAYS distinct days of
     real observations -> use the sector bootstrap default, explicitly
     logged and persisted as such (threshold_source =
     'bootstrap_default_insufficient_history'). Nothing real to learn from
     yet.
  3. Otherwise: summarise the real history (quiet-day report-count
     distribution + any known 'problems'-tier spike events) into structured
     data, ask the shared LLM provider chain (core/llm/provider_chain.py,
     same never-raise try-gemini-then-mistral-then-ollama fallback pattern
     intelligence/persistence/intelligence_store.py::_call_blast_radius_llm()
     already uses) to recommend a threshold + brief reasoning.
  4. Sanity-guard the recommendation (never trust an LLM number blind for a
     gate that decides whether a real push alert fires): reject <= 0,
     reject <= the highest real quiet-day count ever seen (would misfire on
     ordinary days), reject an absurdly high number relative to real
     historical evidence (would make the gate impossible to trigger). A
     rejected recommendation falls back to the bootstrap default, logged
     with why — never silently.
  5. Persist the result (bootstrap or learned, either way explicit about
     which) to downdetector_learned_thresholds — downdetector_adapter.py's
     get_report_count_floor() reads this table (short-TTL cached) instead
     of the old flat constant.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ─── Bootstrap defaults (cold-start, per sector) ───────────────────────────
# Judgment call, disclosed in the mission report: telecom keeps the one
# evidence-grounded number this platform actually has (Telstra's real
# 2026-07-07/08 outage — see downdetector_adapter.py's module docstring:
# 230-354 peak reports during the real event vs. a 1-42 quiet baseline).
# banking/government get a LOWER interim default than telecom's, not a copy
# of it — Chief Engineer's review (Finding 4) found live quiet-day
# baselines for these sectors are 5-10x lower in absolute terms (NAB/ANZ/
# Westpac ~3, Centrelink/myID ~1-2, vs. Telstra ~34), so a genuine bank/
# government outage producing the SAME *relative* spike Telstra's did
# (6-10x baseline) would plausibly peak around 20-70 reports — nowhere near
# 150. These interim defaults are not themselves evidence-grounded the way
# 150 is; they exist purely so day-one behaviour for these sectors isn't
# strictly worse than the old flat constant, until real accumulated history
# lets the LLM learn a proper per-source number (see _MIN_HISTORY_DAYS).
_BOOTSTRAP_DEFAULTS: dict[str, int] = {
    "telecom": 150,
    "banking": 30,
    "government": 20,
    # 2026-08-10 (coverage expansion round 2): energy retailers (Origin,
    # AGL, EnergyAustralia). Live quiet-baseline check at registration time
    # (all 3, single snapshot): 2 reports each — same low order of magnitude
    # as government's observed ~1-2, well below banking's ~3. Same
    # proportional-spike reasoning as banking/government (a genuine outage
    # producing Telstra's real ~6-10x baseline ratio would plausibly land
    # 12-20 on a baseline of 2) — set to match government's interim default
    # rather than inventing a fifth number from a single snapshot per
    # company. Same caveat as banking/government: not itself
    # evidence-grounded the way telecom's 150 is; exists so day-one
    # behaviour isn't worse than doing nothing, until real accumulated
    # history (downdetector_baseline_history) lets the LLM learn a proper
    # per-source number.
    "energy": 20,
    "other": 150,
}


def bootstrap_default(sector: str) -> int:
    return _BOOTSTRAP_DEFAULTS.get(sector, _BOOTSTRAP_DEFAULTS["other"])


# ─── Cold-start / history-sufficiency ──────────────────────────────────────
# Judgment call, disclosed: 21 distinct calendar days of real observations —
# the middle of the 14-30 day range the mission brief itself suggested as
# reasonable. Distinct DAYS, not raw observation rows: the 6 tiered-cadence
# priority sources (scheduler.py's _priority_tiered_collection_job) can
# accumulate 10+ rows in a single day, and a threshold learned from one
# unusually busy/quiet day's repeated samples would not be a real baseline.
_MIN_HISTORY_DAYS = 21

# Sanity-guard bounds (never trust the LLM's number blind for a gate that
# decides whether a real Telegram push fires). Judgment call, disclosed:
# with a real observed spike in history, allow up to 3x the highest real
# spike ever seen — generous margin for a genuinely bigger future event,
# without accepting an arbitrary LLM number. With NO real spike ever
# observed for this source (the common/expected case — real outages are
# rare), cap at 20x the higher of the real quiet-day max or the sector
# bootstrap default, so a source with a near-zero quiet baseline doesn't
# get an unreasonably tiny ceiling either.
_SANITY_SPIKE_MULTIPLIER = 3
_SANITY_NO_SPIKE_MULTIPLIER = 20


@dataclass(frozen=True)
class HistorySummary:
    distinct_days: int
    quiet_count: int
    quiet_min: Optional[int]
    quiet_max: Optional[int]
    quiet_mean: Optional[float]
    quiet_p95: Optional[int]
    spike_events: list[dict]        # [{"observed_at": ..., "report_count": ...}]
    spike_max: Optional[int]


@dataclass(frozen=True)
class ThresholdResult:
    source_name: str
    sector: str
    threshold_value: int
    threshold_source: str     # see migration 0121's CHECK constraint for the 4 legal values
    reasoning: Optional[str]
    history_days_used: int
    llm_provider: Optional[str] = None


def summarize_history(observations: list[dict]) -> HistorySummary:
    """Pure function — separated from I/O so it's directly unit-testable
    against synthetic data (no live Supabase/LLM call required). Splits
    observations into 'quiet' (status != 'problems', i.e. the vast majority
    — this is what a per-source baseline distribution actually is) and
    'spike' (status == 'problems', a genuine historical event this source's
    own gate would have fired on, given the threshold in force at the time)
    buckets. Each observation dict is expected to have 'status',
    'report_count' (nullable), and 'observed_at' (ISO-8601 string) keys —
    the shape of a downdetector_baseline_history row."""
    distinct_days = len({_date_key(o) for o in observations})

    quiet_counts = sorted(
        o["report_count"] for o in observations
        if o.get("status") != "problems" and o.get("report_count") is not None
    )
    spikes = [
        {"observed_at": o.get("observed_at"), "report_count": o.get("report_count")}
        for o in observations
        if o.get("status") == "problems" and o.get("report_count") is not None
    ]
    spike_counts = [s["report_count"] for s in spikes]

    return HistorySummary(
        distinct_days=distinct_days,
        quiet_count=len(quiet_counts),
        quiet_min=quiet_counts[0] if quiet_counts else None,
        quiet_max=quiet_counts[-1] if quiet_counts else None,
        quiet_mean=(sum(quiet_counts) / len(quiet_counts)) if quiet_counts else None,
        quiet_p95=_percentile(quiet_counts, 95) if quiet_counts else None,
        spike_events=spikes,
        spike_max=max(spike_counts) if spike_counts else None,
    )


def _date_key(observation: dict) -> str:
    raw = observation.get("observed_at") or ""
    return raw[:10] if len(raw) >= 10 else raw


def _percentile(sorted_values: list[int], pct: int) -> int:
    if not sorted_values:
        return 0
    k = (len(sorted_values) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return round(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f))


# ─── LLM recommendation ─────────────────────────────────────────────────────

_THRESHOLD_TASK_TYPE = "downdetector-threshold-recompute"

_THRESHOLD_SYSTEM_PROMPT = (
    "You calibrate an outage-detection threshold for a crowdsourced report-"
    "volume monitoring system (Downdetector-style). You are given real "
    "historical data for ONE company/service: its quiet-day 24h peak "
    "report-count distribution (the normal, no-incident range) and, if any "
    "occurred, real past incidents where the service's status reached its "
    "top severity tier, with the report count observed at that time. "
    "Recommend a single integer report-count threshold: the monitoring "
    "system will treat this source as having a genuine outage ONLY when its "
    "24h peak report count reaches or exceeds your number AND its status is "
    "at the top severity tier. Your number must sit comfortably above the "
    "quiet-day range (a threshold at or near the quiet baseline would "
    "misfire on ordinary days) while still being low enough to catch a "
    "real, proportionally significant event for THIS source — do not "
    "simply copy a number from a different company or sector; reason only "
    "from the data given. If a real past incident's report count is "
    "provided, your threshold should sit at or below it, with some margin, "
    "not above it. "
    "Respond in exactly this format and nothing else:\n"
    "THRESHOLD: <a single positive integer>\n"
    "REASONING: <one or two brief sentences, grounded only in the data given>"
)


def _build_threshold_prompt(source_name: str, sector: str, summary: HistorySummary) -> str:
    lines = [
        f"Source: {source_name}",
        f"Sector: {sector}",
        f"Real observation history: {summary.distinct_days} distinct days, "
        f"{summary.quiet_count} quiet-status observations with a parsed report count.",
    ]
    if summary.quiet_count:
        lines.append(
            "Quiet-day 24h peak report-count distribution: "
            f"min={summary.quiet_min}  mean={summary.quiet_mean:.1f}  "
            f"p95={summary.quiet_p95}  max={summary.quiet_max}"
        )
    else:
        lines.append("Quiet-day distribution: no quiet-status observations with a parsed count.")

    if summary.spike_events:
        lines.append(
            f"Known past incidents (status reached top severity tier), "
            f"{len(summary.spike_events)} total, highest report count "
            f"observed = {summary.spike_max}:"
        )
        for ev in summary.spike_events[-5:]:
            lines.append(f"  {ev['observed_at']}: {ev['report_count']} reports")
    else:
        lines.append("Known past incidents: none observed yet in this source's history.")

    return "\n".join(lines)


def _parse_threshold_answer(raw: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """Strict parse of the required 'THRESHOLD: <int>' / 'REASONING: ...'
    format — same discipline as intelligence_store.py's
    '_parse_blast_radius_answer()'. Returns (None, None) on any format
    mismatch, treated by the caller as a provider failure (falls through to
    the next provider, or to the bootstrap default if all fail)."""
    if not raw:
        return None, None
    threshold: Optional[int] = None
    reasoning: Optional[str] = None
    for line in raw.splitlines():
        line = line.strip()
        if threshold is None and line.upper().startswith("THRESHOLD:"):
            value = line.split(":", 1)[1].strip()
            match = re.search(r"-?\d+", value)
            if match:
                threshold = int(match.group())
        elif reasoning is None and line.upper().startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()
    return threshold, reasoning


def _call_threshold_llm(prompt: str) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """Same never-raise, try-gemini-then-mistral-then-ollama fallback chain
    as intelligence_store.py::_call_blast_radius_llm() — shared PATTERN,
    not shared code, since that function is private to the outage-alert
    push-guard module and this is a genuinely different call site (different
    prompt, different governance task_type, different caller). Returns
    (threshold_or_None, provider_name_or_None, reasoning_or_None)."""
    from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    mistral_key = os.getenv("MISTRAL_API_KEY", "")
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_OUTAGE_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")

    providers = [
        ("gemini-2.5-flash", lambda p: call_gemini(
            _THRESHOLD_SYSTEM_PROMPT, p, api_key=gemini_key, max_output_tokens=200)),
        ("mistral-small", lambda p: call_mistral(
            _THRESHOLD_SYSTEM_PROMPT, p, api_key=mistral_key, max_tokens=200)),
        (ollama_model, lambda p: call_ollama(
            _THRESHOLD_SYSTEM_PROMPT, p, base_url=ollama_base, model=ollama_model, num_predict=150)),
    ]
    for name, fn in providers:
        try:
            raw = fn(prompt)
            threshold, reasoning = _parse_threshold_answer(raw)
            if threshold is not None:
                return threshold, name, reasoning
            log.warning(
                "[downdetector-threshold] LLM provider %s returned unparseable output: %r",
                name, raw,
            )
        except Exception as exc:
            log.warning("[downdetector-threshold] LLM provider %s failed: %s", name, exc)
    return None, None, None


# ─── Sanity guard ────────────────────────────────────────────────────────────

def sanity_check(
    candidate: Optional[int], summary: HistorySummary, bootstrap: int,
) -> tuple[bool, str]:
    """Never trust the LLM's recommendation blind for a gate that decides
    whether a real Telegram push fires. Returns (passes, reason) — reason
    is always populated (explains why it passed too, not just why it
    failed), for logging either way."""
    if candidate is None:
        return False, "no numeric threshold recovered from the LLM response"
    if candidate <= 0:
        return False, f"threshold ({candidate}) must be a positive integer"

    quiet_max = summary.quiet_max or 0
    if candidate <= quiet_max:
        return False, (
            f"threshold ({candidate}) is at or below the highest real "
            f"quiet-day count ever observed ({quiet_max}) -- would misfire "
            f"on an ordinary day"
        )

    if summary.spike_max:
        cap = summary.spike_max * _SANITY_SPIKE_MULTIPLIER
    else:
        cap = max(quiet_max, bootstrap) * _SANITY_NO_SPIKE_MULTIPLIER
    if candidate > cap:
        return False, (
            f"threshold ({candidate}) exceeds the sanity cap ({cap}) derived "
            f"from real historical evidence -- would make the gate "
            f"effectively impossible to trigger"
        )

    return True, (
        f"threshold ({candidate}) is above the highest quiet-day count "
        f"({quiet_max}) and within the historical-evidence sanity cap ({cap})"
    )


# ─── Orchestration ───────────────────────────────────────────────────────────

def recompute_threshold_for_source(
    source_name: str,
    sector: str,
    observations: list[dict],
    *,
    min_history_days: int = _MIN_HISTORY_DAYS,
) -> ThresholdResult:
    """Pure orchestration over already-fetched `observations` (list of dicts
    with 'status'/'report_count'/'observed_at' keys, e.g. rows from
    downdetector_baseline_history) — no I/O of its own beyond the LLM call,
    so the cold-start and sanity-guard-rejection paths are directly
    unit-testable with synthetic data (see
    tests/test_downdetector_thresholds.py), without needing 30 real days to
    accumulate or a real LLM call."""
    default = bootstrap_default(sector)
    summary = summarize_history(observations)

    if summary.distinct_days < min_history_days:
        log.info(
            "[downdetector-threshold] %s: insufficient history (%d/%d days) "
            "-- using sector '%s' bootstrap default (%d)",
            source_name, summary.distinct_days, min_history_days, sector, default,
        )
        return ThresholdResult(
            source_name=source_name, sector=sector, threshold_value=default,
            threshold_source="bootstrap_default_insufficient_history",
            reasoning=f"only {summary.distinct_days}/{min_history_days} days of "
                      f"real observation history -- nothing real to learn from yet",
            history_days_used=summary.distinct_days,
        )

    prompt = _build_threshold_prompt(source_name, sector, summary)
    candidate, provider, llm_reasoning = _call_threshold_llm(prompt)

    if candidate is None:
        log.warning(
            "[downdetector-threshold] %s: all LLM providers failed or returned "
            "unparseable output -- using sector '%s' bootstrap default (%d)",
            source_name, sector, default,
        )
        return ThresholdResult(
            source_name=source_name, sector=sector, threshold_value=default,
            threshold_source="bootstrap_default_llm_unavailable",
            reasoning="all LLM providers failed or returned unparseable output",
            history_days_used=summary.distinct_days,
        )

    passed, sanity_reason = sanity_check(candidate, summary, default)
    if not passed:
        log.warning(
            "[downdetector-threshold] %s: LLM (%s) recommended %s, REJECTED by "
            "sanity guard (%s) -- using sector '%s' bootstrap default (%d)",
            source_name, provider, candidate, sanity_reason, sector, default,
        )
        return ThresholdResult(
            source_name=source_name, sector=sector, threshold_value=default,
            threshold_source="bootstrap_default_after_llm_reject",
            reasoning=f"LLM recommended {candidate} ({llm_reasoning or 'no reasoning given'}), "
                      f"rejected by sanity guard: {sanity_reason}",
            history_days_used=summary.distinct_days,
            llm_provider=provider,
        )

    log.info(
        "[downdetector-threshold] %s: LLM (%s) recommended %s, PASSED sanity "
        "guard (%s) -- adopting as learned threshold",
        source_name, provider, candidate, sanity_reason,
    )
    return ThresholdResult(
        source_name=source_name, sector=sector, threshold_value=candidate,
        threshold_source="llm_learned",
        reasoning=llm_reasoning or sanity_reason,
        history_days_used=summary.distinct_days,
        llm_provider=provider,
    )


def recompute_all(
    *, days_lookback: int = 90, min_history_days: int = _MIN_HISTORY_DAYS,
) -> list[ThresholdResult]:
    """Nightly entry point (intelligence/scheduler.py::
    _downdetector_threshold_recompute_job). For every registered Downdetector
    source (active or not — an inactive source can still hold real history
    from before it was deactivated, and computing a threshold for it costs
    nothing extra), recompute and persist its current threshold. Never
    raises — logs and skips a source on any per-source failure, same
    discipline as the rest of this codebase's scheduled jobs."""
    from intelligence.ingestion.downdetector_adapter import sector_for_slug, slug_from_url
    from intelligence.persistence import intelligence_store as store

    since = (datetime.now(timezone.utc) - timedelta(days=days_lookback)).isoformat()

    all_sources = [
        s for s in store.load_source_registry_all()
        if s.get("source_type") == "downdetector"
    ]
    # load_source_registry_all() is active-agnostic (unlike load_source_registry())
    # -- deliberate, see docstring above: recompute for inactive sources too.

    results: list[ThresholdResult] = []
    for source in all_sources:
        source_name = source["source_name"]
        try:
            sector = sector_for_slug(slug_from_url(source["url"]))
            observations = store.load_downdetector_history(source_name, since)
            result = recompute_threshold_for_source(
                source_name, sector, observations, min_history_days=min_history_days,
            )
            store.save_downdetector_threshold(
                source_name=result.source_name,
                sector=result.sector,
                threshold_value=result.threshold_value,
                threshold_source=result.threshold_source,
                reasoning=result.reasoning,
                history_days_used=result.history_days_used,
                llm_provider=result.llm_provider,
            )
            results.append(result)
        except Exception as exc:
            log.error("[downdetector-threshold] recompute failed for %s: %s", source_name, exc)

    return results
