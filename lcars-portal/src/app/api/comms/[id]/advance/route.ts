// POST /api/comms/[id]/advance — advance a comms_content item through the pipeline.
// Body: { trigger: 'officer_drafted' | 'officer_submitted' | 'captain_approved' | 'captain_confirmed' | 'mark_published' | 'discard' }
//
// EOS Phase 2 Priority 5 (Executive Communications Studio): mark_published
// is the one trigger here that makes content visible outside this
// pipeline, so - per the Phase 1 Capability Composition Audit's disclosed
// gap and docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md §4 ("no
// exceptions") - it no longer executes directly. It queues a governed
// publish_content proposal (lib/ai-actions.ts's proposeAction, the same
// mechanism every other AI/system-proposed mutation already uses) and the
// real status flip only happens if and when the Captain approves that
// exact item in Decide, via POST /api/build-request/[id]/approve-action.
// Every earlier transition (officer_drafted through captain_confirmed) is
// unchanged - those are internal drafting states, not a publish action.
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
import { proposeAction } from '@/lib/ai-actions';

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
  try {
    const { trigger } = await req.json();
    const sb = serviceClient();

    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('status, title')
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

    if (trigger === 'mark_published') {
      const proposal = await proposeAction('publish_content', {
        content_id: params.id,
        title: row.title,
      });
      if (!proposal.success) {
        return NextResponse.json({ error: proposal.detail }, { status: 500 });
      }
      return NextResponse.json({ proposed: true, detail: proposal.detail });
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
