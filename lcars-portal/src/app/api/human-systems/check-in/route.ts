// POST /api/human-systems/check-in — governed write for the daily health
// check-in (WORKBENCH-REVIEW.md C4, 2026-07-18). Was a direct browser
// Supabase upsert (medical/check-in/page.tsx) — health_daily_logs' own
// RLS already requires `authenticated`, so this doesn't newly restrict
// who can write; it moves the write server-side and makes the session
// check explicit rather than implicit in RLS, matching the pattern
// api/missions/[id]/approve/route.ts already established.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

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

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase
      .from('health_daily_logs')
      .upsert(payload, { onConflict: 'log_date' });

    if (error) throw error;
    return NextResponse.json({ ok: true });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
