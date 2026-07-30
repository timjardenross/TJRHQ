"""Captain Brief CLI (MSN-0315 Phase 1C) — the first live consumer bridge.

`CaptainBriefDocument` (MSN-0313) is pure Python with no HTTP surface. This
is a thin, dependency-free entry point so a non-Python caller (lcars-portal's
Next.js API route, via subprocess) can get one as JSON on stdout. No new
service to run/monitor — this reuses the existing subprocess-call pattern
already present elsewhere in this repo rather than standing up a persistent
API for a single read-only object.

Usage: python3 -m core.platform.captain_brief_cli [--limit N] [--evolved]
Prints one JSON object (the CaptainBriefDocument, dataclasses flattened) to
stdout. Never raises past this point — poll_events() itself already returns
[] on any Supabase error, so a document with all-empty sections is the
correct honest output, not a crash.

--evolved (MSN-0329 Phase 5): calls assemble_evolved_captain_brief()
instead of the base assemble_captain_brief_document() — runs the full
Understanding/Insight/Reasoning pipeline, including real HTTP calls to
the model router. Real synthesis is slow on this platform's hardware
(observed: 50-180+ seconds per insight, MSN-0329 Phase 3) — callers
using this flag must set a generous timeout, not the ~15s appropriate
for the base (pure, no-I/O) mode. Every insight generated this way is
already persisted to insight_outcomes by assemble_evolved_captain_brief()
itself — this CLI does not need its own separate persistence step.
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
    parser.add_argument("--evolved", action="store_true",
                        help="Run the full Understanding/Insight/Reasoning pipeline (slow — real LLM calls).")
    args = parser.parse_args()

    events = poll_events(limit=args.limit)
    if args.evolved:
        from core.platform.captain_brief_evolution import assemble_evolved_captain_brief
        doc = assemble_evolved_captain_brief(events)
    else:
        doc = assemble_captain_brief_document(events)
    print(json.dumps(dataclasses.asdict(doc), default=str))


if __name__ == "__main__":
    main()
