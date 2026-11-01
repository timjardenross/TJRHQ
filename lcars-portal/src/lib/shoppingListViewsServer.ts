import type { SupabaseClient } from '@supabase/supabase-js';
import { errorDetail } from '@/lib/errorDetail';

/**
 * Server-side data layer for shopping_list_saved_views (migration 0223).
 * Route handlers under src/app/api/shopping-list/views/* are thin wrappers
 * around these functions — same split as
 * lib/knowledgeLibraryDecide.ts/api/knowledge-library/documents/[id]/decide,
 * so route-level auth/validation can be tested without a real Supabase
 * client and this DB logic can be tested without spinning up Next.js
 * request/response objects.
 *
 * Contract (VM activation handoff, Task 2): create, rename, update
 * filters/sort, select, duplicate, delete — all owner-scoped (RLS backs
 * this too, but these functions also filter by owner_id explicitly so a
 * wrong-owner call fails the same way whether RLS is bypassed by a
 * service-role client or not).
 */

const SELECT_COLUMNS = 'id, name, filters, sort, is_default, created_at, updated_at';

export interface SavedView {
  id: string;
  name: string;
  filters: Record<string, unknown>;
  sort: SortPayload;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SortPayload {
  field: string | null;
  direction: 'asc' | 'desc';
}

const DEFAULT_SORT: SortPayload = { field: null, direction: 'asc' };

export type ServerResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: 'invalid_input' | 'not_found' | 'duplicate_name' | 'unavailable'; detail: string };

/** filters is an open jsonb bag (category/status/recipient/occasion today,
 * more later without a migration) — the only structural requirement is
 * "plain object of string/number/boolean/null values", not a specific key
 * set. Anything else (array, nested object, non-primitive value) is
 * rejected rather than silently coerced or dropped — a malformed payload
 * must fail loudly, not produce a view that quietly filters on nothing. */
export function isValidFilterPayload(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  return Object.values(value as Record<string, unknown>).every(
    (v) => v === null || ['string', 'number', 'boolean'].includes(typeof v),
  );
}

/** sort is either {} (no explicit sort — item order applies) or
 * {field: string, direction: 'asc'|'desc'}. Anything else (wrong types, an
 * unknown extra key, a direction outside the enum) is rejected explicitly
 * — an obsolete/malformed sort payload from a future schema change must
 * not be silently reinterpreted as "no sort" or fall back to a misleading
 * default direction. */
export function isValidSortPayload(value: unknown): value is Partial<SortPayload> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const v = value as Record<string, unknown>;
  const keys = Object.keys(v);
  if (keys.length === 0) return true;
  if (!keys.every((k) => k === 'field' || k === 'direction')) return false;
  if ('field' in v && v.field !== null && typeof v.field !== 'string') return false;
  if ('direction' in v && v.direction !== 'asc' && v.direction !== 'desc') return false;
  return true;
}

function normalizeSort(value: unknown): SortPayload {
  if (!isValidSortPayload(value)) return DEFAULT_SORT;
  return { field: value.field ?? null, direction: value.direction ?? 'asc' };
}

export async function listSavedViews(
  supabase: SupabaseClient,
  ownerId: string,
): Promise<ServerResult<SavedView[]>> {
  const { data, error } = await supabase
    .from('shopping_list_saved_views')
    .select(SELECT_COLUMNS)
    .eq('owner_id', ownerId)
    .order('name', { ascending: true });
  if (error) return { ok: false, error: 'unavailable', detail: errorDetail(error) };
  return { ok: true, data: (data ?? []) as SavedView[] };
}

export async function createSavedView(
  supabase: SupabaseClient,
  ownerId: string,
  input: Record<string, unknown>,
): Promise<ServerResult<SavedView>> {
  const name = typeof input.name === 'string' ? input.name.trim() : '';
  if (!name) return { ok: false, error: 'invalid_input', detail: 'name is required' };

  const filters = input.filters === undefined ? {} : input.filters;
  if (!isValidFilterPayload(filters)) {
    return { ok: false, error: 'invalid_input', detail: 'filters must be a flat object of string/number/boolean/null values' };
  }
  const sortInput = input.sort === undefined ? {} : input.sort;
  if (!isValidSortPayload(sortInput)) {
    return { ok: false, error: 'invalid_input', detail: 'sort must be {} or {field, direction}' };
  }
  const sort = normalizeSort(sortInput);
  const makeDefault = input.is_default === true;

  try {
    if (makeDefault) await clearDefault(supabase, ownerId);
    const { data, error } = await supabase
      .from('shopping_list_saved_views')
      .insert({ owner_id: ownerId, name, filters, sort, is_default: makeDefault })
      .select(SELECT_COLUMNS)
      .maybeSingle<SavedView>();
    if (error) {
      if (isUniqueViolation(error)) return { ok: false, error: 'duplicate_name', detail: `A view named "${name}" already exists.` };
      return { ok: false, error: 'unavailable', detail: errorDetail(error) };
    }
    if (!data) return { ok: false, error: 'unavailable', detail: 'Insert returned no row.' };
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: 'unavailable', detail: errorDetail(err) };
  }
}

