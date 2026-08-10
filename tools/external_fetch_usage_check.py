#!/usr/bin/env python3
"""External fetch-path budget check (Firecrawl / Bright Data hard-cap
circuit breaker, 2026-08-10).

Read-only companion to intelligence/ingestion/external_fetch_budget.py —
same "check without mutating" philosophy as tools/registry_staleness_check.py
and tools/id_counter_drift_check.py. Shows each provider's current-billing-
cycle usage against its safe ceiling and real vendor cap, without
incrementing anything (uses external_fetch_budget.current_usage(), never
check_and_increment()).

Usage:
    python3 tools/external_fetch_usage_check.py [provider ...]

With no arguments, checks all known providers (firecrawl, brightdata).
Exit code 0 if every checked provider is under its safe ceiling and the
usage read succeeded, 1 if any provider is at/over its ceiling or its
usage could not be read (a read failure is reported as a problem, never
silently shown as "0 used").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence.ingestion import external_fetch_budget  # noqa: E402


def check(providers: list[str]) -> int:
    exit_code = 0
    print(f"{'Provider':<12}{'Cycle':<24}{'Used':<8}{'Ceiling':<10}{'RealCap':<9}{'Headroom':<10}{'%':<8}")

    for provider in providers:
        try:
            usage = external_fetch_budget.current_usage(provider)
        except Exception as exc:
            print(f"{provider:<12}COULD NOT READ USAGE: {exc}")
            exit_code = 1
            continue

        cycle = f"{usage['billing_cycle_start']}..{usage['billing_cycle_end']}"
        pct = usage["pct_of_ceiling"]
        print(
            f"{provider:<12}{cycle:<24}{usage['call_count']:<8}{usage['ceiling']:<10}"
            f"{usage['cap']:<9}{usage['headroom']:<10}{pct if pct is not None else '?':<8}"
        )

        if usage["headroom"] <= 0:
            print(f"  -> AT OR OVER SAFE CEILING — {provider} calls are currently being refused.")
            exit_code = 1
        elif pct is not None and pct >= 90:
            print(f"  -> approaching ceiling ({pct}% of {usage['ceiling']}).")

    return exit_code


def main() -> None:
    providers = sys.argv[1:] or sorted(external_fetch_budget.PROVIDERS)
    unknown = [p for p in providers if p not in external_fetch_budget.PROVIDERS]
    if unknown:
        print(f"Unknown provider(s): {unknown} (known: {sorted(external_fetch_budget.PROVIDERS)})")
        sys.exit(2)
    sys.exit(check(providers))


if __name__ == "__main__":
    main()
