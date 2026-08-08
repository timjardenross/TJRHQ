// POST /api/comms/[id]/advance — advance a comms_content item through the pipeline.
// Body: { trigger: 'officer_drafted' | 'officer_submitted' | 'captain_approved' | 'captain_confirmed' | 'mark_published' | 'discard' }
//
// mark_published is a direct status flip, same as every other trigger
// below. EOS Phase 2 Priority 5 briefly routed it through a
// propose-then-approve detour (lib/ai-actions.ts's proposeAction +
// a Decide approval) on the theory that publish should get the same
// gate as AI-proposed mutations. In practice that gate had no page: no
// route in the app ever rendered the Decide queue, so every proposal
// this created sat in build_request_inbox forever and comms_content
// never advanced past ready_to_publish - Content Workbench's Portfolio
// tab stayed permanently empty. mark_published is fired only by a
// Captain's own explicit click at the end of a QA'd, already-approved
// pipeline (see ContentBoard.tsx's Proofing stage) - there is no
// separate party for a second confirmation to be gating against - so it
// reverts to the direct update every other trigger here already uses.
// lib/ai-actions.ts's publish_content action type is untouched and still
// available for an LLM-initiated <starfleet-action> publish proposal via
// parseAndProposeActions, which is a genuinely different actor and still
// warrants the propose/approve gate once a Decide page exists to drain it.
//
// discard -> archived is available from every pre-published stage (Phase 1C
// Communications Workbench: no way existed to drop a pipeline item that had
// lost editorial value). Unlike mark_published this does NOT go through
// Decide - it makes nothing newly visible, only hides an item from the
// active pipeline (comms_content rows are never deleted, so it's reversible
// by a direct status flip if ever needed). Once 'published' an item is the
// reputation portfolio record and isn't discardable via this route.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

const TRANSITIONS: Record<string, Record<string, string>> = {
  opportunity:      { officer_drafted: 'draft', discard: 'archived' },
  draft:            { officer_submitted: 'review', discard: 'archived' },
  review:           { captain_approved: 'approved', discard: 'archived' },
  approved:         { captain_confirmed: 'ready_to_publish', discard: 'archived' },
  ready_to_publish: { mark_published: 'published', discard: 'archived' },
};

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { trigger } = await req.json();
    const sb = serviceClient();

    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('status')
      .eq('id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });

    const allowed = TRANSITIONS[row.status] ?? {};
    const next = allowed[trigger];
    if (!next) {
      return NextResponse.json(
        { error: `Trigger '${trigger}' not valid from status '${row.status}'` },
        { status: 400 }
      );
    }

    const { error: updateErr } = await sb
      .from('comms_content')
      .update({ status: next, updated_at: new Date().toISOString() })
      .eq('id', params.id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true, from: row.status, to: next });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
