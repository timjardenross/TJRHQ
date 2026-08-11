// PATCH /api/content-workbench/[id]/qa — save the Proofing-stage QA
// checklist and reviewer sign-off.
//
// This is the structured proofing gate the Communications Workbench review
// found missing: 'review'/'approved' in comms_content were previously bare
// status labels with no checklist and no reviewer field (unlike the separate
// OSINT intelligence-brief workflow's IN_REVIEW -> QA_PASSED -> APPROVED
// pattern in intelligence/workflow/service.py, which this mirrors in spirit
// — a lightweight equivalent, not a port of that RBAC/audit-log machinery).
// This route only ever writes qa_checklist/qa_status/reviewed_by/reviewed_at
// — it never changes comms_content.status. Advancing status (e.g.
// 'captain_approved') still goes through the one canonical
// /api/comms/[id]/advance, unchanged, and the Content Workbench UI gates
// showing that button on qa_status === 'qa_passed'.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

const CHECKLIST_KEYS = ['accuracy', 'brand_voice', 'compliance', 'links_checked'] as const;

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const body = await req.json();
    const checklist: Record<string, unknown> = {};
    for (const key of CHECKLIST_KEYS) {
      if (typeof body.qa_checklist?.[key] === 'boolean') checklist[key] = body.qa_checklist[key];
    }
    if (typeof body.qa_checklist?.notes === 'string') checklist.notes = body.qa_checklist.notes.slice(0, 2000);

    const allChecked = CHECKLIST_KEYS.every((k) => checklist[k] === true);
    const anyUnchecked = CHECKLIST_KEYS.some((k) => checklist[k] === false);
    const qaStatus = body.qa_status ?? (allChecked ? 'qa_passed' : anyUnchecked ? 'qa_failed' : 'pending');
    if (!['pending', 'qa_passed', 'qa_failed'].includes(qaStatus)) {
      return NextResponse.json({ error: 'Invalid qa_status' }, { status: 400 });
    }

    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('status, qa_checklist')
      .eq('id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (!['review', 'approved'].includes(row.status)) {
      return NextResponse.json({ error: `Item is '${row.status}' — QA only applies during proofing` }, { status: 400 });
    }

    const mergedChecklist = { ...(row.qa_checklist ?? {}), ...checklist };
    const patch: Record<string, unknown> = {
      qa_checklist: mergedChecklist,
      qa_status: qaStatus,
      updated_at: new Date().toISOString(),
    };
    if (qaStatus === 'qa_passed') {
      patch.reviewed_by = session.user?.email ?? session.user?.id ?? 'captain-tjr';
      patch.reviewed_at = new Date().toISOString();
    }

    const { error: updateErr } = await sb.from('comms_content').update(patch).eq('id', params.id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true, qa_status: qaStatus, qa_checklist: mergedChecklist });
  } catch (err) {
    console.error('[content-workbench/qa]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
