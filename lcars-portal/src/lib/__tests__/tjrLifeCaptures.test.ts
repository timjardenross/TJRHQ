import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createClientMock } = vi.hoisted(() => ({ createClientMock: vi.fn() }));
vi.mock('@supabase/supabase-js', () => ({ createClient: createClientMock }));

import {
  CaptureUnavailableError,
  MAX_CAPTURE_TEXT_CHARS,
  buildCaptureRow,
  deriveTitle,
  ingestCaptures,
  parseCaptureRequest,
  type ParsedCapture,
} from '../tjrLifeCaptures';

const NOW = new Date('2026-10-19T03:00:00.000Z');
const ID1 = '11111111-1111-4111-8111-111111111111';
const ID2 = '22222222-2222-4222-8222-222222222222';

const item = (over: Record<string, unknown> = {}) => ({
  client_id: ID1,
  kind: 'note',
  text: 'Buy a new pillow',
  captured_at: '2026-10-19T02:00:00Z',
  ...over,
});
const body = (over: Record<string, unknown> = {}) => ({
  contract_version: 'tjr-life-capture.v1',
  device_id: 'device-A_1.x',
  captures: [item()],
  ...over,
});

describe('parseCaptureRequest', () => {
  it('accepts a valid single capture and normalises it', () => {
    const r = parseCaptureRequest(body({ captures: [item({ client_id: ID1.toUpperCase(), text: '  hello  ' })] }), NOW);
    expect(r).toMatchObject({ ok: true, deviceId: 'device-A_1.x' });
    if (!r.ok) return;
    expect(r.captures[0]).toMatchObject({ clientId: ID1, kind: 'note', text: 'hello' });
    expect(r.captures[0].capturedAt.toISOString()).toBe('2026-10-19T02:00:00.000Z');
  });

  it('accepts a full batch of 20 and refuses 21 or 0', () => {
    const many = (n: number) =>
      Array.from({ length: n }, (_, i) => item({ client_id: `00000000-0000-4000-8000-${String(i).padStart(12, '0')}` }));
    expect(parseCaptureRequest(body({ captures: many(20) }), NOW).ok).toBe(true);
    expect(parseCaptureRequest(body({ captures: many(21) }), NOW)).toMatchObject({ ok: false, status: 400 });
    expect(parseCaptureRequest(body({ captures: [] }), NOW)).toMatchObject({ ok: false, status: 400 });
  });

  it('rejects unknown fields at the top level and on an item, not storing them', () => {
    expect(parseCaptureRequest({ ...body(), extra: 1 }, NOW)).toMatchObject({ ok: false, status: 400 });
    expect(parseCaptureRequest(body({ captures: [{ ...item(), captured_by: 'someone' }] }), NOW)).toMatchObject({ ok: false, status: 400 });
    expect(parseCaptureRequest(body({ captures: [{ ...item(), idempotency_key: 'x' }] }), NOW)).toMatchObject({ ok: false, status: 400 });
  });

  it('requires the exact contract version and a safe device id', () => {
    expect(parseCaptureRequest(body({ contract_version: 'tjr-life-capture.v2' }), NOW).ok).toBe(false);
    for (const device_id of ['', 'a b', 'x'.repeat(65), 'a/b', 5, null]) {
      expect(parseCaptureRequest(body({ device_id }), NOW).ok).toBe(false);
    }
  });

  it('enforces the text length in characters (code points), trimmed', () => {
    const ok = 'x'.repeat(MAX_CAPTURE_TEXT_CHARS);
    expect(parseCaptureRequest(body({ captures: [item({ text: ok })] }), NOW).ok).toBe(true);
    expect(parseCaptureRequest(body({ captures: [item({ text: ok + 'x' })] }), NOW).ok).toBe(false);
    expect(parseCaptureRequest(body({ captures: [item({ text: '😀'.repeat(MAX_CAPTURE_TEXT_CHARS) })] }), NOW).ok).toBe(true);
    expect(parseCaptureRequest(body({ captures: [item({ text: '😀'.repeat(MAX_CAPTURE_TEXT_CHARS + 1) })] }), NOW).ok).toBe(false);
    for (const text of ['', '   ', '\n\t', 'a\u0000b', 7, null]) {
      expect(parseCaptureRequest(body({ captures: [item({ text })] }), NOW).ok).toBe(false);
    }
  });

  it('refuses health and decision captures with 422 class_not_consented', () => {
    for (const kind of ['health', 'decision']) {
      expect(parseCaptureRequest(body({ captures: [item({ kind })] }), NOW)).toEqual({
        ok: false, status: 422, error: 'class_not_consented',
      });
    }
  });

  it('refuses the WHOLE request when one item is forbidden, so nothing partial can commit', () => {
    const r = parseCaptureRequest(body({ captures: [item(), item({ client_id: ID2, kind: 'health' })] }), NOW);
    expect(r).toMatchObject({ ok: false, status: 422 });
  });

  it('answers 400 (not 422) when an item is structurally bad even if another is forbidden', () => {
    const r = parseCaptureRequest(body({ captures: [item({ client_id: 'nope' }), item({ client_id: ID2, kind: 'decision' })] }), NOW);
    expect(r).toMatchObject({ ok: false, status: 400 });
  });

  it('rejects unknown kinds, bad ids, duplicate ids within a batch and bad timestamps', () => {
    expect(parseCaptureRequest(body({ captures: [item({ kind: 'reminder' })] }), NOW).ok).toBe(false);
    expect(parseCaptureRequest(body({ captures: [item({ client_id: 'not-a-uuid' })] }), NOW).ok).toBe(false);
    expect(parseCaptureRequest(body({ captures: [item(), item()] }), NOW).ok).toBe(false);
    for (const captured_at of ['yesterday', '2026-10-19', '2026-10-19 02:00:00', 1760000000, null, '2019-12-31T00:00:00Z', '2026-13-40T00:00:00Z']) {
      expect(parseCaptureRequest(body({ captures: [item({ captured_at })] }), NOW).ok).toBe(false);
    }
  });

  it('clamps a future captured_at to the server time and never trusts it', () => {
    const r = parseCaptureRequest(body({ captures: [item({ captured_at: '2030-01-01T00:00:00Z' })] }), NOW);
    expect(r.ok && r.captures[0].capturedAt.toISOString()).toBe(NOW.toISOString());
  });

  it('refuses non-objects and arrays at every level', () => {
    for (const bad of [null, 'x', 5, [], [body()]]) expect(parseCaptureRequest(bad, NOW).ok).toBe(false);
    expect(parseCaptureRequest(body({ captures: 'x' }), NOW).ok).toBe(false);
    expect(parseCaptureRequest(body({ captures: ['x'] }), NOW).ok).toBe(false);
  });
});

