import { beforeEach, describe, expect, it, vi } from 'vitest';

// Compare-and-set guard added for HQ: a decision already made in another
// interface must never be silently overwritten or re-applied, and callers that
// do not opt in must behave exactly as before.
const eqCalls: [string, unknown][] = [];
let rowsUpdated: { id: string }[] = [{ id: 'row-1' }];
const insertSingle = vi.fn().mockResolvedValue({ data: { id: 'ledger-1' }, error: null });
const insertMock = vi.fn(() => ({ select: () => ({ single: insertSingle }) }));

function makeUpdateChain() {
  const chain: Record<string, unknown> = {};
  chain.eq = (col: string, val: unknown) => { eqCalls.push([col, val]); return chain; };
  chain.select = () => Promise.resolve({ data: rowsUpdated, error: null });
  return chain;
}
const fromMock = vi.fn((table: string) => ({
  insert: insertMock,
  update: () => makeUpdateChain(),
  _table: table,
}));
vi.mock('@/lib/supabase-browser', () => ({ createSupabaseBrowserClient: () => ({ from: fromMock }) }));

import { setQueueItemStatus, type QueueItem } from '@/lib/engineering-queue';
import { approveDecideItem, type DecideItem } from '@/lib/decide';

const q = { id: 'row-1', source: 'build' } as QueueItem;
const item: DecideItem = {
  id: 'eng:row-1', source: 'engineering', rawId: 'row-1', question: 'Approve build request "X"?', reasoning: 'r',
  domainTag: 'Engineering', undoAvailable: true, priorStatus: 'awaiting_review', actionType: null, _sortRank: 60,
};

beforeEach(() => { eqCalls.length = 0; rowsUpdated = [{ id: 'row-1' }]; vi.clearAllMocks(); vi.unstubAllGlobals(); });

describe('setQueueItemStatus guard', () => {
  it('without the guard it filters on id only (unchanged behaviour)', async () => {
    const r = await setQueueItemStatus(q, 'approved');
    expect(r.ok).toBe(true);
    expect(eqCalls).toEqual([['id', 'row-1']]);
  });
  it('with the guard it also requires the expected status', async () => {
    const r = await setQueueItemStatus(q, 'approved', 'awaiting_review');
    expect(r.ok).toBe(true);
    expect(eqCalls).toEqual([['id', 'row-1'], ['status', 'awaiting_review']]);
  });
  it('reports "already decided" when the row is no longer in that status', async () => {
    rowsUpdated = [];
    const r = await setQueueItemStatus(q, 'approved', 'awaiting_review');
    expect(r).toMatchObject({ ok: false, alreadyDecided: true });
  });
  it('keeps the old RLS message for an unguarded zero-row update', async () => {
    rowsUpdated = [];
    const r = await setQueueItemStatus(q, 'approved');
    expect(r.ok).toBe(false);
    expect(r.alreadyDecided).toBeUndefined();
    expect(r.error).toMatch(/RLS/);
  });
});

describe('approveDecideItem guard', () => {
  it('opt-in guard approves against the status the item was loaded with', async () => {
    const r = await approveDecideItem(item, { guardStatus: true });
    expect(r.ok).toBe(true);
    expect(eqCalls).toContainEqual(['status', 'awaiting_review']);
  });
  it('a second approval from another interface is rejected and writes NO ledger entry', async () => {
    rowsUpdated = [];
    const r = await approveDecideItem(item, { guardStatus: true });
    expect(r).toMatchObject({ ok: false, alreadyDecided: true, ledgerId: null });
    expect(insertMock).not.toHaveBeenCalled();
  });
  it('existing callers (no opts) still never add a status filter', async () => {
    await approveDecideItem(item);
    expect(eqCalls).toEqual([['id', 'row-1']]);
  });
  it('AI-proposed action: server 409 is surfaced as already decided (guarded only when opted in)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ error: 'Not eligible' }) }));
    const ai = { ...item, actionType: 'create_mission', undoAvailable: false };
    const guarded = await approveDecideItem(ai, { guardStatus: true });
    expect(guarded).toMatchObject({ ok: false, alreadyDecided: true });
    expect(insertMock).not.toHaveBeenCalled();
    insertMock.mockClear();
    // Legacy behaviour retained: an unguarded caller still records its ledger row.
    await approveDecideItem(ai);
    expect(insertMock).toHaveBeenCalled();
  });
});
