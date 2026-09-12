'use client';

/**
 * Shopping List library — Shopping List Workbench data layer.
 *
 * Backs `shopping_list_items` (migration 0199). Mirrors lib/personalTasks.ts's
 * shape (types + fetch/create/update functions, no class) but goes through
 * this app's own API routes (/api/shopping-list/*) rather than the browser
 * Supabase client directly — personal_tasks writes straight from the
 * browser under RLS, but this feature also needs a server-side-only step
 * (link preview scraping, SSRF-checked), so all shopping-list persistence
 * is routed through the API for one consistent path. Single-user app — no
 * owner/user_id filtering beyond RLS's own authenticated policy.
 */

export type ShoppingListStatus = 'wishlist' | 'saved_for' | 'purchased' | 'cancelled';

export const STATUSES: { key: ShoppingListStatus; label: string }[] = [
  { key: 'wishlist', label: 'Wishlist' },
  { key: 'saved_for', label: 'Saving for' },
  { key: 'purchased', label: 'Purchased' },
  { key: 'cancelled', label: 'Cancelled' },
];

export interface ShoppingListItem {
  id: string;
  product_name: string;
  vendor: string | null;
  image_url: string | null;
  source_url: string | null;
  cost: number;
  currency: string;
  category: string;
  recipient: string | null;
  priority_rank: number;
  status: ShoppingListStatus;
  target_occasion: string | null;
  notes: string | null;
  purchased_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface NewShoppingListItemInput {
  product_name: string;
  vendor?: string | null;
  image_url?: string | null;
  source_url?: string | null;
  cost: number;
  currency?: string;
  category: string;
  recipient?: string | null;
  status?: ShoppingListStatus;
  target_occasion?: string | null;
  notes?: string | null;
}

export interface ShoppingListResult {
  ok: boolean;
  id?: string;
  error?: string;
}

async function parseResult(resp: Response): Promise<ShoppingListResult> {
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) return { ok: false, error: json?.error ?? `Request failed (${resp.status})` };
  return { ok: true, id: json?.item?.id ?? json?.id };
}

export async function fetchShoppingList(): Promise<ShoppingListItem[]> {
  try {
    const resp = await fetch('/api/shopping-list');
    if (!resp.ok) return [];
    const json = await resp.json();
    return (json?.items as ShoppingListItem[]) ?? [];
  } catch {
    return [];
  }
}

export async function createShoppingListItem(input: NewShoppingListItemInput): Promise<ShoppingListResult> {
  try {
    const resp = await fetch('/api/shopping-list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    return await parseResult(resp);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to create item.' };
  }
}

export async function updateShoppingListItem(
  id: string,
  patch: Partial<NewShoppingListItemInput> & { purchased_at?: string | null },
): Promise<ShoppingListResult> {
  try {
    const resp = await fetch(`/api/shopping-list/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    return await parseResult(resp);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to update item.' };
  }
}

export async function markPurchased(id: string): Promise<ShoppingListResult> {
  return updateShoppingListItem(id, { status: 'purchased', purchased_at: new Date().toISOString() } as never);
}

export async function deleteShoppingListItem(id: string): Promise<ShoppingListResult> {
  try {
    const resp = await fetch(`/api/shopping-list/${id}`, { method: 'DELETE' });
    return await parseResult(resp);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to delete item.' };
  }
}

/** Persists a new drag-to-reorder position for every item in `orderedIds`
 * (top to bottom) by writing sequential priority_rank values, matching
 * personal_tasks' pattern of one explicit-write-per-user-action (no
 * implicit reordering elsewhere in this codebase to mirror — see
 * migration 0199's header comment). */
export async function reorderShoppingList(orderedIds: string[]): Promise<ShoppingListResult> {
  try {
    const resp = await fetch('/api/shopping-list/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ordered_ids: orderedIds }),
    });
    return await parseResult(resp);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Failed to reorder list.' };
  }
}

export interface LinkPreviewDraftResult {
  ok: boolean;
  draft?: {
    product_name: string | null;
    image_url: string | null;
    cost: number | null;
    currency: string | null;
    vendor: string;
  };
  error?: string;
}

/** Calls /api/shopping-list/preview — read-only; never persists anything
 * itself. The Captain reviews/edits every field before Save actually
 * writes the item. */
export async function previewShoppingListUrl(url: string): Promise<LinkPreviewDraftResult> {
  try {
    const resp = await fetch('/api/shopping-list/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const json = await resp.json().catch(() => ({}));
    if (!resp.ok) return { ok: false, error: json?.error ?? `Preview failed (${resp.status})` };
    return { ok: true, draft: json?.draft };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Preview failed.' };
  }
}

export interface CurrencySubtotal {
  currency: string;
  total: number;
  count: number;
}

/** Subtotals grouped by currency — no cross-currency conversion (v1 scope).
 * Excludes cancelled items so a dead wishlist entry doesn't inflate the
 * total the Captain actually expects to spend/has spent. */
export function subtotalsByCurrency(items: ShoppingListItem[]): CurrencySubtotal[] {
  const byCurrency = new Map<string, CurrencySubtotal>();
  for (const item of items) {
    if (item.status === 'cancelled') continue;
    const existing = byCurrency.get(item.currency);
    if (existing) {
      existing.total += item.cost;
      existing.count += 1;
    } else {
      byCurrency.set(item.currency, { currency: item.currency, total: item.cost, count: 1 });
    }
  }
  return Array.from(byCurrency.values()).sort((a, b) => a.currency.localeCompare(b.currency));
}