describe('buildCaptureRow', () => {
  const capture = (kind: ParsedCapture['kind'], text = 'First line\nsecond'): ParsedCapture => ({
    clientId: ID1, kind, text, capturedAt: new Date('2026-10-19T02:00:00.000Z'),
  });

  it('sets provenance, identity, status and idempotency server-side', () => {
    expect(buildCaptureRow(capture('idea'), 'dev1')).toMatchObject({
      captured_by: 'tjr_life_ios:dev1',
      source_type: 'tjr_life_ios',
      source_channel_id: 'tjr-life-ios',
      source_message_id: `tjr-life:${ID1}`,
      idempotency_key: `tjr-life:${ID1}`,
      item_type: 'idea',
      title: 'First line',
      raw_text: 'First line\nsecond',
      processing_status: 'pending',
      review_status: 'unreviewed',
      classification: 'unclassified',
      summary: null,
    });
  });

  it('maps task and note directly, and commitment to a flagged task', () => {
    expect(buildCaptureRow(capture('task'), 'd').item_type).toBe('task');
    expect(buildCaptureRow(capture('note'), 'd').item_type).toBe('note');
    expect(buildCaptureRow(capture('commitment'), 'd')).toMatchObject({
      item_type: 'task', summary: 'Commitment (captured in TJR Life)', summary_source: 'fallback',
    });
  });

  it('only ever produces item_type values the live table allows', () => {
    const allowed = ['url', 'text_note', 'file', 'image', 'screenshot', 'note', 'idea', 'health', 'decision', 'task'];
    for (const kind of ['task', 'note', 'idea', 'commitment'] as const) {
      expect(allowed).toContain(buildCaptureRow(capture(kind), 'd').item_type);
    }
  });

  it('derives a bounded title', () => {
    expect(deriveTitle('x'.repeat(500)).length).toBeLessThanOrEqual(90);
    expect(deriveTitle('\n\nfoo')).toBe('Untitled capture');
  });
});

type Script = { inserts: Array<{ data?: { id: string } | null; error?: { code?: string } | null }>; existing?: Array<{ data: { id: string } | null }>; auditThrows?: boolean };

