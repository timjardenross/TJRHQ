import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// /api/xo and /api/ai/chat call Ollama Cloud: no personal-health text may reach it, even with cloud routing enabled.

const CTX = '=== SHIP CONTEXT === ACTIVE MISSIONS M-1';
vi.mock('@/lib/ai-context', () => ({ buildShipContext: async () => ({ text: CTX, sources: ['missions'], fetchedAt: 'x' }) }));
vi.mock('@/lib/supabase-server', () => ({
  createSupabaseServerClient: async () => ({ auth: { getSession: async () => ({ data: { session: { user: { id: 'u' } } } }) } }),
}));
vi.mock('@/lib/rateLimit', () => ({ checkRateLimit: () => true }));

import { POST as chat } from '../../ai/chat/route';
import { POST as xo } from '../route';

const req = (path: string, body: unknown) => new NextRequest(`http://localhost${path}`, { method: 'POST', body: JSON.stringify(body) });
let upstream: Array<{ url: string; body: any }>;

beforeEach(() => {
  vi.stubEnv('OLLAMA_CLOUD_ENABLED', 'true');
  vi.stubEnv('OLLAMA_API_KEY', 'k');
  vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', '');
  upstream = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    upstream.push({ url: String(url), body: JSON.parse(String(init?.body ?? '{}')) });
    return new Response(JSON.stringify({ message: { content: 'ok' } }), { status: 200 });
  }));
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

const PERSONAL = 'Captain pain 7/10, slept 4h, CPAP used, nervous system tense. What should I do today?';

describe.each([
  ['/api/ai/chat', chat, (m: string) => ({ messages: [{ role: 'user', content: m }], role: 'chief_engineer', stream: false })],
  ['/api/xo', xo, (m: string) => ({ messages: [{ role: 'user', content: m }] })],
])('%s', (path, handler, mk) => {
  it('refuses personal-health user text with 422 and makes no upstream call', async () => {
    const res = await handler(req(path, mk(PERSONAL)));
    expect(res.status).toBe(422);
    expect((await res.json()).code).toBe('personal_health_blocked');
    expect(upstream).toHaveLength(0);
  });
  it('refuses personal-health text in earlier history too', async () => {
    const body: any = mk('And what about tomorrow?');
    body.messages.unshift({ role: 'user', content: 'sleep_hours=4 pain_score 7' });
    expect((await handler(req(path, body))).status).toBe(422);
    expect(upstream).toHaveLength(0);
  });
  it('still serves ordinary questions, sending only the (health-free) ship context', async () => {
    const res = await handler(req(path, mk('Summarise the active missions')));
    expect(res.status).toBe(200);
    expect(upstream).toHaveLength(1);
    expect(JSON.stringify(upstream[0].body)).toContain('M-1');
    expect(JSON.stringify(upstream[0].body)).not.toMatch(/pain|CPAP|nervous system/i);
  });
  it('explicit opt-in lifts the refusal', async () => {
    vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', '1');
    expect((await handler(req(path, mk(PERSONAL)))).status).toBe(200);
  });
});
