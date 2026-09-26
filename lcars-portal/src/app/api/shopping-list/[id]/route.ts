import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { errorDetail } from '@/lib/errorDetail';
import { logActionHistory } from '@/lib/actionHistoryServer';

const VALID_STATUSES = ['wishlist', 'saved_for', 'purchased', 'cancelled'] as const;
const PATCHABLE_FIELDS = [
  'product_name', 'vendor', 'image_url', 'source_url', 'cost', 'currency',
  'category', 'recipient', 'status', 'target_occasion', 'notes', 'purchased_at',
] as const;

// PATCH /api/shopping-list/[id] — edit any subset of fields, including
// mark-as-purchased (status: 'purchased', purchased_at: <iso>).
export async function PATCH(request: NextRequest, { params }: { params: { id: string } }) {
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

  const patch: Record<string, unknown> = {};
  for (const field of PATCHABLE_FIELDS) {
    if (!(field in body)) continue;
    const value = body[field];
    if (field === 'cost') {
      const num = typeof value === 'number' ? value : Number(value);
      if (!Number.isFinite(num)) {
        await logActionHistory({ action: 'shopping_list.item_update', outcome: 'failed', workbench: 'shopping-list', recordId: params.id, details: { reason: 'cost_invalid' } });
        return NextResponse.json({ error: 'cost must be a number' }, { status: 400 });
      }
      patch.cost = num;
    } else if (field === 'status') {
      if (typeof value !== 'string' || !(VALID_STATUSES as readonly string[]).includes(value)) {
        await logActionHistory({ action: 'shopping_list.item_update', outcome: 'failed', workbench: 'shopping-list', recordId: params.id, details: { reason: 'status_invalid' } });
        return NextResponse.json({ error: `status must be one of ${VALID_STATUSES.join(', ')}` }, { status: 400 });
      }
      patch.status = value;
    } else if (field === 'purchased_at') {
      patch.purchased_at = value === null ? null : String(value);
    } else if (typeof value === 'string') {
      patch[field] = value.trim() || null;
    } else if (value === null) {
      patch[field] = null;
    }
  }
  if ('product_name' in patch && !patch.product_name) {
    await logActionHistory({ action: 'shopping_list.item_update', outcome: 'failed', workbench: 'shopping-list', recordId: params.id, details: { reason: 'product_name_empty' } });
    return NextResponse.json({ error: 'product_name cannot be empty' }, { status: 400 });
  }
  if ('category' in patch && !patch.category) {
    await logActionHistory({ action: 'shopping_list.item_update', outcome: 'failed', workbench: 'shopping-list', recordId: params.id, details: { reason: 'category_empty' } });
    return NextResponse.json({ error: 'category cannot be empty' }, { status: 400 });
  }
  patch.updated_at = new Date().toISOString();

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.from('shopping_list_items').update(patch).eq('id', params.id);
    if (error) throw error;
    await logActionHistory({ action: 'shopping_list.item_update', outcome: 'success', workbench: 'shopping-list', recordId: params.id, details: { fields: Object.keys(patch).filter((k) => k !== 'updated_at') } });
    return NextResponse.json({ ok: true, id: params.id });
  } catch (err) {
    await logActionHistory({ action: 'shopping_list.item_update', outcome: 'failed', workbench: 'shopping-list', recordId: params.id, details: { reason: 'write_error' } });
    return NextResponse.json({ error: 'Failed to update item', detail: errorDetail(err) }, { status: 500 });
  }
}

// DELETE /api/shopping-list/[id]
export async function DELETE(_request: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.from('shopping_list_items').delete().eq('id', params.id);
    if (error) throw error;
    await logActionHistory({ action: 'shopping_list.item_delete', outcome: 'success', workbench: 'shopping-list', recordId: params.id });
    return NextResponse.json({ ok: true, id: params.id });
  } catch (err) {
    await logActionHistory({ action: 'shopping_list.item_delete', outcome: 'failed', workbench: 'shopping-list', recordId: params.id, details: { reason: 'write_error' } });
    return NextResponse.json({ error: 'Failed to delete item', detail: errorDetail(err) }, { status: 500 });
  }
}
