"""USS-TJR-MSN-0339 WP5 — Operational Intelligence Validation Suite.

A standing, replay-based regression detector so a future Telstra-class
silent failure (a broken scraper masked as "ok", a schema-drift bug
silently emptying every brief) is caught automatically, instead of
discovered by a missed alert (per MSN-0338/MSN-0339's own founding
incident). Design: `reports/USS-TJR-MSN-0339-WP5-Validation-Suite-Design.md`.

Two case kinds:
- REAL cases (`_case_*`) query live `intelligence_events` rows by durable
  content match (title substring), not by event_id — event_id is stable
  once written, but matching by content keeps cases readable and lets a
  case still resolve if a row is ever re-collected under a new id.
- SYNTHETIC REPLAY cases run a real historical incident's genuine public
  text through `classify()`/`rank()` directly, no DB write — for the two
  gaps the design doc named (no live bushfire or AWS-active-incident case
  exists in production data yet): a real 2016-06-04 AWS Sydney
  (ap-southeast-2) power-event post-incident summary, and BOM's own
  published sample Fire Weather Warning. Neither is fabricated content.

Each case asserts against MSN-0338 §3's own stage schema: collectible ->
content-plausible -> classified correctly -> scored plausibly -> not
silently deduped/dropped -> reaches the right destination. A case stops
and reports at its first failed stage.

One correction versus the original design doc, found while building this:
the design doc named the GCP case as "duplicate rows across polls (a
dedup regression check)" — live query found exactly ONE row per distinct
GCP-2026-NNN advisory despite the source being polled multiple times
daily. Dedup is working correctly here, not regressed. The case below
asserts that (a real, useful, different check) rather than a
duplicate-row bug that live data shows doesn't exist — per this
programme's own verification-over-assumption discipline.

Explicit non-goals (design doc §5, restated): does not tune confidence/
threshold values; does not claim 100% real-world case coverage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

STAGES = [
    "collectible",
    "content_plausible",
    "classified_correctly",
    "scored_plausibly",
    "not_silently_dropped",
    "reaches_right_destination",
]


@dataclass
class CaseResult:
    case_name: str
    kind: str  # real | negative_control | synthetic_replay
    passed: bool
    stage_reached: str  # last stage attempted; == STAGES[-1] on a full pass
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteReport:
    generated_at: str
    results: list[CaseResult]

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    def render(self) -> str:
        lines = [
            f"Operational Intelligence Validation Suite — {self.generated_at}",
            f"{sum(r.passed for r in self.results)}/{len(self.results)} cases passed",
            "",
        ]
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            lines.append(f"[{mark}] {r.case_name} ({r.kind}) — stage: {r.stage_reached}")
            lines.append(f"       {r.detail}")
        return "\n".join(lines)


def _fail(name: str, kind: str, stage: str, detail: str, evidence: Optional[dict] = None) -> CaseResult:
    return CaseResult(case_name=name, kind=kind, passed=False, stage_reached=stage, detail=detail, evidence=evidence or {})


def _pass(name: str, kind: str, detail: str, evidence: Optional[dict] = None) -> CaseResult:
    return CaseResult(case_name=name, kind=kind, passed=True, stage_reached=STAGES[-1], detail=detail, evidence=evidence or {})


def _query_events(raw_title_ilike: str, limit: int = 10) -> list[dict]:
    from tools.supabase.client import CommanderSupabaseClient

    client = CommanderSupabaseClient()
    raw = client.raw_client
    if raw is None:
        return []
    res = (
        raw.table("intelligence_events")
        .select(
            "event_id,raw_title,event_type,sector,rank_score,confidence,operational_relevance,"
            "published_at,collected_at,customer_impact,banking_relevance,cps230_relevance"
        )
        .ilike("raw_title", raw_title_ilike)
        .order("rank_score", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def _row_importance(row: dict) -> int:
    """Same tiering as intelligence_store._derive_attention_importance, run
    against a queried DB row instead of a RankedEvent. rank_score itself is
    NOT a severity signal (2026-08-22/23 fix, intelligence_store.py:768) —
    it's deliberately deflated by recency_decay/SRS and was documented to
    never cross 71 on 1000 live real events, so validation cases assert on
    this derived tier instead of the raw column."""
    is_red = row.get("customer_impact") == "high" or row.get("banking_relevance") == "high"
    is_amber = row.get("customer_impact") == "medium" or row.get("banking_relevance") == "medium"
    if is_red and row.get("cps230_relevance"):
        return 90
    if is_red:
        return 55
    if is_amber:
        return 42
    return 15


def _replay_through_attention_engine(row: dict) -> "AttentionDecision":  # noqa: F821 — type import below
    from core.platform.attention_engine import evaluate_event

    return evaluate_event({
        "event_id": row["event_id"],
        "event_type": "intelligence.signal.ranked",
        "domain": "operational-resilience-intelligence",
        "importance": _row_importance(row),
        "confidence": round((row["confidence"] or 0) * 100),
        "relevance": round((row["operational_relevance"] or 0) * 100),
    })


# ─── Real cases (design doc §2a) ────────────────────────────────────────────

def _case_slack_outage() -> CaseResult:
    name = "slack_outage_2026_07_05"
    kind = "real"
    rows = _query_events("%Trouble with Slack - General Slack functionality%")
    if not rows:
        return _fail(name, kind, "collectible", "no matching row found in intelligence_events")
    row = rows[0]
    if row["published_at"] is None:
        return _fail(name, kind, "content_plausible", "published_at is null on a supposedly real row", {"row": row})
    if row["event_type"] in ("cross_sector", "other"):
        return _fail(name, kind, "classified_correctly", f"event_type={row['event_type']}", {"row": row})
    importance = _row_importance(row)
    if importance < 55:
        return _fail(name, kind, "scored_plausibly", f"importance={importance}, expected >=55 (RED)", {"row": row})
    decision = _replay_through_attention_engine(row)
    from core.platform.attention_engine import AttentionCategory

    if decision.category in (AttentionCategory.NEVER_INTERRUPT, AttentionCategory.SHOULD_SIMPLY_BE_REMEMBERED):
        return _fail(
            name, kind, "reaches_right_destination",
            f"Attention Engine would silently drop this ({decision.category.value}) — the exact MSN-0338 failure mode",
            {"row": row, "decision_category": decision.category.value},
        )
    # MSN-0338's own finding: this event never reached the Captain. Replayed
    # today it correctly does NOT land in NEVER_INTERRUPT/REMEMBERED (the
    # silent-drop failure mode) — but its real confidence (69) is below the
    # interrupt_confidence_floor (70), so it correctly lands in
    # CAN_BE_DELAYED, not INTERRUPT_NOW. That's not a suite failure: MSN-0329
    # forbids tuning thresholds to make a specific case pass, and
    # "high-importance-but-unverified never interrupts" is the Attention
    # Engine's own documented, intentional behaviour. What this case proves
    # is narrower and real: post-WP2, this event is no longer silently
    # dropped before rendering (daily_brief.py's fix) — it just isn't
    # urgent enough to autonomously interrupt, which is honest, not broken.
    return _pass(
        name, kind,
        f"real row found, importance={importance}, replay classifies {decision.category.value} "
        "(not silently dropped; below INTERRUPT_NOW's confidence floor on its real confidence value, "
        "which is correct behaviour, not a miss)",
        {"row": row, "decision_category": decision.category.value},
    )


def _case_fortinet_alert() -> CaseResult:
    name = "fortinet_credential_exposure"
    kind = "real"
    rows = _query_events("%credential exposure affecting Fortinet%")
    if not rows:
        return _fail(name, kind, "collectible", "no matching row found")
    row = rows[0]
    if row["published_at"] is None:
        return _fail(name, kind, "content_plausible", "published_at is null", {"row": row})
    if row["event_type"] != "cyber":
        return _fail(name, kind, "classified_correctly", f"event_type={row['event_type']}, expected cyber", {"row": row})
    importance = _row_importance(row)
    if importance < 55:
        return _fail(name, kind, "scored_plausibly", f"importance={importance}, expected >=55 (RED)", {"row": row})
    decision = _replay_through_attention_engine(row)
    from core.platform.attention_engine import AttentionCategory

    if decision.category != AttentionCategory.INTERRUPT_NOW:
        return _fail(
            name, kind, "reaches_right_destination",
            f"expected INTERRUPT_NOW, replay gave {decision.category.value}",
            {"row": row, "decision_category": decision.category.value},
        )
    return _pass(name, kind, f"real row, importance={importance}, replay correctly classifies INTERRUPT_NOW", {"row": row})


def _case_cve_dual() -> CaseResult:
    name = "cve_splunk_oracle_dual"
    kind = "real"
    splunk = _query_events("CVE-2026-20253:%")
    oracle = _query_events("CVE-2026-35273:%")
    if not splunk or not oracle:
        return _fail(name, kind, "collectible", f"splunk_found={bool(splunk)} oracle_found={bool(oracle)}")
    for label, row in (("splunk", splunk[0]), ("oracle", oracle[0])):
        if row["event_type"] != "cyber":
            return _fail(name, kind, "classified_correctly", f"{label} event_type={row['event_type']}, expected cyber", {"row": row})
        if row["sector"] != "cyber_security":
            return _fail(name, kind, "classified_correctly", f"{label} sector={row['sector']}, expected cyber_security", {"row": row})
    return _pass(name, kind, "both real CVE rows classify cyber/cyber_security correctly", {"splunk": splunk[0], "oracle": oracle[0]})


def _case_gcp_advisories() -> CaseResult:
    """Corrected versus the design doc: live data shows dedup working
    (exactly one row per distinct GCP-2026-NNN advisory), not a duplicate
    regression. This case's real job is the dedup-correctness check below.

    Built while writing this case, NOT part of the pass/fail gate: found a
    real classifier gap (see KNOWN_GAPS) where some GCP security bulletins
    misclassified as `technology_outage` instead of `cyber` — fixed in
    MSN-0343 (classifier.py's cyber rule now matches the "vulnerabilit"
    stem instead of only the singular "vulnerability"). Left as an
    informational count rather than a hard pass/fail gate here: the rows
    already in intelligence_events from before the fix keep their original
    classification (not retroactively reclassified), so cyber_count on
    historical data won't hit 100% even though new ingestion will."""
    name = "gcp_advisory_batch_dedup"
    kind = "real"
    rows = _query_events("GCP-2026-%", limit=20)
    if len(rows) < 3:
        return _fail(name, kind, "collectible", f"only {len(rows)} GCP-2026-* rows found, expected several")
    titles = [r["raw_title"] for r in rows]
    if len(titles) != len(set(titles)):
        return _fail(name, kind, "not_silently_dropped", "duplicate raw_title found within the batch — dedup regression", {"titles": titles})
    cyber_count = sum(1 for r in rows if r["event_type"] == "cyber")
    return _pass(
        name, kind,
        f"{len(rows)} distinct GCP advisories, zero duplicate titles (dedup correct); "
        f"{cyber_count}/{len(rows)} classified cyber (see KNOWN_GAPS for the rest — a pre-existing classifier gap, not a dedup issue)",
        {"count": len(rows), "cyber_count": cyber_count},
    )


