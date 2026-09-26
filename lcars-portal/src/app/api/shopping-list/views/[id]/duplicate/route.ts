import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { duplicateSavedView } from '@/lib/shoppingListViewsServer';
import { errorDetail } from '@/lib/errorDetail';

// POST /api/shopping-list/views/[id]/duplicate — copies filters/sort into a
// new view named "<original> (copy)" (or "(copy 2)", … on a further
// collision), never auto-selected.
export async function POST(_request: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session?.user?.id) {
    return NextResponse.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const supabase = await createSupabaseServerClient();
    const result = await duplicateSavedView(supabase, session.user.id, params.id);
    if (!result.ok) {
      const status = result.error === 'not_found' ? 404 : result.error === 'duplicate_name' ? 409 : 503;
      return NextResponse.json({ ok: false, unavailable: status === 503, error: result.error, detail: result.detail }, { status });
    }
    return NextResponse.json({ ok: true, data: result.data }, { status: 201 });
  } catch (err) {
    return NextResponse.json({ ok: false, unavailable: true, error: 'unavailable', detail: errorDetail(err) }, { status: 503 });
  }
}
