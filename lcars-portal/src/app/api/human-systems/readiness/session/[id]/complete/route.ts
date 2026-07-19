// POST /api/human-systems/readiness/session/[id]/complete — governed write
// for finishing a workout session (WORKBENCH-REVIEW.md C4, 2026-07-18).
// Was a direct browser Supabase update (readiness/session/[id]/page.tsx's
// handleSubmitCompletion()). physical_workout_sessions' own RLS already
// requires `authenticated` (tightened from role=public the same session
// this route was built - see governance/code-review-attestations.txt),
// so this doesn't newly restrict who can write; it moves the write
// server-side with an explicit session check. Session id comes from the
// URL param, not the body, so a caller can't redirect the update at an
// arbitrary row via a crafted payload.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Session ID required' }, { status: 400 });
  }

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

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase
      .from('physical_workout_sessions')
      .update(payload)
      .eq('id', id);

    if (error) throw error;
    return NextResponse.json({ ok: true });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
