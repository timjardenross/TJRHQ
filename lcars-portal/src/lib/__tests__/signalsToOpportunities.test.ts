import { describe, it, expect, vi } from 'vitest';
import { buildOpportunityRows, createOpportunitiesFromSignals, type SignalRow } from '@/lib/signalsToOpportunities';

// ── buildOpportunityRows (pure) ─────────────────────────────────────────────

function signal(overrides: Partial<SignalRow> = {}): SignalRow {
  return {
    id: 'signal-1',
    event_id_text: 'evt-1',
    raw_title: 'Team wellness initiative reduced absenteeism 15%',
    pillar_key: 'wellness_sustainable_performance',
    rank_score: 0.85,
    domain: 'health',
    suggested_angle: 'A 15% drop in absenteeism worth writing about',
    ...overrides,
  };
}

describe('buildOpportunityRows', () => {
  it('builds one row per valid signal with domain-default format', () => {
    const { rows, errors, signalIds } = buildOpportunityRows([signal(), signal({ id: 's2', event_id_text: 'evt-2', domain: 'operational' })]);
    expect(errors).toEqual([]);
    expect(rows).toHaveLength(2);
    expect(rows[0].format).toBe('case_study');
    expect(rows[1].format).toBe('executive_insight');
    expect(signalIds).toEqual(['evt-1', 'evt-2']);
  });

  it('flags a signal missing raw_title as an error and excludes it from rows', () => {
    const { rows, errors } = buildOpportunityRows([signal({ raw_title: null })]);
    expect(rows).toEqual([]);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toContain('missing raw_title');
  });

  it('flags a signal missing event_id_text as an error', () => {
    const { rows, errors } = buildOpportunityRows([signal({ event_id_text: null })]);
    expect(rows).toEqual([]);
    expect(errors).toHaveLength(1);
  });

  it('falls back to executive_insight format for an unrecognised domain', () => {
    const { rows } = buildOpportunityRows([signal({ domain: 'unknown' })]);
    expect(rows[0].format).toBe('executive_insight');
  });
});

// ── createOpportunitiesFromSignals (mocked Supabase) ────────────────────────
// Mirrors decide.test.ts's approach: mock at the from()/select()/insert()
// boundary so assertions can check exactly what was queried/written, without
// a real database.

function mockSupabase({
  signals,
  fetchError = null,
  insertResult,
}: {
  signals: SignalRow[] | null;
  fetchError?: { message: string } | null;
  insertResult?: { data: { id: string }[] | null; error: { message: string } | null };
}) {
  const selectCalls: string[] = [];
  const filters: Record<string, unknown>[] = [];
  const insertCalls: unknown[][] = [];

  function chain() {
    const self: any = {
      eq: vi.fn((col: string, val: unknown) => { filters.push({ eq: [col, val] }); return self; }),
      in: vi.fn((col: string, val: unknown) => { filters.push({ in: [col, val] }); return self; }),
      gte: vi.fn((col: string, val: unknown) => { filters.push({ gte: [col, val] }); return self; }),
      order: vi.fn(() => self),
      limit: vi.fn(() => self),
      then: (resolve: (v: unknown) => void) => resolve({ data: signals, error: fetchError }),
    };
    return self;
  }

  const fromMock = vi.fn((table: string) => ({
    select: (cols: string) => { selectCalls.push(cols); return chain(); },
    insert: (rows: unknown[]) => {
      insertCalls.push(rows);
      return { select: () => Promise.resolve(insertResult ?? { data: [], error: null }) };
    },
  }));

  return { from: fromMock, _insertCalls: insertCalls, _filters: filters };
}

describe('createOpportunitiesFromSignals', () => {
  it('returns no_signals when nothing matches', async () => {
    const sb = mockSupabase({ signals: [] });
    const result = await createOpportunitiesFromSignals(sb, { domain: 'health' });
    expect(result.status).toBe('no_signals');
    expect(result.created).toBe(0);
  });

  it('creates all opportunities for a valid batch (top-N flow)', async () => {
    const signals = [signal({ event_id_text: 'evt-1' }), signal({ id: 's2', event_id_text: 'evt-2' })];
    const sb = mockSupabase({
      signals,
      insertResult: { data: [{ id: 'opp-1' }, { id: 'opp-2' }], error: null },
    });
    const result = await createOpportunitiesFromSignals(sb, { limit: 5, minRankScore: 0.7, domain: 'health' });
    expect(result.status).toBe('completed');
    expect(result.created).toBe(2);
    expect(result.opportunity_ids).toEqual(['opp-1', 'opp-2']);
  });

  it('rolls back entirely when the insert fails — 0 created', async () => {
    const signals = [signal()];
    const sb = mockSupabase({
      signals,
      insertResult: { data: null, error: { message: 'constraint violation' } },
    });
    const result = await createOpportunitiesFromSignals(sb, { domain: 'health' });
    expect(result.status).toBe('failed');
    expect(result.created).toBe(0);
    expect(result.opportunity_ids).toEqual([]);
    expect(result.error).toContain('rolled back');
  });

  it('aborts the whole batch before insert when one signal is invalid', async () => {
    const signals = [signal(), signal({ id: 's2', event_id_text: null })];
    const sb = mockSupabase({ signals });
    const result = await createOpportunitiesFromSignals(sb, { domain: 'health' });
    expect(result.status).toBe('failed');
    expect(result.created).toBe(0);
    expect(sb._insertCalls).toHaveLength(0); // insert must never be attempted
  });

  it('honours explicit signal_ids over the top-N default', async () => {
    const signals = [signal({ event_id_text: 'evt-9' })];
    const sb = mockSupabase({ signals, insertResult: { data: [{ id: 'opp-9' }], error: null } });
    const result = await createOpportunitiesFromSignals(sb, { signalIds: ['evt-9'] });
    expect(sb._filters.some((f: any) => f.in?.[0] === 'event_id_text')).toBe(true);
    expect(sb._filters.some((f: any) => f.gte)).toBe(false); // min-rank-score path not used
    expect(result.status).toBe('completed');
    expect(result.created).toBe(1);
  });

  it('fails closed when a selected signal is no longer eligible', async () => {
    // asked for 2 signal_ids, but only 1 comes back (the other was suppressed since page load)
    const sb = mockSupabase({ signals: [signal({ event_id_text: 'evt-1' })] });
    const result = await createOpportunitiesFromSignals(sb, { signalIds: ['evt-1', 'evt-2'] });
    expect(result.status).toBe('failed');
    expect(result.created).toBe(0);
    expect(result.error).toContain('no longer eligible');
  });

  it('applies the domain filter on the top-N path', async () => {
    const sb = mockSupabase({ signals: [] });
    await createOpportunitiesFromSignals(sb, { domain: 'operational' });
    expect(sb._filters.some((f: any) => f.eq?.[0] === 'domain' && f.eq?.[1] === 'operational')).toBe(true);
  });
});