export async function updateSavedView(
  supabase: SupabaseClient,
  ownerId: string,
  id: string,
  patch: Record<string, unknown>,
): Promise<ServerResult<SavedView>> {
  const update: Record<string, unknown> = {};

  if ('name' in patch) {
    const name = typeof patch.name === 'string' ? patch.name.trim() : '';
    if (!name) return { ok: false, error: 'invalid_input', detail: 'name cannot be empty' };
    update.name = name;
  }
  if ('filters' in patch) {
    if (!isValidFilterPayload(patch.filters)) {
      return { ok: false, error: 'invalid_input', detail: 'filters must be a flat object of string/number/boolean/null values' };
    }
    update.filters = patch.filters;
  }
  if ('sort' in patch) {
    if (!isValidSortPayload(patch.sort)) {
      return { ok: false, error: 'invalid_input', detail: 'sort must be {} or {field, direction}' };
    }
    update.sort = normalizeSort(patch.sort);
  }
  if (Object.keys(update).length === 0) {
    return { ok: false, error: 'invalid_input', detail: 'no updatable fields provided' };
  }
  update.updated_at = new Date().toISOString();

  const { data, error } = await supabase
    .from('shopping_list_saved_views')
    .update(update)
    .eq('id', id)
    .eq('owner_id', ownerId)
    .select(SELECT_COLUMNS)
    .maybeSingle<SavedView>();
  if (error) {
    if (isUniqueViolation(error)) return { ok: false, error: 'duplicate_name', detail: 'A view with that name already exists.' };
    return { ok: false, error: 'unavailable', detail: errorDetail(error) };
  }
  if (!data) return { ok: false, error: 'not_found', detail: 'No saved view with that id for this owner.' };
  return { ok: true, data };
}

export async function deleteSavedView(
  supabase: SupabaseClient,
  ownerId: string,
  id: string,
): Promise<ServerResult<{ id: string }>> {
  const { data, error } = await supabase
    .from('shopping_list_saved_views')
    .delete()
    .eq('id', id)
    .eq('owner_id', ownerId)
    .select('id')
    .maybeSingle<{ id: string }>();
  if (error) return { ok: false, error: 'unavailable', detail: errorDetail(error) };
  if (!data) return { ok: false, error: 'not_found', detail: 'No saved view with that id for this owner.' };
  return { ok: true, data };
}

/** Sets is_default=true on exactly this row and false on every other view
 * this owner has — two statements, not a DB transaction (no RPC/function
 * exists for this yet and supabase-js has no client-side transaction
 * primitive here), so a crash between them can theoretically leave zero
 * defaults (self-correcting — the client just falls back to "no view
 * selected") but never two defaults, because the second statement only
 * ever clears other rows, and shopping_list_saved_views_one_default_per_
 * owner (migration 0223) makes two real defaults impossible at the DB
 * level regardless of ordering. */
export async function selectSavedView(
  supabase: SupabaseClient,
  ownerId: string,
  id: string,
): Promise<ServerResult<SavedView>> {
  const { data: target, error: fetchError } = await supabase
    .from('shopping_list_saved_views')
    .select('id')
    .eq('id', id)
    .eq('owner_id', ownerId)
    .maybeSingle<{ id: string }>();
  if (fetchError) return { ok: false, error: 'unavailable', detail: errorDetail(fetchError) };
  if (!target) return { ok: false, error: 'not_found', detail: 'No saved view with that id for this owner.' };

  await clearDefault(supabase, ownerId, id);

  const { data, error } = await supabase
    .from('shopping_list_saved_views')
    .update({ is_default: true, updated_at: new Date().toISOString() })
    .eq('id', id)
    .eq('owner_id', ownerId)
    .select(SELECT_COLUMNS)
    .maybeSingle<SavedView>();
  if (error) return { ok: false, error: 'unavailable', detail: errorDetail(error) };
  if (!data) return { ok: false, error: 'not_found', detail: 'No saved view with that id for this owner.' };
  return { ok: true, data };
}

export async function duplicateSavedView(
  supabase: SupabaseClient,
  ownerId: string,
  id: string,
): Promise<ServerResult<SavedView>> {
  const { data: source, error: fetchError } = await supabase
    .from('shopping_list_saved_views')
    .select(SELECT_COLUMNS)
    .eq('id', id)
    .eq('owner_id', ownerId)
    .maybeSingle<SavedView>();
  if (fetchError) return { ok: false, error: 'unavailable', detail: errorDetail(fetchError) };
  if (!source) return { ok: false, error: 'not_found', detail: 'No saved view with that id for this owner.' };

  const copyName = await firstAvailableCopyName(supabase, ownerId, source.name);

  const { data, error } = await supabase
    .from('shopping_list_saved_views')
    .insert({
      owner_id: ownerId,
      name: copyName,
      filters: source.filters,
      sort: source.sort,
      is_default: false, // a duplicate is never auto-selected over the original
    })
    .select(SELECT_COLUMNS)
    .maybeSingle<SavedView>();
  if (error) {
    if (isUniqueViolation(error)) return { ok: false, error: 'duplicate_name', detail: `A view named "${copyName}" already exists.` };
    return { ok: false, error: 'unavailable', detail: errorDetail(error) };
  }
  if (!data) return { ok: false, error: 'unavailable', detail: 'Insert returned no row.' };
  return { ok: true, data };
}

async function clearDefault(supabase: SupabaseClient, ownerId: string, exceptId?: string): Promise<void> {
  let query = supabase
    .from('shopping_list_saved_views')
    .update({ is_default: false, updated_at: new Date().toISOString() })
    .eq('owner_id', ownerId)
    .eq('is_default', true);
  if (exceptId) query = query.neq('id', exceptId);
  await query;
}

async function firstAvailableCopyName(supabase: SupabaseClient, ownerId: string, baseName: string): Promise<string> {
  const { data } = await supabase
    .from('shopping_list_saved_views')
    .select('name')
    .eq('owner_id', ownerId);
  const existing = new Set((data ?? []).map((r: { name: string }) => r.name));
  let candidate = `${baseName} (copy)`;
  let n = 2;
  while (existing.has(candidate)) {
    candidate = `${baseName} (copy ${n})`;
    n += 1;
  }
  return candidate;
}

function isUniqueViolation(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && (error as Record<string, unknown>).code === '23505');
}
