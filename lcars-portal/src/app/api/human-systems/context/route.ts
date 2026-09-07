// Human Systems — Assessed Context (Human Execution Loop mission, brief §6).
//
// The one small, stable, fresh/stale-aware read boundary other workbenches
// consume instead of querying capacity_checkins or re-deriving posture
// themselves (brief §39/§40). See assessed-context.ts for the composition
// rules and the sensitivity boundary (§48) this shape already respects.
//
// Deliberately separate from the main /api/human-systems route (which
// returns the full Recovery/Medical payload for the workbench's own UI) —
// same split rationale trends/route.ts documents for its own separation.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { getAssessedContext } from '../assessed-context';

export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const sb = await createSupabaseServerClient();
    const context = await getAssessedContext(sb);
    return NextResponse.json(context);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to build assessed context', detail: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
