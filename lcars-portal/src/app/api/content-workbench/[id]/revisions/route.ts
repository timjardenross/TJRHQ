// GET /api/content-workbench/[id]/revisions — draft revision history,
// latest first. Read-only; populated by the [id]/generate and [id]/draft
// routes only.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const { data, error } = await sb
      .from('comms_content_revisions')
      .select('id, body, edited_by, created_at')
      .eq('content_id', params.id)
      .order('created_at', { ascending: false });
    if (error) throw error;

    return NextResponse.json({ revisions: data ?? [] });
  } catch (err) {
<<<<<<< HEAD
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
=======
    console.error('[content-workbench/revisions]', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
>>>>>>> 3f9972f3d831aafb30298d1ef6b714751063906b
  }
}
