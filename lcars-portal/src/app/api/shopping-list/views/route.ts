import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { listSavedViews, createSavedView } from '@/lib/shoppingListViewsServer';
import { errorDetail } from '@/lib/errorDetail';

// GET /api/shopping-list/views — every saved view this Captain owns.
// Typed outcome envelope (VM activation handoff, Task 2): `ok: true` always
// carries `data` (possibly `[]`, with `empty: true` when it is — an
// explicit governed empty result, not a silent success masking a fetch
// that never ran); `ok: false` distinguishes a real backend failure
// (`unavailable: true`, 503 — never fabricated/stale data) from a request
// error (400).
export async function GET() {
  const session = await requireSession();
  if (!session?.user?.id) {
    return NextResponse.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const supabase = await createSupabaseServerClient();
    const result = await listSavedViews(supabase, session.user.id);
    if (!result.ok) {
      return NextResponse.json({ ok: false, unavailable: true, error: result.error, detail: result.detail }, { status: 503 });
    }
    return NextResponse.json({ ok: true, data: result.data, empty: result.data.length === 0 });
  } catch (err) {
    // A thrown (not returned) failure — e.g. the Supabase client itself
    // unreachable — must still surface as an honest unavailable result,
    // never a silent 500 with no typed shape the client can act on.
    return NextResponse.json({ ok: false, unavailable: true, error: 'unavailable', detail: errorDetail(err) }, { status: 503 });
  }
}

// POST /api/shopping-list/views — create a saved view {name, filters?, sort?, is_default?}.
export async function POST(request: NextRequest) {
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
    const result = await createSavedView(supabase, session.user.id, body);
    if (!result.ok) {
      const status = result.error === 'invalid_input' ? 400 : result.error === 'duplicate_name' ? 409 : 503;
      return NextResponse.json(
        { ok: false, unavailable: status === 503, error: result.error, detail: result.detail },
        { status },
      );
    }
    return NextResponse.json({ ok: true, data: result.data }, { status: 201 });
  } catch (err) {
    return NextResponse.json({ ok: false, unavailable: true, error: 'unavailable', detail: errorDetail(err) }, { status: 503 });
  }
}
