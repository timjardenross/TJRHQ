import { describe, it, expect } from 'vitest';
import { assembleChanges, composeChangeText } from '@/lib/changeAssembly';

// Generic chainable thenable matching Supabase's query-builder shape - every
// chain method returns the same object, and awaiting it resolves `result`.
function chain(result: { data: unknown[] | null; count?: number } | Promise<never>) {
  const isRejection = result instanceof Promise;
  const obj: Record<string, unknown> = {
    select: () => obj,
    eq: () => obj,
    gte: () => obj,
    not: () => obj,
    or: () => obj,
    order: () => obj,
    limit: () => obj,
    then: (resolve: (v: unknown) => void, reject: (e: unknown) => void) =>
      isRejection ? (result as Promise<never>).then(resolve, reject) : Promise.resolve(result).then(resolve, reject),
  };
  return obj;
}

function fakeSupabase(byTable: Record<string, { data: unknown[] | null; count?: number } | Promise<never>>) {
  return { from: (table: string) => chain(byTable[table] ?? { data: [], count: 0 }) } as never;
}

const SINCE = '2026-07-08T00:00:00Z';

describe('assembleChanges', () => {
  it('returns no clauses and no unchecked domains when every table is quiet', async () => {
    const result = await assembleChanges(fakeSupabase({}), SINCE);
    expect(result.clauses).toEqual([]);
    expect(result.uncheckedDomains).toEqual([]);
  });

  it('produces a clause for a domain with real activity', async () => {
    const supabase = fakeSupabase({
      missions: { data: [{ title: 'Fix the thing', closed_at: SINCE }], count: 1 },
    });
    const result = await assembleChanges(supabase, SINCE);
    const missionsClause = result.clauses.find((c) => c.domain === 'Missions');
    expect(missionsClause?.text).toBe('Mission completed: Fix the thing.');
  });

  it('records a domain as unchecked, never silently drops it, when its query fails', async () => {
    const supabase = fakeSupabase({ missions: Promise.reject(new Error('down')) });
    const result = await assembleChanges(supabase, SINCE);
    expect(result.uncheckedDomains).toContain('Missions');
  });

  it('never uses health_insights.summary for the health clause', async () => {
    const supabase = fakeSupabase({
      health_daily_logs: {
        data: [
          { pain_score: 6, logged_at: '2026-07-08T08:00:00Z' },
          { pain_score: 3, logged_at: '2026-07-08T20:00:00Z' },
        ],
        count: 2,
      },
    });
    const result = await assembleChanges(supabase, SINCE);
    const health = result.clauses.find((c) => c.domain === 'Health');
    expect(health?.text).toBe('Pain trending down over your last 2 entries.');
  });

  it('contributes nothing for health with fewer than 2 pain_score entries needed for a trend, but still reports the single entry', async () => {
    const supabase = fakeSupabase({
      health_daily_logs: { data: [{ pain_score: 4, logged_at: SINCE }], count: 1 },
    });
    const result = await assembleChanges(supabase, SINCE);
    const health = result.clauses.find((c) => c.domain === 'Health');
    expect(health?.text).toBe('1 health log entry recorded.');
  });
});

describe('composeChangeText', () => {
  it('is honest about nothing changing', () => {
    expect(composeChangeText({ clauses: [], uncheckedDomains: [] })).toBe('Nothing notable changed since your last session.');
  });

  it('discloses it could not fully check when nothing changed but a domain failed', () => {
    expect(composeChangeText({ clauses: [], uncheckedDomains: ['Missions'] })).toBe(
      'Nothing notable changed since your last session, as far as I could check.'
    );
  });

  it('caps at the top 4 clauses by count and discloses the rest', () => {
    const clauses = Array.from({ length: 6 }, (_, i) => ({
      domain: `Domain${i}`,
      text: `Domain ${i} changed.`,
      count: 6 - i,
      latest: null,
    }));
    const text = composeChangeText({ clauses, uncheckedDomains: [] });
    expect(text).toContain('Domain 0 changed.');
    expect(text).toContain('(2 more sources also had activity.)');
    expect(text).not.toContain('Domain 5 changed.');
  });

  it('discloses unchecked domains alongside real clauses', () => {
    const text = composeChangeText({
      clauses: [{ domain: 'Missions', text: 'Mission completed: X.', count: 1, latest: null }],
      uncheckedDomains: ['Health'],
    });
    expect(text).toContain("I couldn't check Health just now.");
  });
});
