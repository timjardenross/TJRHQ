#!/usr/bin/env python3
"""
Health Signal Score Recompute — daily retroactive refresh.

Without this, a health_signal's confidence_level/rank_score are frozen at
whatever they were computed as when first collected. If its source later
crosses a tier boundary (via validate_health_source_accuracy.py), older
signals from that source never reflect the improved/worsened trust —
exactly the gap disclosed when the ingestion pipeline shipped.

Mirrors tools/intelligence/recompute_signal_scores.py's shape: paginated
fetch (PostgREST's 1000-row default cap bit that script once — not
repeating it here), recompute confidence_level + rank_score for every
non-suppressed signal from current source tier, batch-write.

Usage:
    python3 tools/health/recompute_health_signal_scores.py [--dry-run]
"""

import os
import sys
import logging
import argparse
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

TIER_SCORE = {"TIER_1": 0.95, "TIER_2": 0.75, "TIER_3": 0.55, "TIER_4": 0.30}


def confidence_level(tier, quality_score):
    if tier == "TIER_1" and quality_score >= 0.70:
        return "HIGH"
    if tier == "TIER_1":
        return "MEDIUM"
    if tier == "TIER_2" and quality_score >= 0.60:
        return "MEDIUM"
    if tier == "TIER_2":
        return "LOW"
    if tier == "TIER_3" and quality_score >= 0.60:
        return "LOW"
    if tier in ("TIER_3", "TIER_4"):
        return "LOW"
    return "UNKNOWN"


class HealthSignalRecomputer:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.stats = {"recomputed": 0, "confidence_changed": 0, "rank_changed": 0, "errors": 0}

    def _fetch_all(self, build_query, page_size=1000):
        """See tools/intelligence/recompute_signal_scores.py's identical
        helper and its docstring — PostgREST caps unpaginated responses at
        1000 rows, which silently truncated that script's first backfill run."""
        rows, offset = [], 0
        while True:
            resp = build_query().range(offset, offset + page_size - 1).execute()
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return rows

    def run(self):
        logger.info(f"Starting health signal recompute{' (DRY RUN)' if self.dry_run else ''}")

        signals = self._fetch_all(lambda: (
            self.supabase.table("health_signals")
            .select("signal_id, confidence_level, rank_score, methodology_quality_score, source_id, "
                    "health_source_registry(reliability_tier)")
            .eq("suppressed", False)
        ))
        logger.info(f"Recomputing {len(signals)} signals")

        for s in signals:
            tier = (s.get("health_source_registry") or {}).get("reliability_tier")
            quality = s.get("methodology_quality_score")
            if tier is None or quality is None:
                continue

            new_confidence = confidence_level(tier, quality)
            new_rank = round(TIER_SCORE.get(tier, 0.30) * quality * 100, 2)

            if new_confidence == s.get("confidence_level") and abs(new_rank - float(s.get("rank_score") or 0)) < 0.01:
                continue

            if new_confidence != s.get("confidence_level"):
                self.stats["confidence_changed"] += 1
            if abs(new_rank - float(s.get("rank_score") or 0)) >= 0.01:
                self.stats["rank_changed"] += 1

            if not self.dry_run:
                try:
                    self.supabase.table("health_signals").update(
                        {"confidence_level": new_confidence, "rank_score": new_rank}
                    ).eq("signal_id", s["signal_id"]).execute()
                except Exception as e:
                    logger.error(f"Update failed for {s['signal_id']}: {e}")
                    self.stats["errors"] += 1
                    continue
            self.stats["recomputed"] += 1

        logger.info(f"Recompute complete: {self.stats}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    HealthSignalRecomputer(dry_run=args.dry_run).run()


if __name__ == "__main__":
    main()
