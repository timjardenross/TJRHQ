// POST /api/human-systems/pulse — governed write for a recovery pulse
// (WORKBENCH-REVIEW.md C4, 2026-07-18). Was a direct browser Supabase
// upsert (medical/pulse/page.tsx). recovery_pulses' own RLS already
// requires `authenticated` for INSERT, so this doesn't newly restrict
// who can write; it moves the write server-side with an explicit session
// check, matching api/missions/[id]/approve/route.ts's pattern.

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
