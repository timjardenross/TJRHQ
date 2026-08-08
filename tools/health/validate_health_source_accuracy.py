#!/usr/bin/env python3
"""
Daily Health Source Accuracy Validation Job

Mirrors tools/intelligence/validate_source_accuracy.py's structure and its
2026-08-08 fix (real columns, not a nonexistent field) — built this way from
the start rather than repeating that mistake for the health domain.

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

    def recompute_source_scores(self, source_id):
        rows = (
            self.supabase.table("health_signal_validation")
            .select("is_accurate").eq("source_id", source_id)
            .gt("validated_at", (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
            .execute().data or []
        )
        if len(rows) < 10:
            return  # not enough evidence yet — leave existing values alone

        accurate = sum(1 for r in rows if r["is_accurate"] is True)
        inaccurate = sum(1 for r in rows if r["is_accurate"] is False)
        total = len(rows)
        replication_success_rate = round(accurate / total, 2)
        retraction_rate = round(inaccurate / total, 2)

        if not self.dry_run:
            self.supabase.table("health_source_registry").update({
                "replication_success_rate": replication_success_rate,
                "retraction_rate": retraction_rate,
                "accuracy_sample_size": total,
                "accuracy_last_updated": datetime.now(timezone.utc).isoformat(),
            }).eq("source_id", source_id).execute()
        logger.info(f"Source {source_id}: replication_success_rate={replication_success_rate}, "
                    f"retraction_rate={retraction_rate}, sample={total}")

    def run(self):
        logger.info(f"Starting health source validation{' (DRY RUN)' if self.dry_run else ''}")
        sources = self.supabase.table("health_source_registry").select("source_id, source_name, source_type").execute().data or []
        logger.info(f"Checking {len(sources)} sources")

        for source in sources:
            signals = self.get_unvalidated_signals_for_source(source["source_id"])
            for signal in signals:
                verdict = self.validate_signal_accuracy(signal, source["source_type"])
                self.save_validation(
                    signal["signal_id"], source["source_id"], verdict,
                    "automated", f"Rule-based on study_design/source_type/adverse_event pattern",
                )
            self.recompute_source_scores(source["source_id"])

        logger.info(f"Validation complete: {self.validated_count} signals validated, {self.errors} errors")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    HealthSourceValidator(dry_run=args.dry_run).run()


if __name__ == "__main__":
    main()
