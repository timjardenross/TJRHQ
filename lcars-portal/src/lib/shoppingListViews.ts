'use client';

/**
 * Shopping List saved-views client library — backs the "Saved views"
 * control on the Shopping List Workbench page. Talks to
 * /api/shopping-list/views/* (migration 0223's shopping_list_saved_views,
 * server-authoritative). Replaces the old `tjr-shopping-saved-views`
 * localStorage-only implementation — the server is now the source of
 * truth; any client caching here is UX-only (last successful fetch kept in
 * component state, never re-read from localStorage as ground truth).
 */

export interface ShoppingListFilters {
  category?: string;
  status?: string;
  recipient?: string;
  occasion?: string;
  [key: string]: string | undefined;
}

export interface ShoppingListSort {
  field: string | null;
  direction: 'asc' | 'desc';
}

export interface SavedShoppingView {
  id: string;
  name: string;
  filters: ShoppingListFilters;
  sort: ShoppingListSort;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedViewsResult {
  ok: boolean;
  data?: SavedShoppingView[];
  view?: SavedShoppingView;
  empty?: boolean;
  unavailable?: boolean;
  error?: string;
}

async function parse(resp: Response): Promise<SavedViewsResult> {
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok || json?.ok === false) {
    const error = json?.error ?? `Request failed (${resp.status})`;
    if (json?.detail) console.error(`[shopping-list saved views] ${error}: ${json.detail}`);
    return { ok: false, error, unavailable: Boolean(json?.unavailable) };
  }
  return { ok: true, data: json?.data, view: json?.data, empty: json?.empty };
}

export async function fetchSavedViews(): Promise<SavedViewsResult> {
  try {
    return await parse(await fetch('/api/shopping-list/views'));
  } catch (err) {
    return { ok: false, unavailable: true, error: err instanceof Error ? err.message : 'Failed to load saved views.' };
  }
}

export async function createSavedView(
  input: { name: string; filters?: ShoppingListFilters; sort?: ShoppingListSort; is_default?: boolean },
): Promise<SavedViewsResult> {
  try {
    return await parse(
      await fetch('/api/shopping-list/views', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    );
  } catch (err) {
    return { ok: false, unavailable: true, error: err instanceof Error ? err.message : 'Failed to save view.' };
  }
}

export async function updateSavedView(
  id: string,
  patch: { name?: string; filters?: ShoppingListFilters; sort?: ShoppingListSort },
): Promise<SavedViewsResult> {
  try {
    return await parse(
      await fetch(`/api/shopping-list/views/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      }),
    );
  } catch (err) {
    return { ok: false, unavailable: true, error: err instanceof Error ? err.message : 'Failed to update view.' };
  }
}

export async function deleteSavedView(id: string): Promise<SavedViewsResult> {
  try {
    return await parse(await fetch(`/api/shopping-list/views/${id}`, { method: 'DELETE' }));
  } catch (err) {
    return { ok: false, unavailable: true, error: err instanceof Error ? err.message : 'Failed to delete view.' };
  }
}

export async function selectSavedView(id: string): Promise<SavedViewsResult> {
  try {
    return await parse(await fetch(`/api/shopping-list/views/${id}/select`, { method: 'POST' }));
  } catch (err) {
    return { ok: false, unavailable: true, error: err instanceof Error ? err.message : 'Failed to select view.' };
  }
}

export async function duplicateSavedView(id: string): Promise<SavedViewsResult> {
  try {
    return await parse(await fetch(`/api/shopping-list/views/${id}/duplicate`, { method: 'POST' }));
  } catch (err) {
    return { ok: false, unavailable: true, error: err instanceof Error ? err.message : 'Failed to duplicate view.' };
  }
}
