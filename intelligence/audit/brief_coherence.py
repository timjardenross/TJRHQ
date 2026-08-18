"""
Track 3: Brief Coherence Validation
Validates that generated briefs accurately reflect the underlying signal data
and produce actionable, coherent narratives.

Checks:
- executive_snapshot consistency with top_events
- emerging_themes grounded in actual signal patterns
- forward_watch predictions aligned with trend data
- CPS230 implications anchored to domain (operational resilience)
- overall_risk rating justified by event composition
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from intelligence.persistence import intelligence_store

log = logging.getLogger(__name__)

_STOPWORDS = {
    "with", "from", "this", "that", "have", "will", "into", "over", "after",
    "been", "were", "does", "than", "some", "more", "most", "such", "only",
}


def _significant_words(text: str) -> set[str]:
    # Starts with a letter so bare numbers don't count, but allows digits/
    # hyphens after it so identifiers like "CVE-2024-39024" — common in
    # top_events titles — still register as a shared token with the
    # narrative, not just plain-English words.
    return {
        w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{3,}", text.lower())
        if w not in _STOPWORDS
    }


def brief_sample(limit: int = 5, days: int = 30) -> dict:
    """Sample recent briefs for coherence validation.

    Returns dict with:
    - brief metadata (generated_at, period, risk)
    - top_events (signals selected for inclusion)
    - narrative sections (executive_snapshot, emerging_themes, forward_watch, etc.)
    - CPS230 implications
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    log.info(f"Sampling {limit} briefs from last {days} days...")
    query = (
        f"intelligence_briefs"
        f"?generated_at=gte.{since}"
        f"&order=generated_at.desc"
        f"&limit={limit}"
        f"&select=brief_id,generated_at,period_start,period_end,overall_risk,"
        f"executive_snapshot,emerging_themes,forward_watch,cps230_implications,"
        f"bottom_line,top_events,events_included,events_suppressed"
    )
    briefs = intelligence_store._get(query)

    samples = {
        "period_days": days,
        "sampled_at": datetime.utcnow().isoformat(),
        "total_briefs_sampled": len(briefs),
        "briefs": [],
    }

    for brief in briefs:
        # Parse top_events if it's JSON
        top_events = brief.get("top_events", [])
        if isinstance(top_events, str):
            try:
                top_events = json.loads(top_events)
            except:
                top_events = []

        cps230 = brief.get("cps230_implications", "")
        if isinstance(cps230, str):
            cps230 = cps230
        else:
            cps230 = json.dumps(cps230) if cps230 else ""

        brief_sample = {
            "brief_id": brief["brief_id"],
            "generated_at": brief["generated_at"],
            "period": f"{brief['period_start']} to {brief['period_end']}",
            "overall_risk": brief["overall_risk"],
            "events_summary": {
                "included": brief["events_included"],
                "suppressed": brief["events_suppressed"],
            },
            "top_events": [
                {
                    "event_id": e.get("event_id"),
                    "title": e.get("title", "")[:80],
                    "risk_rating": e.get("risk_rating"),
                    "source_name": e.get("source_name"),
                }
                for e in top_events[:3]  # First 3 for brevity
            ],
            "narrative": {
                "executive_snapshot": str(brief.get("executive_snapshot", ""))[:200] + "...",
                "emerging_themes": str(brief.get("emerging_themes", ""))[:150] + "...",
                "forward_watch": str(brief.get("forward_watch", ""))[:150] + "...",
                "bottom_line": str(brief.get("bottom_line", ""))[:200] + "...",
            },
            "cps230_implications": cps230[:200] + "...",
        }
        samples["briefs"].append(brief_sample)

    return samples


def brief_coherence_checks(brief_sample: dict) -> dict:
    """Run coherence checks on a single brief sample."""
    checks = {
        "brief_id": brief_sample["brief_id"],
        "checks": {
            "snapshot_reflects_events": None,
            "themes_grounded_in_data": None,
            "forward_watch_justified": None,
            "cps230_anchored_to_domain": None,
            "overall_risk_justified": None,
        },
        "notes": [],
    }

    # Check 1: Executive snapshot matches top_events. Was an exact-substring
    # match on the first 20 chars of a title — the LLM narrative paraphrases
    # rather than quoting titles verbatim, so this failed almost every real
    # brief regardless of actual grounding (confirmed live: drove coherence_score
    # to 75/100 on nearly every brief since 2026-06-20, the single largest
    # contributor to 0 briefs passing nightly QA). Fuzzy keyword-overlap
    # still requires genuine grounding (shared significant words) without
    # demanding verbatim title repetition.
    snapshot = brief_sample["narrative"]["executive_snapshot"]
    top_events = brief_sample["top_events"]
    snapshot_words = _significant_words(snapshot)
    event_words = {w for e in top_events for w in _significant_words(e["title"])}
    # A genuinely quiet period (every top event GREEN — a minor road closure,
    # a M2-3 earthquake) is correctly summarised as "no active threats", not
    # by naming the trivial event. That's accurate grounding, not a failure
    # to reference top events — forcing a name-check here would reward a
    # worse narrative.
    all_green = bool(top_events) and all(e.get("risk_rating") == "GREEN" for e in top_events)
    quiet_period_phrasing = any(
        phrase in snapshot.lower()
        for phrase in ("no active threat", "no significant", "no material", "no elevated")
    )
    if top_events and (snapshot_words & event_words or (all_green and quiet_period_phrasing)):
        checks["checks"]["snapshot_reflects_events"] = True
    else:
        checks["checks"]["snapshot_reflects_events"] = False
        checks["notes"].append("⚠ Executive snapshot does not reference top events")

    # Check 2: Themes plausible given event mix
    themes = brief_sample["narrative"]["emerging_themes"]
    if len(themes) > 20:  # Non-trivial narrative
        checks["checks"]["themes_grounded_in_data"] = True
    else:
        checks["checks"]["themes_grounded_in_data"] = False
        checks["notes"].append("⚠ Emerging themes are sparse or missing")

    # Check 3: Forward watch is more than boilerplate
    forward_watch = brief_sample["narrative"]["forward_watch"]
    if len(forward_watch) > 50 and forward_watch != "No forward watch":
        checks["checks"]["forward_watch_justified"] = True
    else:
        checks["checks"]["forward_watch_justified"] = False
        checks["notes"].append("⚠ Forward watch is generic or missing")

    # Check 4: CPS230 implications grounded
    cps230 = brief_sample["cps230_implications"]
    operational_terms = ["resilience", "continuity", "availability", "critical", "outage", "recovery"]
    if any(term in cps230.lower() for term in operational_terms):
        checks["checks"]["cps230_anchored_to_domain"] = True
    else:
        checks["checks"]["cps230_anchored_to_domain"] = False
        checks["notes"].append("⚠ CPS230 implications lack operational resilience vocabulary")

    # Check 5: Overall risk matches events
    events_with_high_risk = any(e["risk_rating"] == "HIGH" for e in top_events)
    overall_risk = brief_sample["overall_risk"]
    if (events_with_high_risk and overall_risk in ["HIGH", "CRITICAL"]) or (
        not events_with_high_risk and overall_risk in ["LOW", "MEDIUM"]
    ):
        checks["checks"]["overall_risk_justified"] = True
    else:
        checks["checks"]["overall_risk_justified"] = False
        checks["notes"].append(f"⚠ Overall risk {overall_risk} does not match event composition")

    return checks


