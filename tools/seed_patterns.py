"""Standalone seed script for the Operational Pattern Library.

Seeds the 8 initial patterns defined in core/platform/operational_pattern_library.py
and proposes the Dual-Write Production Adoption pattern from MSN-0210K's close-out.

Usage:
    python tools/seed_patterns.py

Both calls are idempotent (upsert on pattern_name) — safe to run multiple times.
Requires Supabase connectivity and the `operational_patterns` table to exist.
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("seed-patterns")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "core", "platform"))

from operational_pattern_library import (  # noqa: E402
    propose_dual_write_adoption_pattern,
    seed_initial_patterns,
)


def main() -> None:
    log.info("Seeding initial Operational Pattern Library entries...")
    seeded_count = seed_initial_patterns()
    log.info("seed_initial_patterns(): %d pattern(s) written", seeded_count)

    log.info("Proposing Dual-Write Production Adoption pattern (MSN-0210K close-out)...")
    dual_write_ok = propose_dual_write_adoption_pattern()
    log.info("propose_dual_write_adoption_pattern(): %s", "written" if dual_write_ok else "skipped/failed")

    total = seeded_count + (1 if dual_write_ok else 0)
    print(f"Patterns seeded: {total}")


if __name__ == "__main__":
    main()
