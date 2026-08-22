// POST /api/captain-intelligence/insights/[id]/outcome — records what
// actually happened to a Captain Intelligence insight (MSN-0329 Phase 4).
// Mirrors core/platform/insight_outcomes.py's record_outcome() exactly —
// this is that function's only caller, closing the loop the Python side
// was built for but nothing ever invoked.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

const VALID_OUTCOMES = new Set(['useful', 'not_useful', 'incorrect']);

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const outcome = body?.outcome;
  if (!VALID_OUTCOMES.has(outcome)) {
    return NextResponse.json({ error: `outcome must be one of: ${[...VALID_OUTCOMES].join(', ')}` }, { status: 400 });
  }

  try {
    const sb = serviceClient();
    const { error } = await sb
      .from('insight_outcomes')
      .update({
        outcome,
        outcome_note: body?.note ?? null,
        outcome_recorded_at: new Date().toISOString(),
      })
      .eq('id', params.id);
    if (error) throw error;

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error('[captain-intelligence/outcome]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
