// POST /api/human-systems/check-in — RETIRED (2026-08-22).
//
// The Telegram bot's "MY CAPACITY TODAY" flow (capacity_checkins table,
// /capacity /deepcheck /evening commands) is now the platform's sole manual
// health-data capture mechanism — extending the same consolidation the
// Captain applied to Recovery Pulse (2026-08-10) and then to Recovery
// Pulse's own successor form (2026-08-21/22, see pulse/route.ts). This
// Medical-tab daily check-in was the last manual-capture holdout still
// writing health_daily_logs. Its only caller (medical/check-in/page.tsx)
// is retired alongside it; the route is kept (rather than deleted) purely
// so the URL doesn't 404 unexpectedly for any stale client or bookmark.
//
// ---- Prior history (kept for context) ----
// Governed write for the daily health check-in (WORKBENCH-REVIEW.md C4,
// 2026-07-18) — was a direct browser Supabase upsert, moved server-side
// with an explicit session check, matching api/missions/[id]/approve's
// pattern. The Medical-tab `mood` field was retired within this same route
// on 2026-08-10 (a separate, divergent model from recovery_pulses' own
// already-decommissioned mood/stress fields).

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
