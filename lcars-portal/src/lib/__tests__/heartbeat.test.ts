import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import {
  recordHeartbeat,
  recordHeartbeatOk,
  recordHeartbeatServerSide,
  type RecordHeartbeatArgs,
} from '@/lib/heartbeat';

// domain_heartbeats has RLS restricted to service_role writes only
// (domain_heartbeats_service_write policy) -- the same shape of gap that
// bit core_events (see core-events.test.ts). These tests prove the TS port
// of core/platform/heartbeat.py::record_heartbeat() never throws and never
// silently drops a failed write.

const ARGS: RecordHeartbeatArgs = {
  domainKey: 'test-domain',
  detail: 'unit test',
};

function fakeClient(insertResult: { error: { message: string } | null }): SupabaseClient {
  return {
    from: () => ({
      insert: async () => insertResult,
    }),
  } as unknown as SupabaseClient;
}

function throwingClient(): SupabaseClient {
  return {
    from: () => ({
      insert: async () => {
        throw new Error('network exploded');
      },
    }),
  } as unknown as SupabaseClient;
}

describe('recordHeartbeat', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  it('returns ok:true and logs nothing on a successful insert', async () => {
    const result = await recordHeartbeat(fakeClient({ error: null }), ARGS);
    expect(result).toEqual({ ok: true });
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('defaults status to "ok" when not provided', async () => {
    let insertedPayload: Record<string, unknown> | undefined;
    const client = {
      from: () => ({
        insert: async (payload: Record<string, unknown>) => {
          insertedPayload = payload;
          return { error: null };
        },
      }),
    } as unknown as SupabaseClient;

    await recordHeartbeat(client, ARGS);
    expect(insertedPayload).toMatchObject({
      domain_key: 'test-domain',
      status: 'ok',
      detail: 'unit test',
      error_message: null,
      latency_ms: null,
    });
  });

  it('returns ok:false and logs a structured failure when the insert is RLS-denied (never throws)', async () => {
    const result = await recordHeartbeat(
      fakeClient({ error: { message: 'new row violates row-level security policy for table "domain_heartbeats"' } }),
      ARGS,
    );
    expect(result.ok).toBe(false);
    expect(result.error).toContain('row-level security');
    expect(errorSpy).toHaveBeenCalledTimes(1);
    const [message, payload] = errorSpy.mock.calls[0] as [string, { domain_key: string; status: string; error: string }];
    expect(message).toBe('[heartbeat] record_heartbeat failed');
    expect(payload).toMatchObject({ domain_key: ARGS.domainKey });
    expect(payload.error).toContain('row-level security');
  });

  it('never throws even if the client itself throws, and still logs the failure', async () => {
    await expect(recordHeartbeat(throwingClient(), ARGS)).resolves.toEqual({
      ok: false,
      error: 'network exploded',
    });
    expect(errorSpy).toHaveBeenCalledTimes(1);
  });
});

describe('recordHeartbeatOk', () => {
  it('always sends status "ok" regardless of what the caller passes elsewhere', async () => {
    let insertedPayload: Record<string, unknown> | undefined;
    const client = {
      from: () => ({
        insert: async (payload: Record<string, unknown>) => {
          insertedPayload = payload;
          return { error: null };
        },
      }),
    } as unknown as SupabaseClient;

    const result = await recordHeartbeatOk(client, 'captains_log', 'log_date=2026-08-10');
    expect(result).toEqual({ ok: true });
    expect(insertedPayload).toMatchObject({ domain_key: 'captains_log', status: 'ok', detail: 'log_date=2026-08-10' });
  });
});

describe('recordHeartbeatServerSide', () => {
  const originalKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  afterEach(() => {
    if (originalKey === undefined) delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    else process.env.SUPABASE_SERVICE_ROLE_KEY = originalKey;
  });

  it('logs and returns ok:false instead of throwing when SUPABASE_SERVICE_ROLE_KEY is missing', async () => {
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const result = await recordHeartbeatServerSide(ARGS);

    expect(result.ok).toBe(false);
    expect(result.error).toContain('SUPABASE_SERVICE_ROLE_KEY');
    expect(errorSpy).toHaveBeenCalledTimes(1);
    errorSpy.mockRestore();
  });
});
