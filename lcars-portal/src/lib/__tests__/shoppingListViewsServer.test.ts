import { describe, it, expect, beforeEach } from 'vitest';
import {
  isValidFilterPayload,
  isValidSortPayload,
  listSavedViews,
  createSavedView,
  updateSavedView,
  deleteSavedView,
  selectSavedView,
  duplicateSavedView,
  type SavedView,
} from '../shoppingListViewsServer';

// Minimal in-memory fake standing in for the Supabase client's
// query-builder chain (.from().select().eq()...maybeSingle()). Real enough
// to exercise owner-scoping, uniqueness, and the one-default-per-owner
// invariant this feature depends on, without a live Postgres connection —
// migration 0223's actual constraints (unique(owner_id, name), the partial
// unique index on is_default) are covered separately by the migration
// itself; this fake just needs to behave the same way the route/lib code
// depends on for these regression tests to be meaningful.
interface Row extends SavedView {
  owner_id: string;
}

function makeFakeSupabase(initialRows: Row[] = []) {
  let rows: Row[] = [...initialRows];
  let idCounter = 1;

  function builder(table: string) {
    if (table !== 'shopping_list_saved_views') throw new Error(`unexpected table ${table}`);
    let filters: { field: string; value: unknown; op: 'eq' | 'neq' }[] = [];
    let mode: 'select' | 'insert' | 'update' | 'delete' = 'select';
    let insertPayload: Partial<Row> | null = null;
    let updatePayload: Partial<Row> | null = null;

    const api = {
      select() { mode = mode === 'insert' || mode === 'update' || mode === 'delete' ? mode : 'select'; return api; },
      insert(payload: Partial<Row>) { mode = 'insert'; insertPayload = payload; return api; },
      update(payload: Partial<Row>) { mode = 'update'; updatePayload = payload; return api; },
      delete() { mode = 'delete'; return api; },
      eq(field: string, value: unknown) { filters.push({ field, value, op: 'eq' }); return api; },
      neq(field: string, value: unknown) { filters.push({ field, value, op: 'neq' }); return api; },
      order() { return api; },
      async maybeSingle<T>(): Promise<{ data: T | null; error: unknown }> {
        const result = run();
        if (result.error) return { data: null, error: result.error };
        const arr = result.data as unknown[];
        return { data: (arr[0] ?? null) as T, error: null };
      },
      then(resolve: (v: { data: unknown; error: unknown }) => void) {
        // Allow `await query` directly (no .maybeSingle()), as list/select
        // call sites in this repo's routes do.
        resolve(run());
        return Promise.resolve();
      },
    };

    function matches(row: Row): boolean {
      return filters.every((f) => (f.op === 'eq' ? (row as any)[f.field] === f.value : (row as any)[f.field] !== f.value));
    }

    function run(): { data: unknown; error: unknown } {
      if (mode === 'select') {
        return { data: rows.filter(matches), error: null };
      }
      if (mode === 'insert') {
        const nameCollision = rows.some((r) => r.owner_id === insertPayload!.owner_id && r.name === insertPayload!.name);
        if (nameCollision) return { data: null, error: { code: '23505', message: 'duplicate key value violates unique constraint' } };
        const now = new Date().toISOString();
        const row: Row = {
          id: `view-${idCounter++}`,
          owner_id: insertPayload!.owner_id as string,
          name: insertPayload!.name as string,
          filters: (insertPayload!.filters as Record<string, unknown>) ?? {},
          sort: (insertPayload!.sort as SavedView['sort']) ?? { field: null, direction: 'asc' },
          is_default: Boolean(insertPayload!.is_default),
          created_at: now,
          updated_at: now,
        };
        rows.push(row);
        return { data: [row], error: null };
      }
      if (mode === 'update') {
        const targets = rows.filter(matches);
        if (targets.length === 0) return { data: [], error: null };
        // Simulate the unique(owner_id, name) constraint on rename too.
        if (updatePayload?.name) {
          const collision = rows.some(
            (r) => r.owner_id === targets[0].owner_id && r.name === updatePayload!.name && r.id !== targets[0].id,
          );
          if (collision) return { data: null, error: { code: '23505', message: 'duplicate key value violates unique constraint' } };
        }
        for (const t of targets) Object.assign(t, updatePayload);
        return { data: targets, error: null };
      }
      // delete
      const targets = rows.filter(matches);
      rows = rows.filter((r) => !matches(r));
      return { data: targets, error: null };
    }

    return api;
  }

  return {
    from: (table: string) => builder(table),
    __rows: () => rows,
  } as any;
}

