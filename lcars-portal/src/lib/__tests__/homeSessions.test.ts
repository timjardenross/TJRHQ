import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { recordAndGetLastSession } from '@/lib/homeSessions';

// Pinned away from any UTC midnight boundary - homeSessions.ts compares
// calendar days via local Date fields, so a real-wall-clock "1 hour ago"
// lands on the previous calendar day for the ~4% of the day within an
// hour of midnight (a real CI run hit this at 2026-09-01T00:11Z). Fixing
// the clock makes every test in this file deterministic regardless of
// run time.
const FIXED_NOW = new Date('2026-06-15T12:00:00.000Z');

// Chainable fake matching the Supabase query-builder shape used by
// homeSessions.ts: .select().order().limit() resolves to {data}.
function fakeSupabase(selectResult: { data: unknown[] | null } | null, opts?: { insertThrows?: boolean }) {
  const insert = vi.fn().mockImplementation(() => {
    if (opts?.insertThrows) return Promise.reject(new Error('insert failed'));
    return Promise.resolve({ data: null, error: null });
  });
  const chain = {
    select: () => chain,
    order: () => chain,
    limit: () => Promise.resolve(selectResult ?? { data: null }),
  };
  return { from: () => ({ ...chain, insert }) } as never;
}

describe('recordAndGetLastSession', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FIXED_NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reports first-ever session when no prior row exists', async () => {
    const result = await recordAndGetLastSession(fakeSupabase({ data: [] }));
    expect(result.lastViewedAt).toBeNull();
    expect(result.isFirstSessionToday).toBe(true);
    expect(result.daysSinceLastSession).toBeNull();
  });

  it('reports same-day when the prior visit was earlier today', async () => {
    const earlier = new Date(FIXED_NOW.getTime() - 60 * 60 * 1000).toISOString();
    const result = await recordAndGetLastSession(fakeSupabase({ data: [{ viewed_at: earlier }] }));
    expect(result.daysSinceLastSession).toBe(0);
    expect(result.isFirstSessionToday).toBe(false);
  });

  it('reports 1 day and isFirstSessionToday when the prior visit was yesterday', async () => {
    const yesterday = new Date(FIXED_NOW);
    yesterday.setDate(yesterday.getDate() - 1);
    const result = await recordAndGetLastSession(fakeSupabase({ data: [{ viewed_at: yesterday.toISOString() }] }));
    expect(result.daysSinceLastSession).toBe(1);
    expect(result.isFirstSessionToday).toBe(true);
  });

  it('reports multi-day gaps for a long absence', async () => {
    const longAgo = new Date(FIXED_NOW);
    longAgo.setDate(longAgo.getDate() - 5);
    const result = await recordAndGetLastSession(fakeSupabase({ data: [{ viewed_at: longAgo.toISOString() }] }));
    expect(result.daysSinceLastSession).toBe(5);
  });

  it('degrades to first-ever, never throws, when the read fails', async () => {
    const supabase = { from: () => ({ select: () => ({ order: () => ({ limit: () => Promise.reject(new Error('down')) }) }) }) } as never;
    const result = await recordAndGetLastSession(supabase);
    expect(result.lastViewedAt).toBeNull();
  });

  it('does not throw when the write fails - a failed session write must not block Home', async () => {
    await expect(recordAndGetLastSession(fakeSupabase({ data: [] }, { insertThrows: true }))).resolves.toBeDefined();
  });
});
