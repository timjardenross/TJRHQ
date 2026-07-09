import { describe, it, expect } from 'vitest';
import { assembleInterrupts, selectPrimaryInterrupt } from '@/lib/interruptAssembly';

function chain(result: { data: unknown[] | null } | Promise<never>) {
  const isRejection = result instanceof Promise;
  const obj: Record<string, unknown> = {
    select: () => obj,
    eq: () => obj,
    gte: () => obj,
    not: () => obj,
    in: () => obj,
    order: () => obj,
    limit: () => obj,
    then: (resolve: (v: unknown) => void, reject: (e: unknown) => void) =>
      isRejection ? (result as Promise<never>).then(resolve, reject) : Promise.resolve(result).then(resolve, reject),
  };
  return obj;
}

function fakeSupabase(byTable: Record<string, { data: unknown[] | null } | Promise<never>>) {
  return { from: (table: string) => chain(byTable[table] ?? { data: [] }) } as never;
}

describe('assembleInterrupts', () => {
  it('nominates nothing and is complete when every domain is quiet', async () => {
    const result = await assembleInterrupts(fakeSupabase({}));
    expect(result.interrupts).toEqual([]);
    expect(result.complete).toBe(true);
    expect(result.uncheckedDomains).toEqual([]);
  });

  it('nominates a health interrupt only when risk_flags is real and non-empty', async () => {
    const supabase = fakeSupabase({
      health_insights: { data: [{ risk_flags: ['elevated pain trend'], generated_at: '2026-07-08T10:00:00Z' }] },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts).toHaveLength(1);
    expect(result.interrupts[0].domain).toBe('Health');
  });

  it('does not nominate on empty risk_flags - the dormant real-world case', async () => {
    const supabase = fakeSupabase({
      health_insights: { data: [{ risk_flags: [], generated_at: '2026-07-08T10:00:00Z' }] },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts).toEqual([]);
  });

  it('nominates an intelligence event above the disclosed relevance threshold', async () => {
    const supabase = fakeSupabase({
      intelligence_events: {
        data: [{ raw_title: 'Major outage', published_at: '2026-07-08T09:00:00Z', operational_relevance: 0.95 }],
      },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts[0].text).toBe('Major outage.');
  });

  it('states the RED brief fact in Starship voice, never quoting the LLM bottom_line', async () => {
    const supabase = fakeSupabase({
      intelligence_briefs: { data: [{ generated_at: '2026-07-08T09:00:00Z', overall_risk: 'RED' }] },
    });
    const result = await assembleInterrupts(supabase);
    const brief = result.interrupts.find((i) => i.domain === 'Intelligence briefs');
    expect(brief?.text).toBe('The latest intelligence brief flagged elevated risk. Worth a look on the Intelligence page.');
  });

  it('marks a domain unchecked (never Sure) when its nominator query fails', async () => {
    const supabase = fakeSupabase({ health_insights: Promise.reject(new Error('down')) });
    const result = await assembleInterrupts(supabase);
    expect(result.uncheckedDomains).toContain('Health');
    expect(result.complete).toBe(false);
  });

  // MSN-0354: missions used to be entirely absent from this assembly - a real
  // P0 mission (MSN-LCARS-003, status='Designed') sat unnominated for 17
  // days. These cases pin the fix.
  it('nominates a P0 mission stuck in a non-terminal status past the 3-day threshold', async () => {
    const supabase = fakeSupabase({
      missions: {
        data: [
          {
            mission_id: 'MSN-LCARS-003',
            title: 'Data Provenance & Operational Trust Framework',
            status: 'Designed',
            priority: 'P0',
            created_at: '2026-06-22T12:53:24Z',
          },
        ],
      },
    });
    const result = await assembleInterrupts(supabase);
    const mission = result.interrupts.find((i) => i.domain === 'Missions');
    expect(mission?.text).toContain('P0 mission "Data Provenance & Operational Trust Framework"');
    expect(mission?.text).toContain('Designed');
  });

  it('does not nominate a P0 mission younger than the 3-day threshold', async () => {
    const supabase = fakeSupabase({
      missions: {
        data: [
          {
            mission_id: 'MSN-NEW',
            title: 'Brand new mission',
            status: 'Designed',
            priority: 'P0',
            created_at: new Date().toISOString(),
          },
        ],
      },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Missions')).toBeUndefined();
  });

  it('does not nominate a P1 mission until it clears the 7-day threshold', async () => {
    const fourDaysAgo = new Date(Date.now() - 4 * 86_400_000).toISOString();
    const eightDaysAgo = new Date(Date.now() - 8 * 86_400_000).toISOString();
    const stillYoung = fakeSupabase({
      missions: {
        data: [{ mission_id: 'MSN-P1-A', title: 'P1 young', status: 'Idea', priority: 'P1', created_at: fourDaysAgo }],
      },
    });
    expect((await assembleInterrupts(stillYoung)).interrupts.find((i) => i.domain === 'Missions')).toBeUndefined();

    const nowStale = fakeSupabase({
      missions: {
        data: [{ mission_id: 'MSN-P1-B', title: 'P1 stale', status: 'Idea', priority: 'P1', created_at: eightDaysAgo }],
      },
    });
    expect((await assembleInterrupts(nowStale)).interrupts.find((i) => i.domain === 'Missions')).toBeDefined();
  });

  it('never nominates a mission sitting in a terminal status, however old', async () => {
    const supabase = fakeSupabase({
      missions: {
        data: [
          {
            mission_id: 'MSN-OLD-CLOSED',
            title: 'Long since closed',
            status: 'Closed',
            priority: 'P0',
            created_at: '2020-01-01T00:00:00Z',
          },
        ],
      },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Missions')).toBeUndefined();
  });

  it('picks the single oldest qualifying mission when several are stale', async () => {
    const supabase = fakeSupabase({
      missions: {
        data: [
          {
            mission_id: 'MSN-OLDEST',
            title: 'Oldest stale mission',
            status: 'Designed',
            priority: 'P0',
            created_at: '2026-06-01T00:00:00Z',
          },
          {
            mission_id: 'MSN-NEWER',
            title: 'Newer stale mission',
            status: 'Designed',
            priority: 'P0',
            created_at: '2026-06-20T00:00:00Z',
          },
        ],
      },
    });
    const result = await assembleInterrupts(supabase);
    const mission = result.interrupts.find((i) => i.domain === 'Missions');
    expect(mission?.text).toContain('Oldest stale mission');
  });

  it('marks Missions unchecked (never Sure) when its nominator query fails', async () => {
    const supabase = fakeSupabase({ missions: Promise.reject(new Error('down')) });
    const result = await assembleInterrupts(supabase);
    expect(result.uncheckedDomains).toContain('Missions');
    expect(result.complete).toBe(false);
  });
});

describe('selectPrimaryInterrupt', () => {
  it('returns null when there are no interrupts', () => {
    expect(selectPrimaryInterrupt([])).toBeNull();
  });

  it('picks the most recent interrupt by evidence time', () => {
    const older = { domain: 'A', text: 'older', evidenceAt: '2026-07-01T00:00:00Z' };
    const newer = { domain: 'B', text: 'newer', evidenceAt: '2026-07-08T00:00:00Z' };
    expect(selectPrimaryInterrupt([older, newer])?.domain).toBe('B');
  });
});