describe('isValidFilterPayload', () => {
  it('accepts a flat object of primitives', () => {
    expect(isValidFilterPayload({ category: 'books', status: 'wishlist', cost: 10, active: true, note: null })).toBe(true);
  });
  it('rejects arrays', () => {
    expect(isValidFilterPayload([1, 2, 3])).toBe(false);
  });
  it('rejects null', () => {
    expect(isValidFilterPayload(null)).toBe(false);
  });
  it('rejects nested objects', () => {
    expect(isValidFilterPayload({ category: { nested: true } })).toBe(false);
  });
});

describe('isValidSortPayload', () => {
  it('accepts an empty object', () => {
    expect(isValidSortPayload({})).toBe(true);
  });
  it('accepts a valid field/direction pair', () => {
    expect(isValidSortPayload({ field: 'cost', direction: 'desc' })).toBe(true);
  });
  it('rejects an invalid direction', () => {
    expect(isValidSortPayload({ field: 'cost', direction: 'sideways' })).toBe(false);
  });
  it('rejects an unknown key (obsolete/malformed payload must fail closed)', () => {
    expect(isValidSortPayload({ field: 'cost', direction: 'asc', legacyMode: true })).toBe(false);
  });
  it('rejects a non-string field', () => {
    expect(isValidSortPayload({ field: 42, direction: 'asc' })).toBe(false);
  });
});

