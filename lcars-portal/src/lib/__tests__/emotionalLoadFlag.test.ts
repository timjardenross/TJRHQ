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

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: (table: string) => makeChain(table),
  },
}));

import { fetchEmotionalLoadFlag } from '@/lib/ros-data';
import { pulseNsState, fetchHumanSystemsRowsWithStatus } from '@/lib/human-systems';

beforeEach(() => {
  setTable('analytics_health_daily', []);
  setTable('recovery_pulses', []);
  setTable('human_systems_daily', []);
});

describe('pulseNsState — real signal takes priority over the stress heuristic', () => {
  it('uses the real nervous_system value when present', () => {
    expect(pulseNsState({ nervous_system: 'dysregulated', stress: 'low' })).toBe('dysregulated');
  });

  it('falls back to the stress-derived heuristic only when nervous_system is null', () => {
    expect(pulseNsState({ nervous_system: null, stress: 'low' })).toBe('calm');
    expect(pulseNsState({ nervous_system: null, stress: 'moderate' })).toBe('activated');
    expect(pulseNsState({ nervous_system: null, stress: 'high' })).toBe('dysregulated');
  });

  it('returns null when both are null (does not crash on nulls)', () => {
    expect(pulseNsState({ nervous_system: null, stress: null })).toBeNull();
  });
});

describe('fetchEmotionalLoadFlag — honest merge of analytics_health_daily + recovery_pulses', () => {
  it('returns noRecentData:true (not a false "Clear") when both sources are empty', async () => {
    const flag = await fetchEmotionalLoadFlag();
    expect(flag).not.toBeNull();
    expect(flag!.noRecentData).toBe(true);
    expect(flag!.raised).toBe(false);
    expect(flag!.recorded_days).toBe(0);
    expect(flag!.message).toMatch(/no nervous-system signal/i);
  });

  it('surfaces real dysregulated recovery_pulses that analytics_health_daily never captured (2026-07-01 / 2026-07-03 shape)', async () => {
    // analytics_health_daily has nothing for this window — mirrors the live
    // gap confirmed after 2026-06-28.
    setTable('analytics_health_daily', []);
    // recovery_pulses shaped exactly like the live rows for these two dates:
    // multiple pulses/day, several distinct nervous_system readings per day,
    // some with stress instead, some with neither.
    setTable('recovery_pulses', [
      { log_date: '2026-07-01', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-01', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-01', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-01', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-03', nervous_system: 'calm', stress: null },
      { log_date: '2026-07-03', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-03', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-03', nervous_system: null, stress: 'low' }, // stress-derived 'calm'
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
    setTable('recovery_pulses', [
      { log_date: '2026-07-03', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-04', nervous_system: 'activated', stress: null },
      { log_date: '2026-07-05', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-07', nervous_system: 'dysregulated', stress: null },
      { log_date: '2026-07-09', nervous_system: 'activated', stress: null },
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
    setTable('recovery_pulses', [
      { log_date: '2026-06-28', nervous_system: 'activated', stress: null },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag!.recorded_days).toBe(2);
    expect(flag!.dysregulated_days).toBe(1);
    expect(flag!.activated_days).toBe(1);
  });

  it('a recovery_pulses row overrides a calmer analytics_health_daily reading for the same day (worst wins)', async () => {
    setTable('analytics_health_daily', [
      { log_date: '2026-07-03', nervous_system_state: 'calm' },
    ]);
    setTable('recovery_pulses', [
      { log_date: '2026-07-03', nervous_system: 'dysregulated', stress: null },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag!.dysregulated_days).toBe(1);
    expect(flag!.activated_days).toBe(0);
  });

  it('does not crash on pulses with every optional field null', async () => {
    setTable('analytics_health_daily', []);
    setTable('recovery_pulses', [
      { log_date: '2026-06-30', nervous_system: null, stress: null },
      { log_date: '2026-06-30', nervous_system: null, stress: null },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag).not.toBeNull();
    expect(flag!.noRecentData).toBe(true);
    expect(flag!.recorded_days).toBe(0);
  });

  it('a genuinely calm week with recorded data reads as Clear, not no-data', async () => {
    setTable('analytics_health_daily', []);
    setTable('recovery_pulses', [
      { log_date: '2026-07-05', nervous_system: 'calm', stress: null },
      { log_date: '2026-07-06', nervous_system: 'calm', stress: null },
    ]);

    const flag = await fetchEmotionalLoadFlag();
    expect(flag!.noRecentData).toBe(false);
    expect(flag!.raised).toBe(false);
    expect(flag!.recorded_days).toBe(2);
    expect(flag!.message).toMatch(/within expected range/i);
  });

  it('returns null (fetch failure) when a query genuinely errors — distinct from empty data', async () => {
    setTable('analytics_health_daily', [], { message: 'network error' });
    setTable('recovery_pulses', []);
    const flag = await fetchEmotionalLoadFlag();
    expect(flag).toBeNull();
  });
});

describe('fetchHumanSystemsRowsWithStatus — real nervous_system flows into merged rows', () => {
  it('prefers the real pulse nervous_system over stress-derived and log value', async () => {
    setTable('human_systems_daily', [
      { log_date: '2026-07-01', nervous_system_state: 'calm' },
    ]);
    setTable('recovery_pulses', [
      { log_date: '2026-07-01', captured_at: '2026-07-01T08:49:41Z', nervous_system: 'dysregulated', stress: null },
    ]);

    const { rows } = await fetchHumanSystemsRowsWithStatus(7);
    const row = rows.find((r) => r.log_date === '2026-07-01');
    expect(row?.nervous_system_state).toBe('dysregulated');
  });

  it('falls back to stress-derived state when the pulse has no real nervous_system reading', async () => {
    setTable('human_systems_daily', []);
    setTable('recovery_pulses', [
      { log_date: '2026-07-03', captured_at: '2026-07-03T10:15:00Z', nervous_system: null, stress: 'low' },
    ]);

    const { rows } = await fetchHumanSystemsRowsWithStatus(7);
    const row = rows.find((r) => r.log_date === '2026-07-03');
    expect(row?.nervous_system_state).toBe('calm');
  });
});
