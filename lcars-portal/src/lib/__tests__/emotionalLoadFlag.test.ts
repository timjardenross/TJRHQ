import { describe, it, expect, vi, beforeEach } from 'vitest';

// MSN-0355: the Emotional Load Flag previously read ONLY analytics_health_daily,
// which stopped receiving rows after 2026-06-28 while recovery_pulses kept being
// actively written (multiple pulses/day via Telegram). Because an empty result
// set was never distinguished from a genuinely calm one, the flag silently read
// "Clear" while real dysregulated pulses on 2026-07-01 and 2026-07-03 went
// unread. These tests lock in the merged-source, worst-of-day, honest-omission
// fix using shapes taken directly from the live data (verified via Supabase MCP
// during this mission).

type TableRow = Record<string, unknown>;
const tableData: Record<string, { data: TableRow[]; error: unknown }> = {};

function setTable(table: string, data: TableRow[], error: unknown = null) {
  tableData[table] = { data, error };
}

function makeChain(table: string) {
  const resolve = () => Promise.resolve(tableData[table] ?? { data: [], error: null });
  const chain: {
    select: () => typeof chain;
    gte: () => typeof chain;
    lte: () => typeof chain;
    order: () => typeof chain;
    eq: () => typeof chain;
    then: (
      onFulfilled?: (v: { data: TableRow[]; error: unknown }) => unknown,
      onRejected?: (e: unknown) => unknown
    ) => Promise<unknown>;
  } = {
    select: () => chain,
    gte: () => chain,
    lte: () => chain,
    order: () => chain,
    eq: () => chain,
    then: (onFulfilled, onRejected) => resolve().then(onFulfilled, onRejected),
  };
  return chain;
}

vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({
    from: (table: string) => makeChain(table),
  }),
}));

import { fetchEmotionalLoadFlag } from '@/lib/ros-data';
import { checkinNsState, fetchHumanSystemsRowsWithStatus } from '@/lib/human-systems';

beforeEach(() => {
  setTable('analytics_health_daily', []);
  setTable('capacity_checkins', []);
  setTable('human_systems_daily', []);
});

describe('checkinNsState — direct regulation_state mapping (no stress-derived fallback)', () => {
  it('maps overloaded to dysregulated', () => {
    expect(checkinNsState({ regulation_state: 'overloaded' })).toBe('dysregulated');
  });

  it('maps both settled and manageable to calm', () => {
    expect(checkinNsState({ regulation_state: 'settled' })).toBe('calm');
    expect(checkinNsState({ regulation_state: 'manageable' })).toBe('calm');
  });

  it('maps activated to activated', () => {
    expect(checkinNsState({ regulation_state: 'activated' })).toBe('activated');
  });

  it('returns null when regulation_state is null (does not crash on nulls)', () => {
    expect(checkinNsState({ regulation_state: null })).toBeNull();
  });
});

