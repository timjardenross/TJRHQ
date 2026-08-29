import { describe, it, expect } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import { fetchGovernedRow } from '@/lib/governedFetch';

interface Row {
  id: string;
  status: string;
}

function fakeClient(response: { data: Row | null; error: { message: string } | null }): SupabaseClient {
  return {
    from: (_table: string) => ({
      select: (_cols: string) => ({
        eq: (_col: string, _val: string) => ({
          maybeSingle: async () => response,
        }),
      }),
    }),
  } as unknown as SupabaseClient;
}

describe('fetchGovernedRow', () => {
  it('returns the row when no eligibility check is given', async () => {
    const client = fakeClient({ data: { id: '1', status: 'awaiting_review' }, error: null });
    const res = await fetchGovernedRow<Row>(client, 'things', 'id', '1', 'id,status');
    expect(res.ok).toBe(true);
    if (res.ok) expect(res.row.status).toBe('awaiting_review');
  });

  it('returns 404 when the row does not exist', async () => {
    const client = fakeClient({ data: null, error: null });
    const res = await fetchGovernedRow<Row>(client, 'things', 'id', 'missing', 'id,status');
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.status).toBe(404);
  });

  it('returns 500 on a lookup error, never throws', async () => {
    const client = fakeClient({ data: null, error: { message: 'connection reset' } });
    const res = await fetchGovernedRow<Row>(client, 'things', 'id', '1', 'id,status');
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.status).toBe(500);
      expect(res.error).toMatch(/connection reset/);
    }
  });

  it('applies the eligibility predicate and returns the caller-chosen status/message on failure', async () => {
    const client = fakeClient({ data: { id: '1', status: 'approved' }, error: null });
    const res = await fetchGovernedRow<Row>(client, 'things', 'id', '1', 'id,status', {
      predicate: (row) => row.status === 'awaiting_review',
      ineligibleStatus: 409,
      ineligibleMessage: (row) => `Not eligible, current status: ${row.status}`,
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.status).toBe(409);
      expect(res.error).toBe('Not eligible, current status: approved');
    }
  });

  it('passes the eligibility predicate through when the row is eligible', async () => {
    const client = fakeClient({ data: { id: '1', status: 'awaiting_review' }, error: null });
    const res = await fetchGovernedRow<Row>(client, 'things', 'id', '1', 'id,status', {
      predicate: (row) => row.status === 'awaiting_review',
      ineligibleStatus: 409,
      ineligibleMessage: () => 'unreachable',
    });
    expect(res.ok).toBe(true);
  });
});
