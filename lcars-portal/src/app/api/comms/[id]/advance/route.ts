// POST /api/comms/[id]/advance — advance a comms_content item through the pipeline.
// Body: { trigger: 'officer_drafted' | 'officer_submitted' | 'captain_approved' | 'captain_confirmed' | 'mark_published' }

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const TRANSITIONS: Record<string, Record<string, string>> = {
  opportunity:      { officer_drafted: 'draft' },
  draft:            { officer_submitted: 'review' },
  review:           { captain_approved: 'approved' },
  approved:         { captain_confirmed: 'ready_to_publish' },
  ready_to_publish: { mark_published: 'published' },
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
