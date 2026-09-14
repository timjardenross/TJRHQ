import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { errorDetail } from '@/lib/errorDetail';

// DELETE /api/emergency-alerts/silences/[id] — ends a silence early.
// Sets ends_at to now rather than deleting the row: same "expire, don't
// erase" model as Prometheus Alertmanager's own silences, so a silence
// that muted something stays visible in the list as history instead of
// vanishing. A silence whose window has already passed is a no-op (the
// update still succeeds; ends_at just doesn't move later).
export async function DELETE(_request: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const sb = await createSupabaseServerClient();
    const now = new Date().toISOString();
    const { error } = await sb
      .from('alert_silences')
      .update({ ends_at: now })
      .eq('id', params.id)
      .gt('ends_at', now); // only pull ends_at earlier, never push an already-expired silence's window forward
    if (error) throw error;
    return NextResponse.json({ ok: true, id: params.id });
  } catch (err) {
    return NextResponse.json({ error: 'Failed to expire silence', detail: errorDetail(err) }, { status: 500 });
  }
}
