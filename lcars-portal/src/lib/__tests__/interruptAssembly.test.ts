import { describe, it, expect } from 'vitest';
import { assembleInterrupts, selectPrimaryInterrupt } from '@/lib/interruptAssembly';

function chain(result: { data: unknown[] | null } | Promise<never>) {
  const isRejection = result instanceof Promise;
  const obj: Record<string, unknown> = {
    select: () => obj,
    eq: () => obj,
    gte: () => obj,
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

  it('nominates a RED brief using its own plain-language bottom_line', async () => {
    const supabase = fakeSupabase({
      intelligence_briefs: {
        data: [{ bottom_line: 'Elevated risk from a third-party outage.', generated_at: '2026-07-08T09:00:00Z', overall_risk: 'RED' }],
      },
    });
    const result = await assembleInterrupts(supabase);
    const brief = result.interrupts.find((i) => i.domain === 'Intelligence briefs');
    expect(brief?.text).toBe('Elevated risk from a third-party outage.');
  });

  it('marks a domain unchecked (never Sure) when its nominator query fails', async () => {
    const supabase = fakeSupabase({ health_insights: Promise.reject(new Error('down')) });
    const result = await assembleInterrupts(supabase);
    expect(result.uncheckedDomains).toContain('Health');
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
