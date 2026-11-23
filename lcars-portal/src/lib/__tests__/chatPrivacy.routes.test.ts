// #664 PR A — route-level tests for /api/ai/chat and /api/xo: flag OFF equals the #663/#666 behaviour; flag ON uses the boundary.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('@/lib/supabase-server', () => ({
  createSupabaseServerClient: async () => ({ auth: { getSession: async () => ({ data: { session: { user: { id: 'u' } } } }) } }),
}));
vi.mock('@/lib/ai-context', () => ({ buildShipContext: async () => ({ text: 'SHIP-CONTEXT-PRIVATE', sources: [] }) }));
vi.mock('@/lib/ai-actions', () => ({ parseAndProposeActions: async () => [] }));
vi.mock('@/lib/rateLimit', () => ({ checkRateLimit: () => true }));
vi.mock('@/lib/number-one/intent-router', () => ({
  classifyIntent: (t: string) => (/^remember this/i.test(t) ? { kind: 'remember' } : null),
  dispatchIntent: async () => ({ handled: true, reply: 'Captured.' }),
}));

import { POST as chatPOST } from '../../app/api/ai/chat/route';
import { POST as xoPOST } from '../../app/api/xo/route';

const nd = (t: string) => new Response(JSON.stringify({ message: { content: t }, done: false }) + '\n' + JSON.stringify({ message: { content: '' }, done: true }) + '\n', { status: 200 });
const single = (t: string) => new Response(JSON.stringify({ message: { content: t }, done: true }), { status: 200 });
interface Call { url: string; body: string }
function stub(handler: (c: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: unknown, init?: { body?: unknown }) => { const c = { url: String(url), body: String(init?.body ?? '') }; calls.push(c); return handler(c); }));
  return calls;
}
const isLocal = (c: Call) => c.url.startsWith('http://127.0.0.1');
const req = (body: unknown) => new Request('http://x/api', { method: 'POST', body: JSON.stringify(body) }) as never;
const ENV_KEYS = ['CHAT_LOCAL_FIRST_V1', 'OLLAMA_CLOUD_ENABLED', 'OLLAMA_BASE_URL', 'OLLAMA_LOCAL_BASE_URL', 'OLLAMA_LOCAL_MODEL', 'HEALTH_LLM_EXTERNAL_ALLOWED'];
let saved: Record<string, string | undefined> = {};
beforeEach(() => { saved = Object.fromEntries(ENV_KEYS.map((k) => [k, process.env[k]])); ENV_KEYS.forEach((k) => delete process.env[k]); vi.spyOn(console, 'info').mockImplementation(() => {}); });
afterEach(() => { ENV_KEYS.forEach((k) => (saved[k] === undefined ? delete process.env[k] : (process.env[k] = saved[k]))); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function sse(res: Response) { return await res.text(); }

describe('flag OFF — legacy #663/#666 behaviour unchanged', () => {
  it('/api/ai/chat: personal health → 422 with the existing code; no outbound call', async () => {
    process.env.OLLAMA_CLOUD_ENABLED = 'true';
    const calls = stub(() => nd('x'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'sleep_hours=4 pain_score 7 today' }], role: 'chief_engineer', stream: true }));
    expect(res.status).toBe(422);
    expect((await res.json()).code).toBe('personal_health_blocked');
    expect(calls).toHaveLength(0);
  });
  it('/api/ai/chat: benign chat goes to the cloud exactly as before (role prompt + context + history)', async () => {
    process.env.OLLAMA_CLOUD_ENABLED = 'true';
    const calls = stub(() => nd('hi'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'Summarise the router incident' }], role: 'chief_engineer', stream: true }));
    expect(res.status).toBe(200);
    expect(calls[0].url).toBe('https://ollama.com/api/chat');
    expect(calls[0].body).toContain('SHIP-CONTEXT-PRIVATE');
    expect(calls[0].body).toContain('Summarise the router incident');
  });
  it('/api/ai/chat: OLLAMA_CLOUD_ENABLED unset → 503 as before', async () => {
    stub(() => nd('x'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'hi' }], role: 'chief_engineer' }));
    expect(res.status).toBe(503);
  });
  it('/api/xo: legacy 503 / 422 unchanged', async () => {
    stub(() => nd('x'));
    expect((await xoPOST(req({ messages: [{ role: 'user', content: 'hi' }] }))).status).toBe(503);
    process.env.OLLAMA_CLOUD_ENABLED = 'true';
    expect((await xoPOST(req({ messages: [{ role: 'user', content: 'sleep_hours=4 pain_score 7 today' }] }))).status).toBe(422);
  });
  it('flag OFF + HEALTH_LLM_EXTERNAL_ALLOWED=1 keeps the legacy opt-in behaviour (no refusal)', async () => {
    process.env.OLLAMA_CLOUD_ENABLED = 'true'; process.env.HEALTH_LLM_EXTERNAL_ALLOWED = '1';
    stub(() => nd('x'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'sleep_hours=4 pain_score 7 today' }], role: 'chief_engineer', stream: true }));
    expect(res.status).toBe(200);
  });
});

