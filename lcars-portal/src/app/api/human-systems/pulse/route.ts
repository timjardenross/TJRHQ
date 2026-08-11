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

  if (typeof payload.log_date !== 'string' || typeof payload.pulse_type !== 'string') {
    return NextResponse.json({ error: 'log_date and pulse_type are required' }, { status: 400 });
  }

  // Never write the decommissioned mood/stress fields, regardless of caller.
  delete payload.mood;
  delete payload.stress;

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase
      .from('recovery_pulses')
      .upsert(payload, { onConflict: 'log_date,pulse_type' });

    if (error) throw error;
    return NextResponse.json({ ok: true });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
