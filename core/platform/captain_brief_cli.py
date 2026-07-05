"""Captain Brief CLI (MSN-0315 Phase 1C) — the first live consumer bridge.

`CaptainBriefDocument` (MSN-0313) is pure Python with no HTTP surface. This
is a thin, dependency-free entry point so a non-Python caller (lcars-portal's
Next.js API route, via subprocess) can get one as JSON on stdout. No new
service to run/monitor — this reuses the existing subprocess-call pattern
already present elsewhere in this repo rather than standing up a persistent
API for a single read-only object.

Usage: python3 -m core.platform.captain_brief_cli [--limit N]
Prints one JSON object (the CaptainBriefDocument, dataclasses flattened) to
stdout. Never raises past this point — poll_events() itself already returns
[] on any Supabase error, so a document with all-empty sections is the
correct honest output, not a crash.
"""

from __future__ import annotations

import argparse
import dataclasses
import json

from core.platform.captain_brief_orchestrator import assemble_captain_brief_document
from core.platform.event_bus import poll_events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    events = poll_events(limit=args.limit)
    doc = assemble_captain_brief_document(events)
    print(json.dumps(dataclasses.asdict(doc), default=str))


if __name__ == "__main__":
    main()