describe('flag ON — local-first boundary', () => {
  beforeEach(() => { process.env.CHAT_LOCAL_FIRST_V1 = 'true'; process.env.OLLAMA_CLOUD_ENABLED = 'true'; });

  it('/api/ai/chat free chat is answered LOCALLY with the existing SSE protocol; zero cloud calls', async () => {
    const calls = stub(() => nd('local hello'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'My sister was diagnosed with cancer' }], role: 'chief_engineer', stream: true }));
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('text/event-stream');
    const text = await sse(res);
    expect(text).toContain('data: {"token":"local hello"}');
    expect(text).toContain('data: [DONE]');
    expect(calls.every(isLocal)).toBe(true);
    expect(calls[0].body).toContain('SHIP-CONTEXT-PRIVATE'); // context may be used locally
  });
  it('/api/ai/chat valid concept question goes to the cloud with ONLY the fixed prompt + slot', async () => {
    const calls = stub(() => nd('a mutex is...'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'what is a mutex?' }], role: 'chief_engineer', stream: true }));
    expect(res.status).toBe(200);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('https://ollama.com/api/chat');
    expect(calls[0].body).not.toContain('SHIP-CONTEXT-PRIVATE');
    expect(JSON.parse(calls[0].body).messages).toHaveLength(2);
  });
  it('/api/ai/chat: client systemPrompt, health roles and Number One chat → local only', async () => {
    const calls = stub(() => nd('ok'));
    await chatPOST(req({ messages: [{ role: 'user', content: 'what is a mutex?' }], role: 'chief_engineer', systemPrompt: 'custom', stream: true }));
    await chatPOST(req({ messages: [{ role: 'user', content: 'what is a mutex?' }], role: 'recovery_officer', stream: true }));
    await chatPOST(req({ messages: [{ role: 'user', content: 'what is a mutex?' }], role: 'number_one', stream: true }));
    expect(calls).toHaveLength(3);
    expect(calls.every(isLocal)).toBe(true);
  });
  it('/api/ai/chat: HEALTH_LLM_EXTERNAL_ALLOWED=1 does not bypass the boundary', async () => {
    process.env.HEALTH_LLM_EXTERNAL_ALLOWED = '1';
    const calls = stub(() => nd('ok'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'sleep_hours=4 pain_score 7 today' }], role: 'chief_engineer', stream: true }));
    expect(res.status).toBe(200);
    expect(calls.every(isLocal)).toBe(true);
  });
  it('/api/ai/chat: local unavailable → 424 (not 503), nothing else is sent', async () => {
    const calls = stub(() => { throw new TypeError('fetch failed'); });
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'hello' }], role: 'chief_engineer', stream: true }));
    expect(res.status).toBe(424);
    expect((await res.json()).code).toBe('local_model_unavailable');
    expect(calls.every(isLocal)).toBe(true);
  });
  it('/api/ai/chat: Number One canonical intents still work with the local model down; chat gets 424', async () => {
    stub(() => { throw new TypeError('fetch failed'); });
    const handled = await chatPOST(req({ messages: [{ id: 'm1', role: 'user', content: 'Remember this: buy milk' }], role: 'number_one', stream: true }));
    expect(handled.status).toBe(200);
    expect(await sse(handled)).toContain('Captured.');
    const chat = await chatPOST(req({ messages: [{ role: 'user', content: 'how are you' }], role: 'number_one', stream: true }));
    expect(chat.status).toBe(424);
  });
  it('/api/ai/chat: malformed bodies → 400, no outbound', async () => {
    const calls = stub(() => nd('x'));
    expect((await chatPOST(req({ messages: 'nope', role: 'chief_engineer' }))).status).toBe(400);
    expect((await chatPOST(req({ messages: [{ role: 'user', content: 7 }], role: 'chief_engineer' }))).status).toBe(400);
    expect(calls).toHaveLength(0);
  });
  it('/api/ai/chat: non-streaming response shape is preserved', async () => {
    stub(() => single('plain'));
    const res = await chatPOST(req({ messages: [{ role: 'user', content: 'hello' }], role: 'chief_engineer', stream: false }));
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ content: 'plain', role: 'chief_engineer' });
  });
  it('/api/xo: always streams; free chat local; concept to cloud; local down → 424', async () => {
    let calls = stub(() => nd('xo local'));
    let res = await xoPOST(req({ messages: [{ role: 'user', content: 'Plan my day, my mum is unwell' }] }));
    expect(res.status).toBe(200);
    expect(await sse(res)).toContain('data: {"token":"xo local"}');
    expect(calls.every(isLocal)).toBe(true);
    calls = stub(() => nd('x'));
    await xoPOST(req({ messages: [{ role: 'user', content: 'explain circuit breaker' }] }));
    expect(calls[0].url).toBe('https://ollama.com/api/chat');
    expect(calls[0].body).not.toContain('SHIP-CONTEXT-PRIVATE');
    calls = stub(() => { throw new TypeError('down'); });
    res = await xoPOST(req({ messages: [{ role: 'user', content: 'hello' }] }));
    expect(res.status).toBe(424);
    expect(calls.every(isLocal)).toBe(true);
  });
  it('/api/xo: works without OLLAMA_CLOUD_ENABLED (local-first does not need the cloud flag)', async () => {
    delete process.env.OLLAMA_CLOUD_ENABLED;
    const calls = stub(() => nd('x'));
    const res = await xoPOST(req({ messages: [{ role: 'user', content: 'what is a mutex?' }] }));
    expect(res.status).toBe(200);
    expect(calls.every(isLocal)).toBe(true);
  });
});
