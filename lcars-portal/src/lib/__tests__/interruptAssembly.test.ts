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

function rpcChain(result: { data: unknown } | Promise<never>) {
  const isRejection = result instanceof Promise;
  const obj: Record<string, unknown> = {
    select: () => obj,
    single: () => obj,
    then: (resolve: (v: unknown) => void, reject: (e: unknown) => void) =>
      isRejection ? (result as Promise<never>).then(resolve, reject) : Promise.resolve(result).then(resolve, reject),
  };
  return obj;
}

function fakeSupabase(
  byTable: Record<string, { data: unknown[] | null; count?: number } | Promise<never>> = {},
  byRpc: Record<string, { data: unknown } | Promise<never>> = {},
) {
  return {
    from: (table: string) => chain(byTable[table] ?? { data: [] }),
    rpc: (fn: string) => rpcChain(byRpc[fn] ?? { data: null }),
  } as never;
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

  // alerts.ts reconciliation (EOS Canonical Architecture Decisions §1) —
  // recoveryPostureNominator, recoveryEscalationNominator, painTrendNominator,
  // deliveryBlockedNominator, failedDispatchNominator, engineeringReviewNominator.

  it('nominates a recovery-posture interrupt when the RPC reports REST', async () => {
    const supabase = fakeSupabase(
      {},
      { get_recovery_posture: { data: { posture: 'REST', posture_message: 'Minimal capacity today.' } } },
    );
    const result = await assembleInterrupts(supabase);
    const posture = result.interrupts.find((i) => i.domain === 'Recovery posture');
    expect(posture?.text).toBe('Minimal capacity today.');
  });

  it('does not nominate a recovery-posture interrupt for a non-REST band', async () => {
    const supabase = fakeSupabase(
      {},
      { get_recovery_posture: { data: { posture: 'STABLE', posture_message: 'Steady.' } } },
    );
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Recovery posture')).toBeUndefined();
  });

  it('marks Recovery posture unchecked when the RPC fails', async () => {
    const supabase = fakeSupabase({}, { get_recovery_posture: Promise.reject(new Error('down')) });
    const result = await assembleInterrupts(supabase);
    expect(result.uncheckedDomains).toContain('Recovery posture');
  });

  it('nominates a recovery-escalation interrupt when the latest pulse notes carry a real red flag', async () => {
    const supabase = fakeSupabase({
      recovery_pulses: {
        data: [{ notes: 'chest pain and cannot breathe', captured_at: '2026-07-09T08:00:00Z' }],
      },
    });
    const result = await assembleInterrupts(supabase);
    const escalation = result.interrupts.find((i) => i.domain === 'Recovery escalation');
    expect(escalation).toBeDefined();
    expect(escalation?.evidenceAt).toBe('2026-07-09T08:00:00Z');
  });

  it('does not nominate a recovery-escalation interrupt when the red-flag phrase is negated', async () => {
    const supabase = fakeSupabase({
      recovery_pulses: { data: [{ notes: 'no chest pain today', captured_at: '2026-07-09T08:00:00Z' }] },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Recovery escalation')).toBeUndefined();
  });

  it('nominates a pain-trend interrupt above the disclosed critical threshold (8)', async () => {
    const supabase = fakeSupabase({
      recovery_pulses: {
        data: [
          { pain_score: 9, captured_at: '2026-07-09T08:00:00Z' },
          { pain_score: 9, captured_at: '2026-07-08T08:00:00Z' },
        ],
      },
    });
    const result = await assembleInterrupts(supabase);
    const pain = result.interrupts.find((i) => i.domain === 'Recovery pain trend');
    expect(pain?.text).toContain('critically high');
  });

  it('does not nominate a pain-trend interrupt at or below the elevated threshold (6)', async () => {
    const supabase = fakeSupabase({
      recovery_pulses: { data: [{ pain_score: 4, captured_at: '2026-07-09T08:00:00Z' }] },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Recovery pain trend')).toBeUndefined();
  });

  it('nominates a delivery interrupt for a blocked mission_delivery row', async () => {
    const supabase = fakeSupabase({
      mission_delivery: { data: [{ title: 'Stalled build', delivery_state: 'blocked', age_days: 5 }] },
    });
    const result = await assembleInterrupts(supabase);
    const delivery = result.interrupts.find((i) => i.domain === 'Delivery');
    expect(delivery?.text).toContain('Stalled build');
    expect(delivery?.text).toContain('blocked');
  });

  it('does not nominate a delivery interrupt when the blocked query returns no rows', async () => {
    // mission_delivery's own eq('delivery_state', 'blocked') filter is what
    // does the real-world filtering; an empty result mirrors "nothing
    // blocked", the honest shape a passing query returns for that case.
    const supabase = fakeSupabase({ mission_delivery: { data: [] } });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Delivery')).toBeUndefined();
  });

  it('nominates a delivery-dispatch interrupt when failed dispatches exist in the last 3 days', async () => {
    const supabase = fakeSupabase({ mission_execution_events: { data: null, count: 2 } });
    const result = await assembleInterrupts(supabase);
    const dispatch = result.interrupts.find((i) => i.domain === 'Delivery dispatch');
    expect(dispatch?.text).toContain('2 mission dispatches failed');
  });

  it('does not nominate a delivery-dispatch interrupt when the failed count is zero', async () => {
    const supabase = fakeSupabase({ mission_execution_events: { data: null, count: 0 } });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Delivery dispatch')).toBeUndefined();
  });

  it('nominates an engineering-review interrupt for a P0/P1 mission_delivery row in_review', async () => {
    const supabase = fakeSupabase({
      mission_delivery: {
        data: [{ title: 'Critical fix', delivery_state: 'in_review', priority_norm: 'P0', pr_url: null }],
      },
    });
    const result = await assembleInterrupts(supabase);
    const review = result.interrupts.find((i) => i.domain === 'Engineering review');
    expect(review?.text).toContain('Critical fix');
    expect(review?.text).toContain('P0');
  });

  it('does not nominate an engineering-review interrupt for a P2 mission_delivery row in_review', async () => {
    const supabase = fakeSupabase({
      mission_delivery: {
        data: [{ title: 'Low priority', delivery_state: 'in_review', priority_norm: 'P2', pr_url: null }],
      },
    });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Engineering review')).toBeUndefined();
  });

  // MSN-0358: captured missions awaiting triage - resolves the file header's
  // own reconciliation note above (this file used to claim Decide already
  // covered this case; it doesn't - fetchDecideQueue()/fetchMissionDecisions()
  // never read captured_items).

  it('nominates a captured-missions interrupt when unreviewed captured missions exist', async () => {
    const supabase = fakeSupabase({ captured_items: { data: null, count: 3 } });
    const result = await assembleInterrupts(supabase);
    const captured = result.interrupts.find((i) => i.domain === 'Captured missions');
    expect(captured?.text).toContain('3 captured missions awaiting triage');
  });

  it('does not nominate a captured-missions interrupt when the unreviewed count is zero', async () => {
    const supabase = fakeSupabase({ captured_items: { data: null, count: 0 } });
    const result = await assembleInterrupts(supabase);
    expect(result.interrupts.find((i) => i.domain === 'Captured missions')).toBeUndefined();
  });

  it('marks Captured missions unchecked (never Sure) when its nominator query fails', async () => {
    const supabase = fakeSupabase({ captured_items: Promise.reject(new Error('down')) });
    const result = await assembleInterrupts(supabase);
    expect(result.uncheckedDomains).toContain('Captured missions');
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
