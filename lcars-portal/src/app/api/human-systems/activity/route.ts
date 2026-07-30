// POST /api/human-systems/activity — governed write for a logged activity
// (WORKBENCH-REVIEW.md C4, 2026-07-18). Was a direct browser Supabase
// insert (medical/log-activity/page.tsx). activity_logs' own RLS already
// requires `authenticated`, so this doesn't newly restrict who can write;
// it moves the write server-side with an explicit session check.

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

  if (typeof payload.log_date !== 'string' || typeof payload.activity_type !== 'string') {
    return NextResponse.json({ error: 'log_date and activity_type are required' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.from('activity_logs').insert(payload);

    if (error) throw error;
    return NextResponse.json({ ok: true });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
