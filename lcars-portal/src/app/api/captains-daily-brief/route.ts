// GET /api/captains-daily-brief — the Captain's actual daily brief
// (morning/eod/weekly), written by intelligence/captains_brief.py's 07:00
// AEST cron (intelligence/scheduler.py's captains_morning_brief job) and
// the XO Telegram bot's /brief command.
//
// Deliberately separate from /api/briefs (intelligence_briefs — the ORI
// cybersecurity/geopolitical resilience-brief archive, a different
// feature entirely). TodaysBriefPanel.tsx used to read /api/briefs, which
// meant Captain's Chair's "Executive Brief" card was actually showing ORI
// briefs — a pipeline that runs fortnightly (intelligence/scheduler.py's
// or_intelligence_brief job), not daily, so it usually had nothing to
// show "today" regardless of whether the real daily brief had generated.
// captains_daily_briefs has no approval_status/workflow column at all
// (migration 0033/0050 — read-only historical log), so there's no
// publish-gate to apply here.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const { data, error } = await sb
      .from('captains_daily_briefs')
      .select('id,brief_type,brief_date,generated_at,brief_text,signals_count,health_snapshot')
      .order('generated_at', { ascending: false })
      .limit(20);
    if (error) throw error;

    return NextResponse.json({ briefs: data ?? [] });
  } catch (err) {
    console.error('[captains-daily-brief] read failed:', err);
    return NextResponse.json({ error: 'captains_daily_brief_read_failed' }, { status: 500 });
  }
}
