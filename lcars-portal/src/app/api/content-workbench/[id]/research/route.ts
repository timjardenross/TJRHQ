// PATCH /api/content-workbench/[id]/research — save the research brief.
//
// This is the Research stage of the Content Workbench (COMMS-002): angle,
// notes, and sources gathered before a draft is generated. Setting
// research_completed_at is what gates /api/content-workbench/[id]/generate —
// there is no structured research step anywhere else in comms_content today
// (/api/comms/generate lets drafting start straight from 'opportunity' with
// no brief). Does not touch comms_content.status — advance() stays the only
// place status transitions happen.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const body = await req.json();
    const notes = typeof body.research_notes === 'string' ? body.research_notes.slice(0, 8000) : undefined;
    const angle = typeof body.research_angle === 'string' ? body.research_angle.slice(0, 500) : undefined;
    const sources = Array.isArray(body.research_sources) ? body.research_sources.slice(0, 30) : undefined;
    const complete = body.complete === true;

    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('status')
      .eq('id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (row.status !== 'opportunity') {
      return NextResponse.json({ error: `Item is '${row.status}' — research only applies before a draft exists` }, { status: 400 });
    }

    const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
    if (notes !== undefined) patch.research_notes = notes;
    if (angle !== undefined) patch.research_angle = angle;
    if (sources !== undefined) patch.research_sources = sources;
    if (complete) {
      if (!notes) {
        return NextResponse.json({ error: 'Add research notes before marking research complete' }, { status: 400 });
      }
      patch.research_completed_at = new Date().toISOString();
    }

    const { error: updateErr } = await sb.from('comms_content').update(patch).eq('id', params.id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error('[content-workbench/research]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
