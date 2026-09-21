import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { updateSavedView, deleteSavedView } from '@/lib/shoppingListViewsServer';
import { errorDetail } from '@/lib/errorDetail';

function statusFor(error: 'invalid_input' | 'not_found' | 'duplicate_name' | 'unavailable'): number {
  switch (error) {
    case 'invalid_input': return 400;
    case 'not_found': return 404;
    case 'duplicate_name': return 409;
    case 'unavailable': return 503;
  }
}

// PATCH /api/shopping-list/views/[id] — rename and/or update filters/sort.
// Owner-scoped: updateSavedView filters by owner_id itself (belt-and-braces
// alongside RLS), so a wrong-owner id reads as 'not_found', never leaking
// whether the row exists for someone else.
export async function PATCH(request: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session?.user?.id) {
    return NextResponse.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: 'invalid_input', detail: 'Invalid JSON body' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();
    const result = await updateSavedView(supabase, session.user.id, params.id, body);
    if (!result.ok) {
      const status = statusFor(result.error);
      return NextResponse.json({ ok: false, unavailable: status === 503, error: result.error, detail: result.detail }, { status });
    }
    return NextResponse.json({ ok: true, data: result.data });
  } catch (err) {
    return NextResponse.json({ ok: false, unavailable: true, error: 'unavailable', detail: errorDetail(err) }, { status: 503 });
  }
}

// DELETE /api/shopping-list/views/[id]
export async function DELETE(_request: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session?.user?.id) {
    return NextResponse.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const supabase = await createSupabaseServerClient();
    const result = await deleteSavedView(supabase, session.user.id, params.id);
    if (!result.ok) {
      const status = statusFor(result.error);
      return NextResponse.json({ ok: false, unavailable: status === 503, error: result.error, detail: result.detail }, { status });
    }
    return NextResponse.json({ ok: true, data: result.data });
  } catch (err) {
    return NextResponse.json({ ok: false, unavailable: true, error: 'unavailable', detail: errorDetail(err) }, { status: 503 });
  }
}
