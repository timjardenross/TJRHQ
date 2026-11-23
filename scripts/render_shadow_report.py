"""Shadow run: render the Weekly Intelligence & Decision Brief from an exported JSON file.

Reads a local file and writes a local file (or stdout). It has no network access, no database
access, no delivery path and no scheduler; nothing it produces is sent anywhere.

    python3 scripts/render_shadow_report.py export.json [--out shadow_report.txt] [--week "17-23 Nov 2026"]

Export format: {"events": [{"id","title","source","collected_at","geography"}...],
                "universe": {"usable": N, "au_events": N, ...},
                "health": {"total": N, "registrations": N, "other": N, "leads": [...]},
                "capacity": {"source": "...", "entries": [...]},
                "db_snapshots": [{"date": "YYYY-MM-DD", "size_mb": N}, ...],
                "now": "ISO timestamp"}
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import intelligence.weekly_evidence as we

BANNER = "SHADOW OUTPUT — generated offline from a local export; not sent, not scheduled, not a published report.\n\n"


def render(export: dict, week: str) -> str:
    now = datetime.fromisoformat(export["now"].replace("Z", "+00:00")) if export.get("now") else datetime.now(timezone.utc)
    evidence = we.build_weekly_evidence(
        events=export.get("events", []), universe=export.get("universe", {}),
        health_records=[], capacity=export.get("capacity", {"entries": []}),
        db_snapshots=export.get("db_snapshots", []), now=now)
    health = export.get("health")
    return BANNER + we.render_intelligence_brief(
        evidence, week_label=week, health=health, health_leads=(health or {}).get("leads"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("export")
    ap.add_argument("--out")
    ap.add_argument("--week", default="(unspecified week)")
    a = ap.parse_args(argv)
    text = render(json.loads(Path(a.export).read_text(encoding="utf-8")), a.week)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
