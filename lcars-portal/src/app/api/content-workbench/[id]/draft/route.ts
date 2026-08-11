// PATCH /api/content-workbench/[id]/draft — save a draft body edit and
// append a revision row.
//
// comms-workbench's own PATCH /api/content/pipeline also edits body, but
// overwrites with no history (a known gap — see backlog item 4 in the
// Content Workbench review). This route is additive and separate: it does
// not change /api/content/pipeline's behaviour, it just gives the Content
// Prep stage a versioned alternative.

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
    const { body: newBody } = await req.json();
    if (typeof newBody !== 'string' || !newBody.trim()) {
      return NextResponse.json({ error: 'body is required' }, { status: 400 });
    }

    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('status')
      .eq('id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (!['draft', 'review', 'approved'].includes(row.status)) {
      return NextResponse.json({ error: `Item is '${row.status}' — cannot edit draft body in this stage` }, { status: 400 });
    }

    const { error: updateErr } = await sb
      .from('comms_content')
      .update({ body: newBody, updated_at: new Date().toISOString() })
      .eq('id', params.id);
    if (updateErr) throw updateErr;

    const { error: revErr } = await sb
      .from('comms_content_revisions')
      .insert({ content_id: params.id, body: newBody, edited_by: session.user?.email ?? session.user?.id ?? 'captain-tjr' });
    if (revErr) throw revErr;

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error('[content-workbench/draft]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
