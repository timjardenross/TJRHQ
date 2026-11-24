// PRODUCTS — latest recurring-provider, systemic and forward-watch products (read-only), with their flattened
// exceptions. Same read pattern as watching/library: requireSession + createSupabaseServerClient.
// Returns { available: false } until the draft intelligence_products migration is applied.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { collectExceptions, fetchLatestProducts } from '@/lib/intelligenceProducts';

export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  try {
    const sb = await createSupabaseServerClient();
    const { available, products } = await fetchLatestProducts(sb);
    return NextResponse.json({ available, products, exceptions: collectExceptions(products) });
  } catch (err) {
    console.error('[intelligence-workbench/products] read failed:', err);
    return NextResponse.json(
      { error: 'products_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