describe('fetchEmotionalLoadFlag — honest merge of analytics_health_daily + capacity_checkins', () => {
  it('returns noRecentData:true (not a false "Clear") when both sources are empty', async () => {
    const flag = await fetchEmotionalLoadFlag();
    expect(flag).not.toBeNull();
    expect(flag!.noRecentData).toBe(true);
    expect(flag!.raised).toBe(false);
    expect(flag!.recorded_days).toBe(0);
    expect(flag!.message).toMatch(/no nervous-system signal/i);
  });

  it('surfaces real dysregulated capacity_checkins that analytics_health_daily never captured (2026-07-01 / 2026-07-03 shape)', async () => {
    // analytics_health_daily has nothing for this window — mirrors the live
    // gap confirmed after 2026-06-28.
    setTable('analytics_health_daily', []);
    // capacity_checkins shaped like the live rows for these two dates:
    // multiple check-ins/day, several distinct regulation_state readings per
    // day.
    setTable('capacity_checkins', [
      { log_date: '2026-07-01', regulation_state: 'overloaded' },
      { log_date: '2026-07-01', regulation_state: 'overloaded' },
      { log_date: '2026-07-01', regulation_state: 'overloaded' },
      { log_date: '2026-07-01', regulation_state: 'overloaded' },
      { log_date: '2026-07-03', regulation_state: 'settled' },
      { log_date: '2026-07-03', regulation_state: 'overloaded' },
      { log_date: '2026-07-03', regulation_state: 'overloaded' },
      { log_date: '2026-07-03', regulation_state: 'settled' }, // resolves to 'calm' directly
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag).not.toBeNull();
    expect(flag!.noRecentData).toBe(false);
    expect(flag!.recorded_days).toBe(2);
    // Worst-of-day: both days had at least one dysregulated pulse, so both
    // count as dysregulated even though 07-03 also had calm pulses.
    expect(flag!.dysregulated_days).toBe(2);
    expect(flag!.activated_days).toBe(0);
  });

  it('raises when 3+ of the recorded days are activated/dysregulated', async () => {
    setTable('analytics_health_daily', []);
    setTable('capacity_checkins', [
      { log_date: '2026-07-03', regulation_state: 'overloaded' },
      { log_date: '2026-07-04', regulation_state: 'activated' },
      { log_date: '2026-07-05', regulation_state: 'overloaded' },
      { log_date: '2026-07-07', regulation_state: 'overloaded' },
      { log_date: '2026-07-09', regulation_state: 'activated' },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag!.raised).toBe(true);
    expect(flag!.dysregulated_days).toBe(3);
    expect(flag!.activated_days).toBe(2);
    expect(flag!.recorded_days).toBe(5);
    expect(flag!.noRecentData).toBe(false);
  });

  it('does not silently prefer one table — an analytics_health_daily-only day still counts', async () => {
    setTable('analytics_health_daily', [
      { log_date: '2026-06-27', nervous_system_state: 'dysregulated' },
    ]);
    setTable('capacity_checkins', [
      { log_date: '2026-06-28', regulation_state: 'activated' },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag!.recorded_days).toBe(2);
    expect(flag!.dysregulated_days).toBe(1);
    expect(flag!.activated_days).toBe(1);
  });

  it('a capacity_checkins row overrides a calmer analytics_health_daily reading for the same day (worst wins)', async () => {
    setTable('analytics_health_daily', [
      { log_date: '2026-07-03', nervous_system_state: 'calm' },
    ]);
    setTable('capacity_checkins', [
      { log_date: '2026-07-03', regulation_state: 'overloaded' },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag!.dysregulated_days).toBe(1);
    expect(flag!.activated_days).toBe(0);
  });

  it('does not crash on check-ins with every optional field null', async () => {
    setTable('analytics_health_daily', []);
    setTable('capacity_checkins', [
      { log_date: '2026-06-30', regulation_state: null },
      { log_date: '2026-06-30', regulation_state: null },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag).not.toBeNull();
    expect(flag!.noRecentData).toBe(true);
    expect(flag!.recorded_days).toBe(0);
  });

  it('a genuinely calm week with recorded data reads as Clear, not no-data', async () => {
    setTable('analytics_health_daily', []);
    setTable('capacity_checkins', [
      { log_date: '2026-07-05', regulation_state: 'settled' },
      { log_date: '2026-07-06', regulation_state: 'settled' },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag!.noRecentData).toBe(false);
    expect(flag!.raised).toBe(false);
    expect(flag!.recorded_days).toBe(2);
    expect(flag!.message).toMatch(/within expected range/i);
  });

  it('returns null (fetch failure) when a query genuinely errors — distinct from empty data', async () => {
    setTable('analytics_health_daily', [], { message: 'network error' });
    setTable('capacity_checkins', []);
    const flag = await fetchEmotionalLoadFlag();
    expect(flag).toBeNull();
  });
});

describe('fetchHumanSystemsRowsWithStatus — real regulation_state flows into merged rows', () => {
  it('prefers the real check-in regulation_state over the human_systems_daily log value', async () => {
    setTable('human_systems_daily', [
      { log_date: '2026-07-01', nervous_system_state: 'calm' },
    ]);
    setTable('capacity_checkins', [
      { log_date: '2026-07-01', captured_at: '2026-07-01T08:49:41Z', regulation_state: 'overloaded' },
    ]);

    const { rows } = await fetchHumanSystemsRowsWithStatus(7);
    const row = rows.find((r) => r.log_date === '2026-07-01');
    expect(row?.nervous_system_state).toBe('dysregulated');
  });

  it('resolves to calm when the check-in reports a settled regulation_state (no log row present)', async () => {
    setTable('human_systems_daily', []);
    setTable('capacity_checkins', [
      { log_date: '2026-07-03', captured_at: '2026-07-03T10:15:00Z', regulation_state: 'settled' },
    ]);

    const { rows } = await fetchHumanSystemsRowsWithStatus(7);
    const row = rows.find((r) => r.log_date === '2026-07-03');
    expect(row?.nervous_system_state).toBe('calm');
  });
});
