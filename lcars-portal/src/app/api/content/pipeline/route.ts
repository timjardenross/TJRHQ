// Content pipeline API — update comms_content items.
// PATCH /api/content/pipeline?id=...  — update notes, body
//
// GET removed 2026-07-18 (WORKBENCH-REVIEW.md Medium finding, Group E):
// redundant with /api/comms's own GET over the same table, and confirmed
// zero real callers (comms-workbench/_components/PipelineTab.tsx only ever
// calls the PATCH, with ?id=).
//
// EOS Phase 3 Priority 4/6 (Canonical Architecture Audit / Governance
// Validation): this PATCH used to also accept an arbitrary `status`
// (including 'published') and write it directly via a service-role
// client, with no session check and no governance gate - a live,
// unauthenticated bypass of the exact propose-then-approve mechanism
// Phase 2 Priority 5 built for comms_content's publish step
// (lib/ai-actions.ts's publishContent(), gated behind Captain approval in
// Decide). A whole-of-platform audit confirmed this route has zero in-app
// callers, so removing status-write capability breaks nothing live.
// api/comms/[id]/advance/route.ts is the one canonical path for every
// comms_content status transition now - this route no longer competes
// with it.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function PATCH(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const id = req.nextUrl.searchParams.get('id');
    if (!id) return NextResponse.json({ error: 'id is required' }, { status: 400 });

    const body = await req.json();
    const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };

    if (body.status !== undefined) {
      return NextResponse.json(
        { error: 'Status transitions go through /api/comms/[id]/advance, not this route.' },
        { status: 400 },
      );
    }
    if (body.notes !== undefined) patch.notes = body.notes;
    if (body.body !== undefined) patch.body = body.body;

    const sb = serviceClient();
    const { error } = await sb.from('comms_content').update(patch).eq('id', id);
    if (error) throw error;

    return NextResponse.json({ success: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Internal error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
