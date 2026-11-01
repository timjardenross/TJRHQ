import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { selectSavedView } from '@/lib/shoppingListViewsServer';
import { errorDetail } from '@/lib/errorDetail';

// POST /api/shopping-list/views/[id]/select — marks this view as the one to
// auto-apply on load (is_default=true here, false on every other view this
// owner has). This is what makes the selected view reload-safe server-side
// instead of relying on localStorage as the source of truth.
export async function POST(_request: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session?.user?.id) {
    return NextResponse.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const supabase = await createSupabaseServerClient();
    const result = await selectSavedView(supabase, session.user.id, params.id);
    if (!result.ok) {
      const status = result.error === 'not_found' ? 404 : 503;
      return NextResponse.json({ ok: false, unavailable: status === 503, error: result.error, detail: result.detail }, { status });
    }
    return NextResponse.json({ ok: true, data: result.data });
  } catch (err) {
    return NextResponse.json({ ok: false, unavailable: true, error: 'unavailable', detail: errorDetail(err) }, { status: 503 });
  }
}