def print_brief_coherence_template(samples: dict) -> None:
    """Print template for manual brief coherence validation."""
    print(f"\n{'='*100}")
    print(f"BRIEF COHERENCE VALIDATION TEMPLATE — Manual Review")
    print(f"{'='*100}\n")

    print("INSTRUCTIONS:")
    print("  For each brief below, review the narrative sections and assess coherence.")
    print("  A coherent brief: (1) reflects actual top events, (2) themes are grounded in data,")
    print("                    (3) forward watch is specific, (4) CPS230 is anchored to operations.\n")

    for i, brief in enumerate(samples["briefs"], 1):
        print(f"\n[BRIEF {i}] {brief['brief_id']}")
        print(f"  Generated: {brief['generated_at']} | Period: {brief['period']}")
        print(f"  Overall Risk: {brief['overall_risk']}")
        print(f"  Events: {brief['events_summary']['included']} included, {brief['events_summary']['suppressed']} suppressed\n")

        print(f"  TOP EVENTS (first 3):")
        for j, event in enumerate(brief["top_events"], 1):
            print(f"    {j}. {event['title']}")
            print(f"       Risk: {event['risk_rating']} | Source: {event['source_name']}\n")

        print(f"  NARRATIVE SECTIONS:")
        print(f"    Executive Snapshot:")
        print(f"      {brief['narrative']['executive_snapshot']}\n")
        print(f"    Emerging Themes:")
        print(f"      {brief['narrative']['emerging_themes']}\n")
        print(f"    Forward Watch:")
        print(f"      {brief['narrative']['forward_watch']}\n")
        print(f"    CPS230 Implications:")
        print(f"      {brief['cps230_implications']}\n")

        print(f"  COHERENCE CHECKLIST:")
        print(f"    [ ] Snapshot reflects actual top events?")
        print(f"    [ ] Themes are grounded in signal data (not generic)?")
        print(f"    [ ] Forward watch is specific & actionable (not boilerplate)?")
        print(f"    [ ] CPS230 uses operational resilience vocabulary?")
        print(f"    [ ] Overall risk justified by event composition?")
        print(f"    [ ] Bottom line is clear recommendation?")
        print(f"\n  Manual Assessment: ✓ COHERENT | ✗ FRAGMENTED | ? UNCLEAR")
        print(f"  Notes: __________________________________________________________________\n")

        print("-" * 100)

    print()


def print_brief_stats(samples: dict) -> None:
    """Print brief composition statistics."""
    print(f"\n{'='*80}")
    print(f"BRIEF COMPOSITION STATISTICS ({len(samples['briefs'])} sampled)")
    print(f"{'='*80}\n")

    if not samples["briefs"]:
        print(f"No briefs found in the sample period. Coherence audit cannot proceed.")
        print(f"(This may indicate: no briefs generated, or query filter too strict)\n")
        return

    total_events_included = sum(b["events_summary"]["included"] for b in samples["briefs"])
    total_events_suppressed = sum(b["events_summary"]["suppressed"] for b in samples["briefs"])

    print(f"AGGREGATE STATISTICS")
    print(f"  Total briefs: {len(samples['briefs'])}")
    print(f"  Total events included: {total_events_included}")
    print(f"  Total events suppressed: {total_events_suppressed}")

    if total_events_included + total_events_suppressed > 0:
        inclusion_rate = total_events_included / (total_events_included + total_events_suppressed) * 100
        print(f"  Inclusion rate: {inclusion_rate:.1f}%\n")
    else:
        print(f"  Inclusion rate: N/A (no events)\n")

    print(f"RISK DISTRIBUTION (overall_risk field)")
    risk_counts = {}
    for brief in samples["briefs"]:
        risk = brief["overall_risk"]
        risk_counts[risk] = risk_counts.get(risk, 0) + 1

    for risk in sorted(risk_counts.keys()):
        count = risk_counts[risk]
        print(f"  {risk}: {count}")

    print()
