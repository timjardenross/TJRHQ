#!/usr/bin/env python3
"""CLI entry point for the Daily Operating Cycle (USS-TJR-MSN-0210L/M
Officer Execution Convergence).

platform-runtime/lib/daily_ops_cycle.py's run_daily_cycle() is the live,
fully-implemented executive-staff orchestrator (EXEC-001 through EXEC-010A —
Human Systems -> Strategic Planning -> ORI -> Engineering -> Communications
-> Number One -> Investigation/Learning/Strategic/Program/Portfolio/
Enterprise-Architecture/Investment reviews -> Autonomous Officers ->
Exception Router -> Captain Brief), correctly wired end-to-end and covered
by tests, but until this script existed it had zero callers anywhere in the
repo — confirmed via repo-wide grep and via core/coordination/
execution_engine.py's own module docstring ("...run_daily_cycle(), has zero
callers of its own anywhere..."). This script is that missing entry point,
so deploy/daily-ops-cycle.service + .timer have something real to invoke.

Gathers the same two inputs run_daily_cycle() needs, reusing already-live
data paths rather than inventing a new one:
  - missions:       core/context-assembly/context_service.py's
                     _load_live_missions_for_number_one() — the file corpus
                     overlaid with live Supabase status/priority, the same
                     mission list Number One's own HTTP brief endpoint
                     (context_service.py's http_number_one_brief) uses.
  - capacity_entry:  today's most recent capacity_checkins row
                     (checkin_type=capacity), fetched the same way
                     core/coordination/command_bus.py's _capacity_status()
                     and platform-runtime/lib/daily_ops_cycle.py's own
                     _step_ori() already query Supabase (CommanderSupabaseClient,
                     tools/supabase/client.py) — capacity_checkins is the
                     sole capture path per the 2026-08-22 MY CAPACITY TODAY
                     migration.

Prints the resulting Captain brief to stdout, which systemd's
StandardOutput=journal (deploy/daily-ops-cycle.service) captures. This
script deliberately does NOT invent a new distribution channel for the
brief (Telegram/Slack/etc posting is core/notifications/ territory, out of
scope for this change) — that remains a follow-up decision for whoever owns
brief distribution.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    str(REPO_ROOT),
    str(REPO_ROOT / "core" / "context-assembly"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("daily-ops-cycle-runner")


def _load_missions() -> list[dict[str, Any]]:
    """Live mission list, same source as Number One's own HTTP brief."""
    try:
        import context_service  # core/context-assembly/context_service.py

        return context_service._load_live_missions_for_number_one()
    except Exception as exc:  # noqa: BLE001 - non-blocking: run_daily_cycle()'s own
        # steps already degrade gracefully against an empty/partial mission list.
        log.warning("Could not load live missions — proceeding with empty list: %s", exc)
        return []


def _load_capacity_entry() -> dict[str, Any] | None:
    """Today's most recent capacity_checkins row, or None (mapped to
    "Unknown" status by capacity_zone_from_checkin() downstream)."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not (client.is_enabled() and client.raw_client):
            log.warning("Supabase client not enabled — capacity_entry will be None")
            return None

        today = datetime.now(timezone.utc).astimezone().date().isoformat()
        res = (
            client.raw_client.table("capacity_checkins")
            .select("*")
            .eq("log_date", today)
            .eq("checkin_type", "capacity")
            .order("captured_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001 - non-blocking: _step_human_systems()
        # already tolerates capacity_entry=None (falls back to "Unknown").
        log.warning("Could not load today's capacity_checkins row — capacity_entry will be None: %s", exc)
        return None


def main() -> int:
    from platform_runtime.lib.daily_ops_cycle import run_daily_cycle

    missions = _load_missions()
    capacity_entry = _load_capacity_entry()

    log.info(
        "Starting daily ops cycle: %d missions, capacity_entry=%s",
        len(missions), "present" if capacity_entry else "none",
    )

    brief = run_daily_cycle(missions, capacity_entry)

    print(brief)
    log.info("Daily ops cycle complete (%d chars of brief).", len(brief))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
