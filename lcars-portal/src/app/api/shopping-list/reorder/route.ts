import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { errorDetail } from '@/lib/errorDetail';

// POST /api/shopping-list/reorder — body: { ordered_ids: string[] }.
// Writes sequential priority_rank (1..N) matching the given top-to-bottom
// order. Every id must belong to an existing item; anything else 400s
// rather than silently reordering a partial list.
export async function POST(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const orderedIds = Array.isArray(body.ordered_ids)
    ? body.ordered_ids.filter((v): v is string => typeof v === 'string')
    : null;
  if (!orderedIds || orderedIds.length === 0) {
    return NextResponse.json({ error: 'ordered_ids must be a non-empty array of ids' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();
    const updates = orderedIds.map((id, index) =>
      supabase.from('shopping_list_items').update({ priority_rank: index + 1, updated_at: new Date().toISOString() }).eq('id', id),
    );
    const results = await Promise.all(updates);
    const failed = results.find((r) => r.error);
    if (failed?.error) throw failed.error;
    return NextResponse.json({ ok: true, count: orderedIds.length });
  } catch (err) {
    return NextResponse.json({ error: 'Failed to reorder list', detail: errorDetail(err) }, { status: 500 });
  }
}