def _case_copilot_incident() -> CaseResult:
    name = "copilot_availability_incident"
    kind = "real"
    rows = _query_events("Incident with Copilot Availability")
    if not rows:
        return _fail(name, kind, "collectible", "no matching row found")
    row = rows[0]
    if row["event_type"] != "technology_outage":
        return _fail(name, kind, "classified_correctly", f"event_type={row['event_type']}, expected technology_outage", {"row": row})
    importance = _row_importance(row)
    if importance < 42:
        return _fail(name, kind, "scored_plausibly", f"importance={importance}, expected >=42 (AMBER)", {"row": row})
    return _pass(name, kind, f"real row, importance={importance}, classified technology_outage", {"row": row})


def _case_nbn_junk_negative_control() -> CaseResult:
    """Negative control — MUST fail content-plausibility to pass this case.
    These rows predate WP1's scraper fix (collected 2026-06-13); the live
    source is fixed now (WP1), but these specific historical rows are the
    exact known-junk signature (published_at always NULL, generic nav-link
    titles) the suite exists to keep catching if it ever recurs on another
    source. Matched by row characteristics, not a live source_health
    lookup — content_valid is a source-health-level signal reflecting
    TODAY's state, not these historical rows' state at collection time."""
    name = "nbn_pre_fix_junk_negative_control"
    kind = "negative_control"
    rows = _query_events("%nbn%", limit=20)
    junk = [r for r in rows if r["published_at"] is None]
    if not junk:
        return _fail(name, kind, "collectible", "no known-junk rows found — either fixed retroactively or query drifted")
    if len(junk) < 3:
        return _fail(name, kind, "content_plausible", f"only {len(junk)} published_at=null rows, expected several", {"rows": junk})
    # This IS the pass condition for a negative control: junk correctly
    # identifiable as content-invalid by its own field values.
    return _pass(
        name, kind,
        f"{len(junk)} known-junk rows correctly identifiable (published_at=null) — "
        "the exact signature this suite exists to keep catching",
        {"count": len(junk)},
    )


