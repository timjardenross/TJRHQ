// POST /api/human-systems/readiness/exercise-log — governed per-step write
// during a workout session (WORKBENCH-REVIEW.md C4, 2026-07-18). Was a
// direct browser Supabase insert (readiness/session/[id]/page.tsx's
// logCurrentStep()). physical_workout_exercise_logs' own RLS already
// requires `authenticated` (tightened from role=public the same session
// this route was built - see governance/code-review-attestations.txt),
// so this doesn't newly restrict who can write; it moves the write
// server-side with an explicit session check.

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

  if (typeof payload.workout_session_id !== 'string' || typeof payload.exercise_id !== 'string') {
    return NextResponse.json({ error: 'workout_session_id and exercise_id are required' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.from('physical_workout_exercise_logs').insert(payload);

    if (error) throw error;
    return NextResponse.json({ ok: true });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
