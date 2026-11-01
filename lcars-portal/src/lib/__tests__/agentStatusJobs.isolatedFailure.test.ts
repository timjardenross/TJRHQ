import { describe, it, expect } from 'vitest';
import { fetchIsolatedFailureFlags, fetchAgentStatusEntries } from '../agentStatusJobs';

// HQ V1 Integration QA §12 repair: domain_heartbeats_latest only exposes the
// single latest row per domain, so a lone blip and a persistent outage look
// identical to computeCapabilities. fetchIsolatedFailureFlags closes that
// gap with a bounded, per-domain read of the raw domain_heartbeats event log
// (the same table History already reads) — only for domains the caller
// already knows are currently 'failed' and 'critical'.

type Row = { status: string };

/** A minimal fake Supabase-like client: `.from(table).select(...).eq(k, v)
 *  .order(...).limit(n)` resolves to `{ data, error }` from a per-domain_key
 *  fixture map, keyed by whatever `.eq('domain_key', v)` was called with. */
function fakeSupabase(rowsByDomainKey: Map<string, Row[] | 'error'>) {
  return {
    from: (_table: string) => ({
      select: (_cols: string) => ({
        eq: (_col: string, domainKey: string) => ({
          order: (_col2: string, _opts: unknown) => ({
            limit: (n: number) => {
              const rows = rowsByDomainKey.get(domainKey);
              if (rows === 'error') return Promise.resolve({ data: null, error: new Error('boom') });
              return Promise.resolve({ data: (rows ?? []).slice(0, n), error: null });
            },
          }),
        }),
      }),
    }),
  };
}

describe('fetchIsolatedFailureFlags', () => {
  it('returns an empty map for an empty domainKeys list without querying', async () => {
    const sb = fakeSupabase(new Map());
    const result = await fetchIsolatedFailureFlags(sb, []);
    expect(result.size).toBe(0);
  });

  it('marks a domain isolated when the immediately preceding heartbeat was ok (a fresh, first-time failure)', async () => {
    const sb = fakeSupabase(new Map([
      ['job_a', [{ status: 'failed' }, { status: 'ok' }]],
    ]));
    const result = await fetchIsolatedFailureFlags(sb, ['job_a']);
    expect(result.get('job_a')).toBe(true);
  });

  it('marks a domain NOT isolated when the immediately preceding heartbeat was also failed (a persistent, two-in-a-row failure)', async () => {
    const sb = fakeSupabase(new Map([
      ['job_a', [{ status: 'failed' }, { status: 'failed' }]],
    ]));
    const result = await fetchIsolatedFailureFlags(sb, ['job_a']);
    expect(result.get('job_a')).toBe(false);
  });

  it('defaults to NOT isolated when there is no prior heartbeat at all — ambiguity never suppresses a genuine attention signal', async () => {
    const sb = fakeSupabase(new Map([
      ['job_a', [{ status: 'failed' }]],
    ]));
    const result = await fetchIsolatedFailureFlags(sb, ['job_a']);
    expect(result.get('job_a')).toBe(false);
  });

  it('defaults to NOT isolated on a query error for that domain — fails safe, still escalates', async () => {
    const sb = fakeSupabase(new Map([
      ['job_a', 'error'],
    ]));
    const result = await fetchIsolatedFailureFlags(sb, ['job_a']);
    expect(result.get('job_a')).toBe(false);
  });
});

describe('fetchAgentStatusEntries — isolated-failure wiring', () => {
  function fakeLatestAndHistory(
    latest: Array<{ domain_key: string; status: string; detail: string | null; error_message: string | null; checked_at: string | null }>,
    historyByDomainKey: Map<string, Row[] | 'error'>,
  ) {
    return {
      from: (table: string) => {
        if (table === 'domain_heartbeats_latest') {
          return {
            select: (_cols: string) => ({
              in: (_col: string, _keys: string[]) => Promise.resolve({ data: latest, error: null }),
            }),
          };
        }
        // domain_heartbeats (the raw event log, for the streak check)
        return {
          select: (_cols: string) => ({
            eq: (_col: string, domainKey: string) => ({
              order: (_col2: string, _opts: unknown) => ({
                limit: (n: number) => {
                  const rows = historyByDomainKey.get(domainKey);
                  if (rows === 'error') return Promise.resolve({ data: null, error: new Error('boom') });
                  return Promise.resolve({ data: (rows ?? []).slice(0, n), error: null });
                },
              }),
            }),
          }),
        };
      },
    };
  }

  it('does not query domain_heartbeats at all when no critical job is currently failed (the common healthy case)', async () => {
    let historyQueried = false;
    const sb = {
      from: (table: string) => {
        if (table === 'domain_heartbeats_latest') {
          return { select: () => ({ in: () => Promise.resolve({ data: [], error: null }) }) };
        }
        historyQueried = true;
        return { select: () => ({ eq: () => ({ order: () => ({ limit: () => Promise.resolve({ data: [], error: null }) }) }) }) };
      },
    };
    const entries = await fetchAgentStatusEntries(sb);
    expect(historyQueried).toBe(false);
    // Every job with no heartbeat row reports 'unknown', never a fabricated 'ok'.
    expect(entries.every((e) => e.status === 'unknown' || e.status === 'retired' || e.status === 'disabled')).toBe(true);
  });

  it('marks a currently-failed critical job isolated when its prior heartbeat was ok', async () => {
    const sb = fakeLatestAndHistory(
      [{ domain_key: 'core_events', status: 'failed', detail: null, error_message: 'timeout', checked_at: '2026-09-06T00:00:00Z' }],
      new Map([['core_events', [{ status: 'failed' }, { status: 'ok' }]]]),
    );
    const entries = await fetchAgentStatusEntries(sb);
    const coreEvents = entries.find((e) => e.domainKey === 'core_events')!;
    expect(coreEvents.status).toBe('failed');
    expect(coreEvents.isIsolatedFailure).toBe(true);
  });
});
