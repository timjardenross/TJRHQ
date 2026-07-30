#!/usr/bin/env python3
"""
Intelligence Audit Runner — Three-Track Audit of Phase A Pipeline

Runs all three audit tracks:
1. Source Fidelity (data quality, signal-to-noise)
2. Enrichment Validation (scoring/tiering accuracy)
3. Brief Coherence (narrative quality)

Generates audit report in markdown + templates for manual review.

Usage:
  python scripts/run_intelligence_audit.py                    # Run all tracks
  python scripts/run_intelligence_audit.py --track fidelity   # Run one track
  python scripts/run_intelligence_audit.py --days 30          # Audit last 30 days
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.audit import (
    source_fidelity_report,
    print_fidelity_report,
    enrichment_sample,
    enrichment_stats,
    print_enrichment_validation_template,
    print_enrichment_stats,
    brief_sample,
    print_brief_coherence_template,
    print_brief_stats,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("intelligence-audit")


def run_audit_track_1_fidelity(days: int = 30) -> dict:
    """Track 1: Source Fidelity — which sources generate signal?"""
    log.info("=" * 80)
    log.info("TRACK 1: SOURCE FIDELITY")
    log.info("=" * 80)

    report = source_fidelity_report(days=days)
    print_fidelity_report(report)

    return report


def run_audit_track_2_enrichment(days: int = 14) -> dict:
    """Track 2: Enrichment Validation — is scoring/tiering accurate?"""
    log.info("=" * 80)
    log.info("TRACK 2: ENRICHMENT VALIDATION")
    log.info("=" * 80)

    # Get statistics
    stats = enrichment_stats(days=days)
    print_enrichment_stats(stats)

    # Get sample events for manual review
    samples = enrichment_sample(days=days, sample_per_level=10)
    print_enrichment_validation_template(samples)

    return {
        "stats": stats,
        "samples": samples,
    }


def run_audit_track_3_briefs(days: int = 30, limit: int = 5) -> dict:
    """Track 3: Brief Coherence — do briefs accurately reflect signals?"""
    log.info("=" * 80)
    log.info("TRACK 3: BRIEF COHERENCE")
    log.info("=" * 80)

    samples = brief_sample(limit=limit, days=days)
    print_brief_stats(samples)
    print_brief_coherence_template(samples)

    return samples


def generate_audit_report(fidelity: dict, enrichment: dict, briefs: dict) -> str:
    """Generate markdown audit report."""
    report = f"""# Intelligence Audit Report

**Generated:** {datetime.utcnow().isoformat()}

---

## Executive Summary

This audit validates three dimensions of the Phase A intelligence pipeline:

1. **Source Fidelity** — Which sources generate operational intelligence?
2. **Enrichment Validation** — Is scoring/tiering accurate and useful?
3. **Brief Coherence** — Do briefs accurately reflect signals and inform decisions?

---

## Track 1: Source Fidelity

**Measurement:** Signal-to-noise ratio per source (items collected → events classified).

**Summary:**
- Total sources monitored: {fidelity['total_sources']}
- Overall signal rate: {fidelity['summary']['overall_signal_rate']:.1%}
- High-value sources (>5 events): {len(fidelity['summary']['high_value_sources'])}
- Low-value sources (<1 event): {len(fidelity['summary']['low_value_sources'])}
- Degraded sources (>20% failure): {len(fidelity['summary']['degraded_sources'])}

**Interpretation:**
- Signal rate {fidelity['summary']['overall_signal_rate']:.1%} indicates how many collected items become classified events.
- High-value sources should be prioritized; low-value sources are archive candidates.
- Degraded sources need health review or may require archival.

**Recommendation:**
Archive the following low-value sources (generate zero signal in {fidelity['period_days']} days):
{format_list(fidelity['summary']['low_value_sources'][:5])}

---

## Track 2: Enrichment Validation

**Measurement:** Accuracy of source_tier classification and score_breakdown scoring.

**Statistics:**
- Total events sampled: {enrichment['stats']['total_events']}
- Score breakdown population rate: {enrichment['stats']['score_breakdown_population_rate']:.1%}
- Events by tier: {format_dict(enrichment['stats']['tier_distribution'])}
- Events by risk: {format_dict(enrichment['stats']['risk_distribution'])}

