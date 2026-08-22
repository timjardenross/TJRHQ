// POST /api/human-systems/pulse — RETIRED (2026-08-22).
//
// The Telegram bot's "MY CAPACITY TODAY" flow (capacity_checkins table,
// /capacity /deepcheck /evening commands) replaced recovery_pulses as the
// canonical health-capacity capture path on 2026-08-21 and is now the SOLE
// capture path for this data — extending the same consolidation principle
// the Captain applied to Recovery Pulse itself on 2026-08-10 (see this
// route's prior history below). This endpoint's only caller
// (medical/pulse/page.tsx) has been retired alongside it; the route is kept
// (rather than deleted) purely so the URL doesn't 404 unexpectedly for any
// stale client or bookmark.
//
// ---- Prior history (kept for context) ----
// POST /api/human-systems/pulse — governed write for a recovery pulse
// (WORKBENCH-REVIEW.md C4, 2026-07-18). Was a direct browser Supabase
// upsert (medical/pulse/page.tsx). recovery_pulses' own RLS already
// requires `authenticated` for INSERT, so this doesn't newly restrict
// who can write; it moves the write server-side with an explicit session
// check, matching api/missions/[id]/approve/route.ts's pattern.
//
// Recovery Pulse decommission (Captain directive, 2026-08-10): the Telegram
// bot's energy/nervous_system/body_signals/day_win model is now canonical;
// mood/stress were an alternate, divergent data model written only by this
// route's one caller (medical/pulse/page.tsx, now itself repointed to the
// canonical fields). `mood`/`stress` are stripped here too — defense in
// depth so this route can never become a re-entry point for the divergent
// path even if called directly. Historical mood/stress rows are untouched;
// this only blocks new writes.

import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';

export async function POST(_request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  return NextResponse.json(
    { error: 'This endpoint is retired. Log capacity check-ins via the XO Telegram bot (/capacity command) instead.' },
    { status: 410 }
  );
}
