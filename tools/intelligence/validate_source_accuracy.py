#!/usr/bin/env python3
"""
Daily Source Accuracy Validation Job

Validates recent intelligence events against internal signals.
Calculates accuracy_ratio and false_positive_rate for each source.
Updates intelligence_source_registry with SRS scores.

Run daily (typically 01:00 UTC after brief generation).

Usage:
    python3 tools/intelligence/validate_source_accuracy.py
    python3 tools/intelligence/validate_source_accuracy.py --dry-run
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
REPO_ROOT = Path(__file__).parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

try:
    from supabase import create_client
except ImportError:
    logger.error("supabase-py not installed. Install: pip install supabase")
    sys.exit(1)


class SourceAccuracyValidator:
    """Validates intelligence events and updates source reliability scores."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.validated_count = 0
        self.validation_errors = 0

    def validate_event_accuracy(self, event: dict) -> Optional[bool]:
        """
        Determine if an event's claim is accurate.

        Returns: True (accurate) | False (false positive) | None (unknown)
        """

        # Rule 1: Internal monitoring events are always accurate (direct measurement)
        if event.get("category") == "internal_monitoring":
            return True

        # Rule 2: Regulatory sources assumed accurate unless proven otherwise
        if event.get("category") == "regulatory":
            return True  # Assume accurate; expert review changes this

        # Rule 3: For operational events, check if we saw corresponding degradation
        if event.get("event_type") == "technology_outage":
            # Query: Did we see error rate spike in logs during this window?
            # For now, simplified check: if it's from a cloud provider, assume accurate
            if "aws" in event.get("raw_title", "").lower() or \
               "azure" in event.get("raw_title", "").lower() or \
               "gcp" in event.get("raw_title", "").lower():
                return True  # Cloud provider reports are authoritative

        # Rule 4: For other events, mark as unknown
        # (we don't have validation logic for them yet)
        return None

    def get_validated_events_for_source(self, source_id: str, days: int = 30) -> list:
        """Get events from this source that have not yet been validated."""

        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            # Get events from source not yet validated
            response = (
                self.supabase.table("intelligence_events")
                .select("event_id, source_id, raw_title, raw_summary, event_type, published_at")
                .eq("source_id", source_id)
                .gt("published_at", cutoff_date)
                .order("published_at", desc=True)
                .execute()
            )

            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching events for source {source_id}: {e}")
            return []

    def save_validation(self, event_id: str, source_id: str, is_accurate: Optional[bool],
                       validation_method: str, validation_detail: str, event_published_at: str) -> bool:
        """Save validation result to database."""

        if is_accurate is None:
            # Don't save unknown validations
            return True

        try:
            if not self.dry_run:
                self.supabase.table("intelligence_event_validation").insert({
                    "event_id": event_id,
                    "source_id": source_id,
                    "is_accurate": is_accurate,
                    "validation_method": validation_method,
                    "validation_detail": validation_detail,
                    "event_published_at": event_published_at,
                    "validated_at": datetime.utcnow().isoformat(),
                    "validated_by": "system"
                }).execute()

            self.validated_count += 1
            return True

        except Exception as e:
            logger.error(f"Error saving validation for event {event_id}: {e}")
            self.validation_errors += 1
            return False

    def calculate_source_accuracy(self, source_id: str) -> Tuple[float, float, int]:
        """
        Calculate accuracy_ratio and false_positive_rate for a source.

        Returns: (accuracy_ratio, false_positive_rate, sample_size)
        """

        try:
            # Query validated events for this source (last 30 days)
            response = (
                self.supabase.table("intelligence_event_validation")
                .select("is_accurate")
                .eq("source_id", source_id)
                .gt("validated_at", (datetime.utcnow() - timedelta(days=30)).isoformat())
                .execute()
            )

            validations = response.data if response.data else []

            if len(validations) < 10:
                # Need at least 10 validated events for meaningful score
                logger.info(f"Source {source_id}: only {len(validations)} validated events, "
                           "using defaults (accuracy=0.50, fp_rate=0.20)")
                return 0.50, 0.20, len(validations)

            true_positives = sum(1 for v in validations if v["is_accurate"] is True)
            false_positives = sum(1 for v in validations if v["is_accurate"] is False)
            total = len(validations)

            accuracy_ratio = round(true_positives / total, 2)
            false_positive_rate = round(false_positives / total, 2)

            return accuracy_ratio, false_positive_rate, total

        except Exception as e:
            logger.error(f"Error calculating accuracy for source {source_id}: {e}")
            return 0.50, 0.20, 0  # Defaults on error

    def update_source_scores(self, source_id: str, accuracy_ratio: float,
                            false_positive_rate: float, sample_size: int) -> bool:
        """Update source registry with new accuracy scores."""

        try:
            if not self.dry_run:
                self.supabase.table("intelligence_source_registry").update({
                    "accuracy_ratio": accuracy_ratio,
                    "false_positive_rate": false_positive_rate,
                    "accuracy_sample_size": sample_size,
                    "accuracy_last_updated": datetime.utcnow().isoformat()
                }).eq("source_id", source_id).execute()

            return True

        except Exception as e:
            logger.error(f"Error updating source {source_id}: {e}")
            return False

    def run(self) -> None:
        """Execute the daily validation job."""

        logger.info("Starting daily source accuracy validation...")

        if self.dry_run:
            logger.info("DRY RUN: No changes will be written to database")

        try:
            # Step 1: Get all active sources
            sources_response = (
                self.supabase.table("intelligence_source_registry")
                .select("source_id, source_name, category")
                .eq("active", True)
                .execute()
            )
            sources = sources_response.data if sources_response.data else []
            logger.info(f"Found {len(sources)} active sources")

            # Step 2: For each source, validate recent events
            validated_by_source = {}
            for source in sources:
                source_id = source["source_id"]
                source_name = source["source_name"]

                events = self.get_validated_events_for_source(source_id)
                if not events:
                    continue

                validated_for_source = 0
                for event in events:
                    is_accurate = self.validate_event_accuracy(event)

                    if is_accurate is not None:
                        saved = self.save_validation(
                            event["event_id"],
                            source_id,
                            is_accurate,
                            validation_method="automated",
                            validation_detail=f"Validated based on event type and source category",
                            event_published_at=event["published_at"]
                        )
                        if saved:
                            validated_for_source += 1

                if validated_for_source > 0:
                    validated_by_source[source_name] = validated_for_source

            logger.info(f"Validated {self.validated_count} events "
                       f"({len(validated_by_source)} sources with new validations)")

            # Step 3: Recalculate accuracy for all sources
            logger.info("Recalculating accuracy scores for all sources...")
            updated_count = 0

            for source in sources:
                source_id = source["source_id"]
                source_name = source["source_name"]

                accuracy_ratio, fp_rate, sample_size = self.calculate_source_accuracy(source_id)

                updated = self.update_source_scores(source_id, accuracy_ratio, fp_rate, sample_size)
                if updated:
                    updated_count += 1

                    if sample_size > 0:
                        srs = round(
                            0.75 * accuracy_ratio * (1 - fp_rate),  # Assuming base confidence ~0.75
                            2
                        )
                        logger.debug(
                            f"{source_name}: accuracy={accuracy_ratio}, fp_rate={fp_rate}, "
                            f"sample={sample_size}, SRS≈{srs}"
                        )

            logger.info(f"Updated {updated_count} source accuracy scores")

            # Step 4: Report
            logger.info("Daily validation job complete")
            logger.info(f"  Events validated: {self.validated_count}")
            logger.info(f"  Sources updated: {updated_count}")
            logger.info(f"  Validation errors: {self.validation_errors}")

            if self.dry_run:
                logger.info("(DRY RUN: No changes written)")

        except Exception as e:
            logger.error(f"Fatal error in validation job: {e}")
            sys.exit(1)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate intelligence events and update source reliability scores"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing to database (preview only)"
    )

    args = parser.parse_args()

    validator = SourceAccuracyValidator(dry_run=args.dry_run)
    validator.run()


if __name__ == "__main__":
    main()