**Potential Misclassifications:**
{format_list(enrichment['stats']['misclassification_patterns']) if enrichment['stats']['misclassification_patterns'] else '  None detected'}

**Next Step:**
Review {len(enrichment['samples']['events'].get('HIGH', []))} HIGH-risk events manually to validate tier accuracy.
Use the validation template above to assess scoring logic.

---

## Track 3: Brief Coherence

**Measurement:** Narrative quality and alignment with underlying signal data.

**Summary:**
- Briefs sampled: {len(briefs['briefs'])}
- Total events included in briefs: {sum(b['events_summary']['included'] for b in briefs['briefs'])}
- Total events suppressed: {sum(b['events_summary']['suppressed'] for b in briefs['briefs'])}

**Manual Review Instructions:**
Use the brief coherence template above. For each brief, assess:
- ✓ Does executive snapshot reflect top events?
- ✓ Are emerging themes grounded in actual signal data?
- ✓ Is forward watch specific (not generic)?
- ✓ Does CPS230 language match operational resilience domain?
- ✓ Is overall risk justified by event composition?

---

## Remediation Roadmap

### Immediate (Week 1 of Phase B):
- [ ] Archive low-value sources identified in Track 1
- [ ] Review HIGH-risk events in Track 2 for misclassifications
- [ ] Run manual coherence assessment on Track 3 briefs

### Short-term (Phase B Week 2–3):
- [ ] Tune enrichment scoring weights based on validation findings
- [ ] Update source tier classifier if systematic misclassifications found
- [ ] Validate brief narrative quality with pilot team feedback

### Long-term (Phase B hardening):
- [ ] Build automated enrichment quality checks (% score_breakdown populated, tier distribution)
- [ ] Instrument brief coherence checks (snapshot ↔ events alignment)
- [ ] Add source health dashboards (real-time signal-to-noise monitoring)

---

## Sign-Off

**Audit Scope:**
- Source Fidelity: {fidelity['period_days']} days
- Enrichment Validation: {enrichment['stats']['period_days']} days
- Brief Coherence: {briefs['period_days']} days

**Status:** Ready for manual validation and remediation prioritization.

**Next Phase:** Finalize manual reviews and execute remediation roadmap in parallel with Phase B UI build.
"""
    return report


def format_list(items, max_items=5):
    """Format a list for markdown."""
    if not items:
        return "  (none)"
    items = items[:max_items]
    return "\n".join(f"  - {item}" for item in items)


def format_dict(d):
    """Format a dict for markdown."""
    return ", ".join(f"{k}: {v}" for k, v in sorted(d.items()))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Intelligence Audit — Three-track evaluation of Phase A pipeline"
    )
    parser.add_argument(
        "--track",
        choices=["fidelity", "enrichment", "briefs", "all"],
        default="all",
        help="Which audit track to run (default: all)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Time window for audit (default: 30 days)",
    )
    parser.add_argument(
        "--output",
        help="Save audit report to file (default: stdout)",
    )
    args = parser.parse_args()

    log.info("Starting Intelligence Audit...")
    log.info(f"  Track: {args.track}")
    log.info(f"  Time window: {args.days} days\n")

    results = {}

    if args.track in ("fidelity", "all"):
        results["fidelity"] = run_audit_track_1_fidelity(days=args.days)

    if args.track in ("enrichment", "all"):
        results["enrichment"] = run_audit_track_2_enrichment(days=args.days)

    if args.track in ("briefs", "all"):
        results["briefs"] = run_audit_track_3_briefs(days=args.days)

    # Generate summary report
    if args.track == "all" and all(k in results for k in ["fidelity", "enrichment", "briefs"]):
        report = generate_audit_report(
            results["fidelity"],
            results["enrichment"],
            results["briefs"],
        )

        if args.output:
            with open(args.output, "w") as f:
                f.write(report)
            log.info(f"✓ Audit report saved to {args.output}")
        else:
            print("\n" + "=" * 100)
            print("AUDIT REPORT")
            print("=" * 100)
            print(report)

    log.info("\n✓ Intelligence Audit complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
