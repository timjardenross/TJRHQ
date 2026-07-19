import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import { publishEvent, publishEventServerSide, publishMissionEvent, type PublishEventArgs } from '@/lib/core-events';

// core_events has RLS enabled with zero anon/authenticated policies (migration
// 0055) -- publishEvent()'s failure path is the whole point of this suite.
// A real completed Physical Readiness session hit exactly this: the insert
// was denied, the old bare `catch {}` swallowed it, and nobody knew until a
// manual DB check. These tests prove that can't happen silently again.

const ARGS: PublishEventArgs = {
  eventType: 'test.event',
  domain: 'test-domain',
  source: 'vitest',
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

describe('publishEvent', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  it('returns ok:true and logs nothing on a successful insert', async () => {
    const result = await publishEvent(fakeClient({ error: null }), ARGS);
    expect(result).toEqual({ ok: true });
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('returns ok:false and logs a structured failure when the insert is RLS-denied (never throws)', async () => {
    const result = await publishEvent(
      fakeClient({ error: { message: 'new row violates row-level security policy for table "core_events"' } }),
      ARGS,
    );
    expect(result.ok).toBe(false);
    expect(result.error).toContain('row-level security');
    expect(errorSpy).toHaveBeenCalledTimes(1);
    const [message, payload] = errorSpy.mock.calls[0] as [string, { event_type: string; domain: string; source: string; error: string }];
    expect(message).toBe('[core-events] publish_event failed');
    expect(payload).toMatchObject({ event_type: ARGS.eventType, domain: ARGS.domain, source: ARGS.source });
    expect(payload.error).toContain('row-level security');
  });

  it('never throws even if the client itself throws, and still logs the failure', async () => {
    await expect(publishEvent(throwingClient(), ARGS)).resolves.toEqual({
      ok: false,
      error: 'network exploded',
    });
    expect(errorSpy).toHaveBeenCalledTimes(1);
  });
});

describe('publishMissionEvent', () => {
  it('propagates failure instead of silently discarding it', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const result = await publishMissionEvent(fakeClient({ error: { message: 'denied' } }), {
      eventType: 'mission.approved',
      missionId: 'MSN-TEST-0001',
      toStatus: 'Approved',
      source: 'vitest',
    });
    expect(result.ok).toBe(false);
    expect(errorSpy).toHaveBeenCalledTimes(1);
    errorSpy.mockRestore();
  });
});

describe('publishEventServerSide', () => {
  const originalKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  afterEach(() => {
    if (originalKey === undefined) delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    else process.env.SUPABASE_SERVICE_ROLE_KEY = originalKey;
  });

  it('logs and returns ok:false instead of throwing when SUPABASE_SERVICE_ROLE_KEY is missing', async () => {
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const result = await publishEventServerSide(ARGS);

    expect(result.ok).toBe(false);
    expect(result.error).toContain('SUPABASE_SERVICE_ROLE_KEY');
    expect(errorSpy).toHaveBeenCalledTimes(1);
    errorSpy.mockRestore();
  });
});
