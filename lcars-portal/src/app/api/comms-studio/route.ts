// POST /api/comms-studio — Executive Communications Studio: saves an
// assembled document (lib/commsStudio.ts) as a new comms_content draft.
//
// Reuses the exact same table and lifecycle the public-content pipeline
// already uses, rather than a parallel store — migration 0027's own
// comment already anticipates this: comms_content is "ONE consolidated,
// additive content-lifecycle store", and its classification column already
// distinguishes 'internal_only' from 'publishable'. This route only
// creates the row at status='draft'; the existing /comms page and its
// governed advance/route.ts (including the publish-approval gate closed by
// this same mission) handle everything from there on.
//
// Session check added 2026-07-18 (WORKBENCH-REVIEW.md H1): this file
// previously argued a session check wasn't needed since nothing can leave
// draft/review without separate governance — true for privilege escalation,
// but an unauthenticated insert is still real write abuse (arbitrary junk
// rows an actual Captain review queue then has to see). Gating costs
// nothing here; the "no immediate external effect" argument justifies
// skipping the *governance* gate, not skipping auth entirely.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

const VALID_TYPES = ['executive_brief', 'decision_brief', 'mission_report'];

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { type, refId, title, body, evidence } = await req.json();

    if (!VALID_TYPES.includes(type)) {
      return NextResponse.json({ error: `Unsupported document type: ${type}` }, { status: 400 });
    }
    if (typeof title !== 'string' || !title.trim() || typeof body !== 'string' || !body.trim()) {
      return NextResponse.json({ error: 'title and body are required' }, { status: 400 });
    }

    const sb = serviceClient();
    const { data, error } = await sb
      .from('comms_content')
      .insert({
        title: title.slice(0, 200),
        body,
        classification: 'internal_only',
        status: 'draft',
        source_kind: type,
        source_ref: typeof refId === 'string' && refId ? refId : null,
        format: type,
        notes: Array.isArray(evidence) && evidence.length > 0 ? `Evidence: ${evidence.join('; ')}` : null,
      })
      .select('id')
      .single();
    if (error) throw error;

    return NextResponse.json({ id: data.id });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
