#!/usr/bin/env python3
"""
Daily Health Source Accuracy Validation Job

Mirrors tools/intelligence/validate_source_accuracy.py's structure and its
2026-08-08 fix (real columns, not a nonexistent field) — built this way from
the start rather than repeating that mistake for the health domain.

2026-08-09 gap-closure: the Health_SRS formula (0093_health_osint_workbench.sql)
has 5 multiplicative terms — publisher_reputation, peer_reviewed,
avg_methodology_quality, the replication_success_rate/retraction_rate pair,
and the conflict_of_interest_disclosure/funding_transparency pair. Before
this fix, recompute_source_scores() only ever wrote replication_success_rate/
retraction_rate; avg_methodology_quality stayed frozen at the 0.5 default set
at auto-registration (collect_health_signals.py._get_or_create_source())
forever, and so did publisher_reputation (0.45 default) and
funding_transparency/conflict_of_interest_disclosure (0.5/True defaults).
That mathematically capped auto-registered sources (114/130 = 88% of the
registry) around SRS ~0.30 regardless of how well their signals validated —
below the TIER_3 floor of 0.45.

This fix closes the avg_methodology_quality gap specifically, and only for
auto-registered sources: every collected health_signals row already carries
a real, structurally-computed methodology_quality_score (from study_design/
sample_size/p_value presence — see collect_health_signals.py.
_methodology_quality()), independent of whether that signal ever matches
one of the 4 heuristic accuracy-verdict rules below.
recompute_source_scores() now aggregates that already-computed,
non-fabricated per-signal data into avg_methodology_quality — but only for
auto_registered=true sources. It deliberately does NOT touch the 16
hand-curated seed sources' avg_methodology_quality: verified against live
data that doing so is actively wrong, not just untested — see
recompute_avg_methodology_quality()'s docstring for the reproduced Lancet
TIER_1->TIER_4 regression this caused before the scoping fix.

publisher_reputation and funding_transparency/conflict_of_interest_disclosure
are NOT touched by this fix — there is no real per-source data stream in
this pipeline that could inform them (no citation-index/funding-disclosure
feed is collected), so writing to them here would mean fabricating a value
rather than surfacing real evidence. See
.claude/skills/bot-reviews/fixes-2026-08-09/health-osint-fixes.md for the
disclosed options on that gap (a documented "earn reputation via sustained
validation" graduation rule is the leading candidate, but the rate/cap
parameters are a policy choice, not a data-availability fact, so it's
flagged for Captain/Chief of Staff decision rather than guessed here).

Heuristic validation rules (disclosed as heuristic, not ground-truth):
  1. Source is a health_agency (NIH/FDA/CDC/WHO) -> accurate. Direct
     government/institutional publication, not a third-party claim.
  2. study_design == meta_analysis -> accurate. Systematic reviews are the
     most rigorous evidence tier; treating them as validated is standard
     evidence-hierarchy practice, not a real-world outcome check.
  3. study_design == RCT with sample_size >= 100 -> accurate. Adequately
     powered randomized trial.
  4. signal_type == adverse_event with no FDA flag and < 3 reports and no
     recorded severity -> flagged inaccurate (weak, unconfirmed safety
     claim) — the one rule that can produce a negative signal, so the
     validator isn't structurally incapable of ever penalizing a source.
  5. Everything else -> unvalidated (not saved, matches the technical
     validator's "don't save unknown" behavior).

Usage:
    python3 tools/health/validate_health_source_accuracy.py [--dry-run]
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

from supabase import create_client


class HealthSourceValidator:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.validated_count = 0
        self.errors = 0

    def validate_signal_accuracy(self, signal: dict, source_type: str):
        if source_type == "health_agency":
            return True
        if signal.get("study_design") == "meta_analysis":
            return True
        if signal.get("study_design") == "RCT" and (signal.get("sample_size") or 0) >= 100:
            return True
        if (signal.get("signal_type") == "adverse_event" and not signal.get("fda_flagged")
                and (signal.get("frequency_reported") or 0) < 3 and not signal.get("severity")):
            return False
        return None

    def get_unvalidated_signals_for_source(self, source_id: str, days: int = 30) -> list:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        already = (
            self.supabase.table("health_signal_validation")
            .select("signal_id").eq("source_id", source_id).execute()
        )
        validated_ids = {r["signal_id"] for r in (already.data or [])}

        resp = (
            self.supabase.table("health_signals")
            .select("signal_id, study_design, sample_size, signal_type, fda_flagged, frequency_reported, severity, collected_at")
            .eq("source_id", source_id).gt("collected_at", cutoff).execute()
        )
        signals = resp.data or []
        return [s for s in signals if s["signal_id"] not in validated_ids]

    def save_validation(self, signal_id, source_id, is_accurate, method, detail):
        if is_accurate is None:
            return
        if not self.dry_run:
            try:
                self.supabase.table("health_signal_validation").insert({
                    "signal_id": signal_id, "source_id": source_id, "is_accurate": is_accurate,
                    "validation_method": method, "validation_detail": detail, "validated_by": "system",
                }).execute()
            except Exception as e:
                logger.error(f"Save validation failed for {signal_id}: {e}")
                self.errors += 1
                return
        self.validated_count += 1

    def recompute_avg_methodology_quality(self, source_id, min_signals: int = 3):
        """Aggregate the real per-signal methodology_quality_score (already
        computed at collection time, independent of accuracy validation)
        into this source's avg_methodology_quality — the SRS input this job
        never wrote before. Queried from health_signals directly, not
        health_signal_validation: most signals never match one of the 4
        heuristic accuracy-verdict rules in validate_signal_accuracy() and
        so never get a validation row, but they all get a
        methodology_quality_score at collection time. Gating this on the
        same n>=10 threshold used for replication_success_rate below would
        starve it of data it already has.

        min_signals=3 is a disclosed, deliberately lower floor than the
        accuracy gate: methodology_quality_score is a deterministic
        structural computation (study_design/sample_size/p_value presence),
        not a noisy heuristic accuracy guess, so it needs less smoothing —
        but still enough (3, not 1) that a single anecdotal case report
        can't swing a source's average on its own.

        Caller must only invoke this for auto_registered sources (see
        recompute_source_scores) — verified against live data before this
        landed: applying it to the 16 hand-curated seed sources corrupted
        their expert-set values, because those sources' recent signals come
        largely through RSS table-of-contents feeds (WHO/NEJM/Lancet in
        collect_health_signals.py's RSS_FEEDS), which carry a lot of
        editorial/comment/obituary content misclassified as "anecdotal" or
        generic "observational" by the much weaker title-keyword heuristic
        (_infer_study_design_from_title) rather than PubMed's structured
        PublicationType tag. Concretely: The Lancet's real RSS feed on
        2026-08-09 was 11/15 [Comment]/[Perspectives]/[Correspondence]/
        [Obituary]/[World Report] items (quality 0.1-0.55), which dropped
        its avg_methodology_quality from a curated 0.90 to 0.289 and its
        tier from TIER_1 to TIER_4 — a real, reproduced, wrong result, not
        a hypothetical risk. Auto-registered sources don't have this
        problem: every one is created via the PubMed pathway only (see
        save_item()/_get_or_create_source() — RSS items only ever look up
        an existing hand-curated source by name, never auto-register a new
        one), so their methodology_quality_score inputs always come from
        PubMed's structured PublicationType tag, not the RSS title-keyword
        guess.

        Returns (avg_quality, n) or None if fewer than min_signals available.
        """
        rows = (
            self.supabase.table("health_signals")
            .select("methodology_quality_score")
            .eq("source_id", source_id)
            .eq("suppressed", False)
            .not_.is_("methodology_quality_score", "null")
            .execute().data or []
        )
        if len(rows) < min_signals:
            return None
        scores = [r["methodology_quality_score"] for r in rows]
        return round(sum(scores) / len(scores), 3), len(scores)

    def recompute_source_scores(self, source_id, auto_registered: bool = False):
        update = {}

        validation_rows = (
            self.supabase.table("health_signal_validation")
            .select("is_accurate").eq("source_id", source_id)
            .gt("validated_at", (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
            .execute().data or []
        )
        if len(validation_rows) >= 10:
            accurate = sum(1 for r in validation_rows if r["is_accurate"] is True)
            inaccurate = sum(1 for r in validation_rows if r["is_accurate"] is False)
            total = len(validation_rows)
            update["replication_success_rate"] = round(accurate / total, 2)
            update["retraction_rate"] = round(inaccurate / total, 2)
            update["accuracy_sample_size"] = total

        # Scoped to auto-registered sources only — see
        # recompute_avg_methodology_quality's docstring for why applying
        # this to hand-curated seed sources is actively wrong, not just
        # untested (verified against live data: it corrupted The Lancet's
        # score from a curated TIER_1 to a noise-driven TIER_4).
        if auto_registered:
            mq = self.recompute_avg_methodology_quality(source_id)
            if mq is not None:
                avg_quality, n_quality = mq
                update["avg_methodology_quality"] = avg_quality

        if not update:
            return  # not enough evidence yet on any input — leave existing values alone

        update["accuracy_last_updated"] = datetime.now(timezone.utc).isoformat()

        if not self.dry_run:
            self.supabase.table("health_source_registry").update(update).eq("source_id", source_id).execute()
        logger.info(f"Source {source_id}: {update}")

    def run(self):
        logger.info(f"Starting health source validation{' (DRY RUN)' if self.dry_run else ''}")
        sources = self.supabase.table("health_source_registry").select("source_id, source_name, source_type, auto_registered").execute().data or []
        logger.info(f"Checking {len(sources)} sources")

        for source in sources:
            signals = self.get_unvalidated_signals_for_source(source["source_id"])
            for signal in signals:
                verdict = self.validate_signal_accuracy(signal, source["source_type"])
                self.save_validation(
                    signal["signal_id"], source["source_id"], verdict,
                    "automated", f"Rule-based on study_design/source_type/adverse_event pattern",
                )
            self.recompute_source_scores(source["source_id"], auto_registered=bool(source.get("auto_registered")))

        logger.info(f"Validation complete: {self.validated_count} signals validated, {self.errors} errors")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    HealthSourceValidator(dry_run=args.dry_run).run()


if __name__ == "__main__":
    main()
