#!/usr/bin/env python3
"""Build the read-only incident snapshot rows the HQ Workbench shows (Intelligence page, Home Needs You, Decisions inbox).

Rows come from ``incident_clustering`` + ``delivery_tiers`` over an event list. ``incident_key`` (= ``incident_id``) is ``tiered_brief.incident_id``, the SAME key
the Telegram alert payload carries (``alert_dispatcher``), so one incident is one entry in Telegram, Home, Decisions and the Intelligence page.

DRY-RUN by default: prints the rows, writes nothing. A write needs ``INCIDENT_SNAPSHOT_WRITE=1`` AND the table to exist (draft migration
``docs/migration-drafts/DRAFT-intelligence-incident-snapshots.sql`` is NOT applied) AND SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. Without all of
these this module never touches the network. Not scheduled by anything here.

Usage: python3 tools/intelligence/publish_incident_snapshot.py --events <tsv|json> [--now ISO]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence import delivery_tiers as dt
from intelligence import incident_clustering as ic
from intelligence import tiered_brief as tb
from tools.intelligence.alert_replay import _ts, load_events

TABLE = "intelligence_incident_snapshots"
WRITE_FLAG = "INCIDENT_SNAPSHOT_WRITE"


def material_exception(inc: ic.Incident, td: dt.TierDecision) -> bool:
    """Material (tier SCHEDULED_BRIEF) and still a current disruption, but not alert-fresh or relevance-demonstrated: it will wait for the
    next brief although it is live. These are the exceptions Home and Decisions surface so they are not lost between alerts and briefs."""
    return td.tier == dt.SCHEDULED_BRIEF and inc.restoration_status in ("ongoing", "partially_restored")


def build_rows(events: list[dict], *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = []
    for inc in ic.cluster_incidents(events, now=now, force=True):
        td = dt.tier_for_incident(inc, now=now)
        times = [r.candidate.published for r in inc.reports if r.candidate.published]
        rows.append({
            "incident_key": tb.incident_id(inc), "headline": inc.decision.headline.title, "tier": td.tier,
            "restoration_status": inc.restoration_status, "n_reports": inc.n_reports, "why": td.reasons[0],
            "reports": [{"relation": r.relation, "event_id": r.event_id, "title": r.candidate.title,
                         "published_at": r.candidate.published.isoformat() if r.candidate.published else None,
                         "restoration": r.restoration} for r in inc.reports],
            "material_exception": material_exception(inc, td), "snapshot_at": now.isoformat(),
            "last_report_at": max(times).isoformat() if times else None})
    return rows


def write_rows(rows: list[dict]) -> bool:
    """Upsert by incident_key. Returns False (no network) unless the write flag, URL and key are all present."""
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if os.getenv(WRITE_FLAG, "").strip().lower() not in ("1", "true", "yes", "on") or not url or not key or not rows:
        return False
    req = urllib.request.Request(f"{url}/rest/v1/{TABLE}?on_conflict=incident_key", data=json.dumps(rows).encode(), method="POST",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "Prefer": "return=minimal,resolution=merge-duplicates"})
    with urllib.request.urlopen(req, timeout=15):  # nosec B310 - SUPABASE_URL env, https
        pass
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--events", required=True)
    ap.add_argument("--now")
    a = ap.parse_args(argv)
    events = load_events(Path(a.events))
    now = _ts(a.now) if a.now else max(_ts(e["collected_at"]) for e in events)
    rows = build_rows(events, now=now)
    wrote = write_rows(rows)
    print(json.dumps({"dry_run": not wrote, "rows": rows}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
