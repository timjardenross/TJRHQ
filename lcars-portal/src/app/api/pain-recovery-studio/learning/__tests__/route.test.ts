import { beforeEach, describe, expect, it, vi } from 'vitest';

const requireValidatedUserMock = vi.fn();
const createClientMock = vi.fn();

vi.mock('@/lib/supabase-server', () => ({
  requireValidatedUser: () => requireValidatedUserMock(),
  createSupabaseServerClient: async () => createClientMock(),
}));

import { GET, POST, PUT } from '../route';

const USER_ID = '11111111-1111-4111-8111-111111111111';

function consentResult(value: { data?: unknown; error?: unknown }) {
  return { select: () => ({ eq: () => ({ maybeSingle: async () => value }) }) };
}

function eventReader(value: { data?: unknown; error?: unknown }) {
  return {
    select: () => ({
      eq: () => ({
        in: () => ({
          order: async () => value,
        }),
      }),
    }),
  };
}

function eventWriter(value: { data?: unknown; error?: unknown }) {
  return {
    insert: vi.fn().mockReturnValue({
      select: vi.fn().mockReturnValue({
        single: async () => value,
      }),
    }),
  };
}

function makeClient(consent: unknown, events: unknown) {
  return {
    from: vi.fn((table: string) => {
      if (table === 'pain_recovery_consents') return consentResult(consent as { data?: unknown; error?: unknown });
      return events as ReturnType<typeof eventReader> | ReturnType<typeof eventWriter>;
    }),
  };
}

function makeRequest(body?: unknown) {
  return new Request('http://localhost/api/pain-recovery-studio/learning', {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('append-only learning API', () => {
  beforeEach(() => {
    requireValidatedUserMock.mockReset();
    createClientMock.mockReset();
  });

  it('rejects unauthenticated reads', async () => {
    requireValidatedUserMock.mockResolvedValue(null);
    const response = await GET();
    expect(response.status).toBe(401);
  });

  it('fail-closes when consent is unavailable', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: USER_ID });
    createClientMock.mockResolvedValue(makeClient({ error: { message: 'connection failed' } }, null));
    const response = await GET();
    expect(response.status).toBe(503);
  });

  it('requires explicit remote storage consent', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: USER_ID });
    createClientMock.mockResolvedValue(makeClient({ data: { status: 'withdrawn', main_consent: false } }, null));
    const response = await GET();
    expect(response.status).toBe(403);
    expect((await response.json()).local_only).toBe(true);
  });

  it('returns raw history and the latest record for each date', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: USER_ID });
    const events = {
      data: [
        {
          id: 'event-1',
          event_type: 'learning_record',
          payload: { date: '2026-11-14', nextDayCost: '2', learningNote: 'old' },
          created_at: '2026-11-14T01:00:00Z',
        },
        {
          id: 'event-2',
          event_type: 'learning_record',
          payload: { date: '2026-11-14', nextDayCost: '0', learningNote: 'newer' },
          created_at: '2026-11-14T02:00:00Z',
        },
        {
          id: 'event-3',
          event_type: 'learning_decision',
          payload: { id: 'suggestion-1', date: '2026-11-14', decision: 'different', note: 'chose rest' },
          created_at: '2026-11-14T03:00:00Z',
        },
      ],
    };
    createClientMock.mockResolvedValue(makeClient({ data: { status: 'granted', main_consent: true } }, eventReader(events)));
    const response = await GET();
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.records).toHaveLength(2);
    expect(body.latestRecords).toHaveLength(1);
    expect(body.latestRecords[0].eventId).toBe('event-2');
    expect(body.latestRecords[0].nextDayCost).toBe(0);
    expect(body.decisions[0].decision).toBe('different');
  });

  it('rejects an invalid learning event before consent or storage', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: USER_ID });
    const response = await POST(makeRequest({ kind: 'learning_record', record: { date: 'not-a-date' } }));
    expect(response.status).toBe(400);
    expect(createClientMock).not.toHaveBeenCalled();
  });

  it('appends a validated record event', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: USER_ID });
    const inserted = { data: { id: 'event-4', event_type: 'learning_record', payload: { date: '2026-11-14', nextDayCost: 0 }, created_at: 'now' } };
    const client = makeClient({ data: { status: 'granted', main_consent: true } }, eventWriter(inserted));
    createClientMock.mockResolvedValue(client);
    const response = await POST(makeRequest({ kind: 'learning_record', record: { date: '2026-11-14', next_day_cost: '0', learning_note: 'preserved a shorter walk' } }));
    expect(response.status).toBe(201);
    const eventsTable = client.from('pain_recovery_events') as ReturnType<typeof eventWriter>;
    const [event] = eventsTable.insert.mock.calls[0];
    expect(event).toMatchObject({ user_id: USER_ID, event_type: 'learning_record', payload: { date: '2026-11-14', nextDayCost: 0, learningNote: 'preserved a shorter walk' } });
  });

  it('appends a validated decision event', async () => {
    requireValidatedUserMock.mockResolvedValue({ id: USER_ID });
    const inserted = { data: { id: 'event-5', event_type: 'learning_decision', payload: { id: 'suggestion', date: '2026-11-14', decision: 'use' }, created_at: 'now' } };
    const client = makeClient({ data: { status: 'granted', main_consent: true } }, eventWriter(inserted));
    createClientMock.mockResolvedValue(client);
    const response = await POST(makeRequest({ kind: 'learning_decision', decision: { id: 'suggestion', date: '2026-11-14', decision: 'use' } }));
    expect(response.status).toBe(201);
    const eventsTable = client.from('pain_recovery_events') as ReturnType<typeof eventWriter>;
    const [event] = eventsTable.insert.mock.calls[0];
    expect(event).toMatchObject({ user_id: USER_ID, event_type: 'learning_decision', payload: { decision: 'use' } });
  });

  it('does not expose update methods', async () => {
    const response = await PUT();
    expect(response.status).toBe(405);
    expect(response.headers.get('allow')).toContain('GET, POST');
    expect(await response.json()).toMatchObject({ error: expect.stringContaining('append-only') });
  });
});
