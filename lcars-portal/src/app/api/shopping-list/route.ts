import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { errorDetail } from '@/lib/errorDetail';

const VALID_STATUSES = ['wishlist', 'saved_for', 'purchased', 'cancelled'] as const;
const ITEM_SELECT = [
  'id', 'product_name', 'vendor', 'image_url', 'source_url', 'cost', 'currency',
  'category', 'recipient', 'priority_rank', 'status', 'target_occasion', 'notes',
  'purchased_at', 'created_at', 'updated_at',
].join(', ');

// GET /api/shopping-list — every item, ordered by manual priority.
export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase
      .from('shopping_list_items')
      .select(ITEM_SELECT)
      .order('priority_rank', { ascending: true });
    if (error) throw error;
    return NextResponse.json({ items: data ?? [] });
  } catch (err) {
    return NextResponse.json({ error: 'Failed to fetch shopping list', detail: errorDetail(err) }, { status: 500 });
  }
}

// POST /api/shopping-list — create one item. New items are placed at the
// bottom of manual priority (max existing priority_rank + 1) so a fresh
// add never silently jumps the Captain's existing order.
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

  const product_name = typeof body.product_name === 'string' ? body.product_name.trim() : '';
  if (!product_name) {
    return NextResponse.json({ error: 'product_name is required' }, { status: 400 });
  }
  const category = typeof body.category === 'string' ? body.category.trim() : '';
  if (!category) {
    return NextResponse.json({ error: 'category is required' }, { status: 400 });
  }
  const cost = typeof body.cost === 'number' ? body.cost : Number(body.cost);
  if (!Number.isFinite(cost)) {
    return NextResponse.json({ error: 'cost must be a number' }, { status: 400 });
  }
  const rawStatus = typeof body.status === 'string' ? body.status.trim() : 'wishlist';
  const status = (VALID_STATUSES as readonly string[]).includes(rawStatus) ? rawStatus : 'wishlist';

  try {
    const supabase = await createSupabaseServerClient();

    const { data: maxRow } = await supabase
      .from('shopping_list_items')
      .select('priority_rank')
      .order('priority_rank', { ascending: false })
      .limit(1)
      .maybeSingle<{ priority_rank: number }>();
    const nextRank = (maxRow?.priority_rank ?? 0) + 1;

    const { data, error } = await supabase
      .from('shopping_list_items')
      .insert({
        product_name,
        vendor: typeof body.vendor === 'string' ? body.vendor.trim() || null : null,
        image_url: typeof body.image_url === 'string' ? body.image_url.trim() || null : null,
        source_url: typeof body.source_url === 'string' ? body.source_url.trim() || null : null,
        cost,
        currency: typeof body.currency === 'string' && body.currency.trim() ? body.currency.trim() : 'AUD',
        category,
        recipient: typeof body.recipient === 'string' ? body.recipient.trim() || null : null,
        priority_rank: nextRank,
        status,
        target_occasion: typeof body.target_occasion === 'string' ? body.target_occasion.trim() || null : null,
        notes: typeof body.notes === 'string' ? body.notes.trim() || null : null,
      })
      .select('id')
      .maybeSingle<{ id: string }>();
    if (error) throw error;
    return NextResponse.json({ item: data }, { status: 201 });
  } catch (err) {
    return NextResponse.json({ error: 'Failed to create item', detail: errorDetail(err) }, { status: 500 });
  }
}
