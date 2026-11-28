import { beforeEach, describe, expect, it, vi } from 'vitest';

const answerQuery = vi.fn();
vi.mock('@/lib/ask', () => ({ answerQuery: (...a: unknown[]) => answerQuery(...a) }));
import { askHq, classifyChatFailure, createSseParser, type SseEvent } from '../ask';

const sse = (...parts: string[]) => new ReadableStream<Uint8Array>({ start(c) { const e = new TextEncoder(); for (const p of parts) c.enqueue(e.encode(p)); c.close(); } });
const chatOk = (...parts: string[]) => ({ ok: true, status: 200, body: sse(...parts), json: async () => ({}) });
const failure = (status: number, body: unknown) => ({ ok: false, status, json: async () => body });

beforeEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals(); answerQuery.mockResolvedValue({ prose: 'x', basedOn: [], matched: false }); });

describe('SSE parsing', () => {
  it('handles tokens split across chunks, actions and done', () => {
    const got: SseEvent[] = [];
    const p = createSseParser((e) => got.push(e));
    p.push('data: {"token":"Hel');
    p.push('lo"}\ndata: {"actions":[{"type":"log_decision","success":true,"detail":"queued"}]}\n');
    p.push('data: [DONE]\n');
    expect(got).toEqual([{ token: 'Hello' }, { actions: [{ type: 'log_decision', success: true, detail: 'queued' }] }, { done: true }]);
  });
  it('skips malformed lines instead of failing', () => {
    const got: SseEvent[] = [];
    createSseParser((e) => got.push(e)).push('data: {oops\ndata: {"token":"ok"}\n');
    expect(got).toEqual([{ token: 'ok' }]);
  });
});

describe('Ask uses the existing services', () => {
  it('answers from retrieval first (no model call) when an intent matches', async () => {
    answerQuery.mockResolvedValue({ prose: 'Two missions are active.', basedOn: [{ label: 'missions', count: 2 }], matched: true });
    const f = vi.fn();
    vi.stubGlobal('fetch', f);
    const r = await askHq('What missions are active?');
    expect(r).toMatchObject({ kind: 'answer', via: 'retrieval', text: 'Two missions are active.' });
    expect(f).not.toHaveBeenCalled();
  });
  it('otherwise streams from the AI Console with role general and nothing else', async () => {
    const f = vi.fn().mockResolvedValue(chatOk('data: {"token":"Hello "}\n', 'data: {"token":"world"}\n', 'data: [DONE]\n'));
    vi.stubGlobal('fetch', f);
    const tokens: string[] = [];
    const r = await askHq('Who depends on Meridian?', { onToken: (t) => tokens.push(t) });
    expect(r).toMatchObject({ kind: 'answer', via: 'model', text: 'Hello world' });
    expect(tokens.at(-1)).toBe('Hello world');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/ai/chat');
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent).toEqual({ role: 'general', stream: true, messages: [{ role: 'user', content: 'Who depends on Meridian?' }] });
    expect(sent).not.toHaveProperty('systemPrompt');
    expect(sent).not.toHaveProperty('model');
  });
  it('adds only the viewed item title as context', async () => {
    const f = vi.fn().mockResolvedValue(chatOk('data: [DONE]\n'));
    vi.stubGlobal('fetch', f);
    await askHq('Why does this matter?', { context: 'Provider outage' });
    expect(JSON.parse((f.mock.calls[0][1] as RequestInit).body as string).messages[0].content).toContain('Provider outage');
  });
  it('passes governed action proposals through as queued, never as done', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(chatOk('data: {"token":"ok"}\n', 'data: {"actions":[{"type":"create_mission","success":true,"detail":"Proposed for your approval in Decide"}]}\n', 'data: [DONE]\n')));
    const r = await askHq('Open a mission to look into this');
    expect(r.kind === 'answer' && r.proposals[0].detail).toMatch(/proposed for your approval/i);
  });
  it('advice mode calls the Advisory service and labels degraded answers', async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ result: { executive_summary: 'Wait.', recommendation: 'Hold', risks_and_challenges: ['Cost'], degraded: true } }) });
    vi.stubGlobal('fetch', f);
    const r = await askHq('Should we switch provider?', { mode: 'advice' });
    expect(f.mock.calls[0][0]).toBe('/api/advisory');
    expect(JSON.parse((f.mock.calls[0][1] as RequestInit).body as string)).toEqual({ action: 'advice', question: 'Should we switch provider?' });
    expect(r.kind === 'answer' && r.text).toContain('Recommendation: Hold');
    expect(r.kind === 'answer' && r.notes.join(' ')).toMatch(/degraded/i);
    expect(answerQuery).not.toHaveBeenCalled();
  });
});

describe('failures are explained honestly', () => {
  it.each([
    [401, {}, 'unavailable', /signed out/i],
    [503, {}, 'unavailable', /not switched on/i],
    [424, { error: 'local model down' }, 'unavailable', /local model/i],
    [429, {}, 'unavailable', /too many/i],
    [504, {}, 'unavailable', /in time/i],
    [422, { code: 'personal_health_blocked', error: 'Health information is never sent.' }, 'refused', /never sent/i],
    [500, { error: 'boom' }, 'error', /boom/],
  ])('status %s', async (status, body, kind, rx) => {
    const r = await classifyChatFailure(failure(status as number, body) as unknown as Response);
    expect(r.kind).toBe(kind);
    expect('reason' in r && r.reason).toMatch(rx as RegExp);
  });
  it('an unreachable service is reported, not thrown', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    expect((await askHq('anything')).kind).toBe('unavailable');
  });
  it('an empty question never calls anything', async () => {
    const f = vi.fn(); vi.stubGlobal('fetch', f);
    expect((await askHq('   ')).kind).toBe('error');
    expect(f).not.toHaveBeenCalled();
  });
});