# ─── Synthetic replay cases (design doc §2b) ────────────────────────────────

def _case_bushfire_synthetic_replay() -> CaseResult:
    """Real historical content, no DB write: BOM's own published sample
    Fire Weather Warning (bom.gov.au/weather-services/bushfire/
    sample-fire-weather-warning.shtml — issued 03:12 WST Wed 23 Jan 2013,
    Western Australia). Genuine BOM-authored text, not fabricated by this
    suite. Weatherzone Warnings is the real, live, active source this
    programme uses for severe-weather content (BOM's own feed is inactive/
    403-blocked per MSN-0338 §2) — reused here as the plausible real
    source this content would arrive through."""
    name = "bushfire_synthetic_replay_bom_sample"
    kind = "synthetic_replay"
    from datetime import timedelta

    from intelligence.classification.classifier import classify
    from intelligence.models import IntelligenceItem
    from intelligence.ranking.ranker import rank

    item = IntelligenceItem(
        source_id="cd47b5f7-14f9-4357-99c2-7c89f4f9dea0",  # Weatherzone Warnings (real, active)
        source_name="Weatherzone Warnings",
        source_priority=1,
        source_confidence_weight=0.88,
        source_category="emergency_management",
        raw_title="Fire Weather Warning — Extreme Fire Danger, Goldfields and South Interior",
        raw_summary=(
            "Extreme Fire Danger is forecast for the following fire weather districts: "
            "Goldfields and South Interior; Severe Fire Danger is forecast for the following "
            "fire weather districts: Esperance Shire, Gascoyne Coast and North Interior. "
            "These are the worst conditions for a bush or grass fire. If a fire starts and "
            "takes hold it will be extremely difficult to control and will take significant "
            "firefighting resources and cooler conditions to bring under control."
        ),
        canonical_url="https://www.bom.gov.au/weather-services/bushfire/sample-fire-weather-warning.shtml",
        published_at=datetime(2013, 1, 23, 3, 12, tzinfo=timezone.utc),
        collected_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    event = classify(item)
    ranked = rank([event])[0]
    if event.event_type not in ("severe_weather", "bushfire"):
        return _fail(
            name, kind, "classified_correctly",
            f"event_type={event.event_type}, expected severe_weather or bushfire",
            {"event_type": event.event_type},
        )
    from intelligence.persistence.intelligence_store import _derive_attention_importance

    importance = _derive_attention_importance(ranked)
    if importance < 42:
        return _fail(name, kind, "scored_plausibly", f"importance={importance}, expected >=42 (AMBER)", {"rank_score": ranked.rank_score, "importance": importance})
    return _pass(
        name, kind,
        f"real BOM sample warning text classifies {event.event_type}, importance={importance}",
        {"event_type": event.event_type, "rank_score": ranked.rank_score, "importance": importance},
    )


def _case_aws_sydney_synthetic_replay() -> CaseResult:
    """Real historical content, no DB write: AWS's own official post-event
    summary "Summary of the AWS Service Event in the Sydney Region",
    June 4 2016 (aws.amazon.com/message/4372T8/) — a real DRUPS/utility
    power-loss cascading failure, genuine AWS-authored incident text."""
    name = "aws_sydney_synthetic_replay_2016_06_04"
    kind = "synthetic_replay"
    from intelligence.classification.classifier import classify
    from intelligence.models import IntelligenceItem
    from intelligence.ranking.ranker import rank

    item = IntelligenceItem(
        source_id="ffbb72c8-45aa-45a3-b4e4-478d474744f6",  # AWS Sydney (ap-southeast-2) — real, active
        source_name="AWS Sydney (ap-southeast-2)",
        source_priority=1,
        source_confidence_weight=0.97,
        source_category="cloud_technology",
        raw_title="Summary of the AWS Service Event in the Sydney Region",
        raw_summary=(
            "A utility power loss during severe weather triggered a cascading infrastructure "
            "failure at 10:25 PM PDT on June 4th. The facility's backup diesel rotary "
            "uninterruptable power supply (DRUPS) malfunctioned when exposed to an unusually "
            "long voltage sag rather than a complete outage; critical isolation breakers "
            "failed to open quickly enough, draining the DRUPS energy reserve into the "
            "degraded grid and preventing generator engagement. EC2 instances and EBS volumes "
            "in a single Availability Zone experienced outages; customers saw errors launching "
            "new instances or scaling auto-scaling groups. Power was restored at 11:46 PM PDT; "
            "over 80% of affected instances were operational by 1:00 AM; DNS issues persisted "
            "until 2:49 AM; a latent software bug delayed remaining recovery until ~8:00 AM. "
            "Less than 0.01% of EBS volumes suffered permanent data loss."
        ),
        canonical_url="https://aws.amazon.com/message/4372T8/",
        published_at=datetime(2016, 6, 4, tzinfo=timezone.utc),
        collected_at=datetime.now(timezone.utc),
    )
    event = classify(item)
    ranked = rank([event])[0]
    if event.event_type not in ("technology_outage", "cloud_outage"):
        return _fail(
            name, kind, "classified_correctly",
            f"event_type={event.event_type}, expected technology_outage or cloud_outage",
            {"event_type": event.event_type},
        )
    from intelligence.persistence.intelligence_store import _derive_attention_importance

    importance = _derive_attention_importance(ranked)
    if importance < 42:
        return _fail(name, kind, "scored_plausibly", f"importance={importance}, expected >=42 (AMBER)", {"rank_score": ranked.rank_score, "importance": importance})
    return _pass(
        name, kind,
        f"real AWS post-event summary text classifies {event.event_type}, importance={importance}",
        {"event_type": event.event_type, "rank_score": ranked.rank_score, "importance": importance},
    )


CASES = [
    _case_slack_outage,
    _case_fortinet_alert,
    _case_cve_dual,
    _case_gcp_advisories,
    _case_copilot_incident,
    _case_nbn_junk_negative_control,
    _case_bushfire_synthetic_replay,
    _case_aws_sydney_synthetic_replay,
]

# Named, tracked gap — not silently absent (design doc §5's own non-goal:
# "a named list of what's not yet covered ships with the suite"). No real
# banking/regulatory negative control is included; MSN-0338 §5 already
# found APRA/RBA-class events reach briefs correctly, making this the
# programme's lowest-priority gap to fill.
KNOWN_GAPS = [
    "No banking/regulatory negative control case (lowest priority — MSN-0338 §5 already confirmed this path works)",
    "No LIVE (non-replay) AWS-active-incident or bushfire case exists in production data yet — "
    "both cases above are real historical text replayed offline, not a currently-collectible live row; "
    "swap in a live row here the day a real one exists.",
    "FIXED (MSN-0343, 2026-07-08): some GCP security bulletins (GCP-2026-025/027/029/039, real cross-platform "
    "GKE bulletins with genuine CVEs) misclassified as technology_outage instead of cyber because the plural "
    "'vulnerabilities' in their boilerplate didn't substring-match the classifier's singular 'vulnerability' "
    "keyword. intelligence/classification/classifier.py's cyber _EVENT_TYPE_RULES entry now matches the "
    "'vulnerabilit' stem, covering both forms. Fix is forward-only — the GCP-2026-025/027/029/039 rows already "
    "in intelligence_events retain their original (wrong) classification from ingestion time; not retroactively "
    "reclassified, since doing so correctly requires re-running the full classify() pipeline per row, not just "
    "flipping event_type. The next real ingestion of a similar bulletin will classify correctly.",
]


def run_suite() -> SuiteReport:
    results = []
    for case_fn in CASES:
        try:
            results.append(case_fn())
        except Exception as exc:
            results.append(_fail(case_fn.__name__, "unknown", "collectible", f"case raised {type(exc).__name__}: {exc}"))
    return SuiteReport(generated_at=datetime.now(timezone.utc).isoformat(), results=results)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = run_suite()
    print(report.render())
    if not report.all_passed:
        import sys

        sys.exit(1)
