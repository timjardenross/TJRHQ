// POST /api/human-systems/check-in — governed write for the daily health
// check-in (WORKBENCH-REVIEW.md C4, 2026-07-18). Was a direct browser
// Supabase upsert (medical/check-in/page.tsx) — health_daily_logs' own
// RLS already requires `authenticated`, so this doesn't newly restrict
// who can write; it moves the write server-side and makes the session
// check explicit rather than implicit in RLS, matching the pattern
// api/missions/[id]/approve/route.ts already established.
//
// Manual capture retirement (Captain directive, 2026-08-10 — see
// .claude/skills/bot-reviews/fixes-2026-08-09/manual-capture-retirement.md):
// Recovery Pulse (Telegram XO bot) is now the platform's only manual
// health-data capture mechanism. This Medical-tab check-in's own `mood`
// field (a separate, structurally-unrelated model from recovery_pulses'
// already-decommissioned mood/stress fields — see pulse/route.ts) is
// retired here too. Mirrors that route's exact defense-in-depth pattern:
// the UI no longer sends `mood`, and this strips it server-side regardless
// of caller. Historical mood rows are untouched; this only blocks new writes.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { recordHeartbeatServerSide } from '@/lib/heartbeat';

export async function POST(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  if (typeof payload.log_date !== 'string' || !payload.log_date) {
    return NextResponse.json({ error: 'log_date is required' }, { status: 400 });
  }

  // Never write the retired manual mood field, regardless of caller.
  delete payload.mood;

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase
      .from('health_daily_logs')
      .upsert(payload, { onConflict: 'log_date' });

    if (error) throw error;

    // Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
    // slack-bot-heartbeat-investigation.md): health_daily_logs's real write
    // is this route (governed daily check-in, WORKBENCH-REVIEW.md C4) — the
    // domain_registry row had zero heartbeat calls anywhere, Python or TS,
    // since the only prior writer (platform-runtime/commands/health_check.py,
    // Slack) has been dead since starfleet-slack-bot.service was disabled.
    // Best-effort, non-blocking — mirrors captains-log/heartbeat/route.ts's
    // just-added pattern but inline, since this route already is the
    // server-side write itself rather than a browser-upsert relay.
    void recordHeartbeatServerSide({
      domainKey: 'health_daily_logs',
      status: 'ok',
      detail: `log_date=${payload.log_date}`,
    });

    return NextResponse.json({ ok: true });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