function makeClient(script: Script) {
  const calls = { captured: [] as unknown[], audit: [] as unknown[], readbacks: [] as string[] };
  let i = 0;
  let j = 0;
  const client = {
    from(table: string) {
      if (table === 'audit_events') {
        return { insert: async (row: unknown) => { calls.audit.push(row); if (script.auditThrows) throw new Error('boom'); return { error: null }; } };
      }
      return {
        insert(row: unknown) {
          calls.captured.push(row);
          const res = script.inserts[i++] ?? { data: null, error: { code: 'XX000' } };
          return { select: () => ({ maybeSingle: async () => ({ data: res.data ?? null, error: res.error ?? null }) }) };
        },
        select: () => ({
          eq: (_col: string, value: string) => {
            calls.readbacks.push(value);
            return { maybeSingle: async () => script.existing?.[j++] ?? { data: null } };
          },
        }),
      };
    },
  };
  return { client: client as never, calls };
}

describe('ingestCaptures', () => {
  const logSpies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => {}));
  beforeEach(() => vi.clearAllMocks());

  const parsed = (n = 1) => ({
    deviceId: 'dev1',
    captures: [ID1, ID2].slice(0, n).map((clientId) => ({ clientId, kind: 'note' as const, text: 'secret text', capturedAt: NOW })),
  });

  it('accepts new captures and returns their HQ ids', async () => {
    const { client, calls } = makeClient({ inserts: [{ data: { id: 'hq-1' } }, { data: { id: 'hq-2' } }] });
    const results = await ingestCaptures(parsed(2), client);
    expect(results).toEqual([
      { client_id: ID1, status: 'accepted', hq_id: 'hq-1' },
      { client_id: ID2, status: 'accepted', hq_id: 'hq-2' },
    ]);
    expect(calls.captured).toHaveLength(2);
  });

  it('reports a retry (unique violation) as duplicate with the canonical row id, never inserting a second', async () => {
    const { client, calls } = makeClient({ inserts: [{ error: { code: '23505' } }], existing: [{ data: { id: 'hq-old' } }] });
    const results = await ingestCaptures(parsed(), client);
    expect(results).toEqual([{ client_id: ID1, status: 'duplicate', hq_id: 'hq-old' }]);
    expect(calls.readbacks).toEqual([`tjr-life:${ID1}`]);
    expect(calls.captured).toHaveLength(1);
  });

  it('fails the whole request with a detail-free error on any other database failure', async () => {
    const { client } = makeClient({ inserts: [{ data: { id: 'hq-1' } }, { error: { code: '42501' } }] });
    await expect(ingestCaptures(parsed(2), client)).rejects.toBeInstanceOf(CaptureUnavailableError);
  });

  it('fails when a unique violation cannot be read back', async () => {
    const { client } = makeClient({ inserts: [{ error: { code: '23505' } }], existing: [{ data: null }] });
    await expect(ingestCaptures(parsed(), client)).rejects.toBeInstanceOf(CaptureUnavailableError);
  });

  it('writes one audit row per request with counts and no capture text; an audit failure changes nothing', async () => {
    const { client, calls } = makeClient({ inserts: [{ data: { id: 'hq-1' } }], auditThrows: true });
    const results = await ingestCaptures(parsed(), client);
    expect(results[0].status).toBe('accepted');
    expect(JSON.stringify(calls.audit)).not.toContain('secret text');
    expect(calls.audit[0]).toMatchObject({ action: 'capture_ingest', details: { accepted: 1, duplicate: 0 } });
  });

  it('builds the service-role client only from server env and fails closed without it', async () => {
    const saved = { url: process.env.NEXT_PUBLIC_SUPABASE_URL, key: process.env.SUPABASE_SERVICE_ROLE_KEY };
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    await expect(ingestCaptures(parsed())).rejects.toBeInstanceOf(CaptureUnavailableError);
    expect(createClientMock).not.toHaveBeenCalled();
    process.env.SUPABASE_SERVICE_ROLE_KEY = 'service-role-secret';
    createClientMock.mockReturnValue(makeClient({ inserts: [{ data: { id: 'h' } }] }).client);
    await ingestCaptures(parsed());
    expect(createClientMock.mock.calls[0][1]).toBe('service-role-secret');
    process.env.NEXT_PUBLIC_SUPABASE_URL = saved.url;
    if (saved.key === undefined) delete process.env.SUPABASE_SERVICE_ROLE_KEY; else process.env.SUPABASE_SERVICE_ROLE_KEY = saved.key;
  });

  it('never logs capture text', async () => {
    const { client } = makeClient({ inserts: [{ data: { id: 'hq-1' } }] });
    await ingestCaptures(parsed(), client);
    for (const spy of logSpies) expect(spy).not.toHaveBeenCalled();
  });
});
