import { describe, it, expect } from 'vitest';
import { fetchStaleOkDomainKeys, fetchAgentStatusEntries } from '../agentStatusJobs';

// HQ V1 Integration QA §9/§10 (Deferred Gap I4) regression: a job that
// wrote 'ok' once and then silently stopped running must not report
// 'ok' forever. domain_heartbeat_latest (the pre-existing, singular view —
// migration 0071) computes is_stale against domain_registry's own
// expected_cadence_minutes/grace_period_minutes; a currently-'ok' job
// flagged is_stale there must be downgraded to 'unknown'.

function fakeStaleView(staleDomainKeys: Set<string>) {
  return {
    from: (table: string) => {
      if (table !== 'domain_heartbeat_latest') throw new Error(`unexpected table ${table}`);
      return {
        select: (_cols: string) => ({
          in: (_col: string, keys: string[]) => ({
            eq: (_col2: string, _val: boolean) =>
              Promise.resolve({
                data: keys.filter((k) => staleDomainKeys.has(k)).map((k) => ({ domain_key: k, is_stale: true })),
                error: null,
              }),
          }),
        }),
      };
    },
  };
}

describe('fetchStaleOkDomainKeys', () => {
  it('returns an empty set for an empty domainKeys list without querying', async () => {
    const sb = fakeStaleView(new Set());
    const result = await fetchStaleOkDomainKeys(sb, []);
    expect(result.size).toBe(0);
  });

  it('flags only the domain keys the view reports as stale', async () => {
    const sb = fakeStaleView(new Set(['job_a']));
    const result = await fetchStaleOkDomainKeys(sb, ['job_a', 'job_b']);
    expect(result.has('job_a')).toBe(true);
    expect(result.has('job_b')).toBe(false);
  });

  it('fails safe to an empty set (no downgrade) on a query error', async () => {
    const sb = {
      from: () => ({ select: () => ({ in: () => ({ eq: () => Promise.resolve({ data: null, error: new Error('boom') }) }) }) }),
    };
    const result = await fetchStaleOkDomainKeys(sb, ['job_a']);
    expect(result.size).toBe(0);
  });
});

describe('fetchAgentStatusEntries — stale-ok downgrade wiring', () => {
  function fakeClient(
    latest: Array<{ domain_key: string; status: string; detail: string | null; error_message: string | null; checked_at: string | null }>,
    staleDomainKeys: Set<string>,
  ) {
    return {
      from: (table: string) => {
        if (table === 'domain_heartbeats_latest') {
          return { select: () => ({ in: () => Promise.resolve({ data: latest, error: null }) }) };
        }
        if (table === 'domain_heartbeat_latest') {
          return {
            select: () => ({
              in: (_col: string, keys: string[]) => ({
                eq: () => Promise.resolve({
                  data: keys.filter((k) => staleDomainKeys.has(k)).map((k) => ({ domain_key: k, is_stale: true })),
                  error: null,
                }),
              }),
            }),
          };
        }
        // domain_heartbeats (isolated-failure check) — not exercised by
        // these tests since no job here is 'failed'.
        return { select: () => ({ eq: () => ({ order: () => ({ limit: () => Promise.resolve({ data: [], error: null }) }) }) }) };
      },
    };
  }

  it('downgrades a currently-ok job flagged stale by domain_heartbeat_latest to unknown', async () => {
    const sb = fakeClient(
      [{ domain_key: 'core_events', status: 'ok', detail: 'fine', error_message: null, checked_at: '2026-01-01T00:00:00Z' }],
      new Set(['core_events']),
    );
    const entries = await fetchAgentStatusEntries(sb);
    const coreEvents = entries.find((e) => e.domainKey === 'core_events')!;
    expect(coreEvents.status).toBe('unknown');
  });

  it('leaves a currently-ok job alone when it is not flagged stale', async () => {
    const sb = fakeClient(
      [{ domain_key: 'core_events', status: 'ok', detail: 'fine', error_message: null, checked_at: '2026-01-01T00:00:00Z' }],
      new Set(),
    );
    const entries = await fetchAgentStatusEntries(sb);
    const coreEvents = entries.find((e) => e.domainKey === 'core_events')!;
    expect(coreEvents.status).toBe('ok');
  });

  it('does not query domain_heartbeat_latest at all when no job is currently ok', async () => {
    let queried = false;
    const sb = {
      from: (table: string) => {
        if (table === 'domain_heartbeats_latest') {
          return { select: () => ({ in: () => Promise.resolve({ data: [], error: null }) }) };
        }
        queried = true;
        return { select: () => ({ in: () => ({ eq: () => Promise.resolve({ data: [], error: null }) }) }) };
      },
    };
    await fetchAgentStatusEntries(sb);
    expect(queried).toBe(false);
  });
});