describe('shoppingListViewsServer CRUD + ownership + defaults', () => {
  const OWNER_A = 'owner-a';
  const OWNER_B = 'owner-b';
  let supabase: ReturnType<typeof makeFakeSupabase>;

  beforeEach(() => {
    supabase = makeFakeSupabase();
  });

  it('creates, lists, and empty-lists honestly', async () => {
    const empty = await listSavedViews(supabase, OWNER_A);
    expect(empty).toEqual({ ok: true, data: [] });

    const created = await createSavedView(supabase, OWNER_A, { name: 'Gifts for Mum', filters: { recipient: 'Mum' } });
    expect(created.ok).toBe(true);
    if (created.ok) expect(created.data.name).toBe('Gifts for Mum');

    const listed = await listSavedViews(supabase, OWNER_A);
    expect(listed.ok).toBe(true);
    if (listed.ok) expect(listed.data).toHaveLength(1);
  });

  it('rejects invalid filters/sort input on create', async () => {
    const badFilters = await createSavedView(supabase, OWNER_A, { name: 'x', filters: { nested: { a: 1 } } });
    expect(badFilters).toMatchObject({ ok: false, error: 'invalid_input' });

    const badSort = await createSavedView(supabase, OWNER_A, { name: 'y', sort: { direction: 'up' } });
    expect(badSort).toMatchObject({ ok: false, error: 'invalid_input' });

    const noName = await createSavedView(supabase, OWNER_A, { name: '   ' });
    expect(noName).toMatchObject({ ok: false, error: 'invalid_input' });
  });

  it('rejects duplicate names for the same owner', async () => {
    await createSavedView(supabase, OWNER_A, { name: 'Same Name' });
    const dupe = await createSavedView(supabase, OWNER_A, { name: 'Same Name' });
    expect(dupe).toMatchObject({ ok: false, error: 'duplicate_name' });
  });

  it('allows the same name across different owners (ownership isolation)', async () => {
    const a = await createSavedView(supabase, OWNER_A, { name: 'Shared Name' });
    const b = await createSavedView(supabase, OWNER_B, { name: 'Shared Name' });
    expect(a.ok).toBe(true);
    expect(b.ok).toBe(true);
  });

  it('never lets one owner read, update, or delete another owner\'s view', async () => {
    const created = await createSavedView(supabase, OWNER_A, { name: "Owner A's view" });
    expect(created.ok).toBe(true);
    if (!created.ok) return;
    const viewId = created.data.id;

    const bList = await listSavedViews(supabase, OWNER_B);
    expect(bList).toEqual({ ok: true, data: [] });

    const bUpdate = await updateSavedView(supabase, OWNER_B, viewId, { name: 'Hijacked' });
    expect(bUpdate).toMatchObject({ ok: false, error: 'not_found' });

    const bDelete = await deleteSavedView(supabase, OWNER_B, viewId);
    expect(bDelete).toMatchObject({ ok: false, error: 'not_found' });

    // Untouched from owner A's perspective.
    const aList = await listSavedViews(supabase, OWNER_A);
    expect(aList.ok).toBe(true);
    if (aList.ok) expect(aList.data[0].name).toBe("Owner A's view");
  });

  it('updates filters/sort and rejects a stale/invalid patch', async () => {
    const created = await createSavedView(supabase, OWNER_A, { name: 'v1' });
    if (!created.ok) throw new Error('setup failed');

    const updated = await updateSavedView(supabase, OWNER_A, created.data.id, {
      filters: { status: 'purchased' },
      sort: { field: 'cost', direction: 'desc' },
    });
    expect(updated.ok).toBe(true);
    if (updated.ok) {
      expect(updated.data.filters).toEqual({ status: 'purchased' });
      expect(updated.data.sort).toEqual({ field: 'cost', direction: 'desc' });
    }

    const invalid = await updateSavedView(supabase, OWNER_A, created.data.id, { sort: { direction: 'diagonal' } as never });
    expect(invalid).toMatchObject({ ok: false, error: 'invalid_input' });

    const noFields = await updateSavedView(supabase, OWNER_A, created.data.id, {});
    expect(noFields).toMatchObject({ ok: false, error: 'invalid_input' });
  });

  it('select() enforces exactly one default per owner', async () => {
    const a = await createSavedView(supabase, OWNER_A, { name: 'A' });
    const b = await createSavedView(supabase, OWNER_A, { name: 'B' });
    if (!a.ok || !b.ok) throw new Error('setup failed');

    const selectA = await selectSavedView(supabase, OWNER_A, a.data.id);
    expect(selectA.ok).toBe(true);
    if (selectA.ok) expect(selectA.data.is_default).toBe(true);

    const selectB = await selectSavedView(supabase, OWNER_A, b.data.id);
    expect(selectB.ok).toBe(true);

    const list = await listSavedViews(supabase, OWNER_A);
    expect(list.ok).toBe(true);
    if (list.ok) {
      const defaults = list.data.filter((v) => v.is_default);
      expect(defaults).toHaveLength(1);
      expect(defaults[0].id).toBe(b.data.id);
    }
  });

  it('select() on a nonexistent id returns not_found, not a silent no-op', async () => {
    const result = await selectSavedView(supabase, OWNER_A, 'no-such-id');
    expect(result).toMatchObject({ ok: false, error: 'not_found' });
  });

  it('duplicates a view with a non-colliding name and never as default', async () => {
    const original = await createSavedView(supabase, OWNER_A, { name: 'Original', filters: { category: 'books' }, is_default: true });
    if (!original.ok) throw new Error('setup failed');

    const dup1 = await duplicateSavedView(supabase, OWNER_A, original.data.id);
    expect(dup1.ok).toBe(true);
    if (dup1.ok) {
      expect(dup1.data.name).toBe('Original (copy)');
      expect(dup1.data.filters).toEqual({ category: 'books' });
      expect(dup1.data.is_default).toBe(false);
    }

    const dup2 = await duplicateSavedView(supabase, OWNER_A, original.data.id);
    expect(dup2.ok).toBe(true);
    if (dup2.ok) expect(dup2.data.name).toBe('Original (copy 2)');
  });

  it('reports unavailable, not a fabricated result, when the backend errors', async () => {
    const brokenSupabase = {
      from() {
        throw new Error('connection refused');
      },
    } as any;
    await expect(listSavedViews(brokenSupabase, OWNER_A)).rejects.toThrow();
    // Route handlers catch this — listSavedViews itself only wraps
    // PostgrestError-shaped {data, error} results, not thrown exceptions,
    // matching every other lib function in this file (createSavedView
    // wraps its own try/catch since insert() awaits before erroring here;
    // listSavedViews' query build itself can throw synchronously on a
    // truly broken client, which is exactly what this asserts).
  });
});