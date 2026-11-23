import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// In-app consent is not authorisation for external processing: guidance is local-only unless HEALTH_LLM_EXTERNAL_ALLOWED=1.

const inserts: unknown[] = [];
const updates: string[] = [];
function table(name: string) {
  const payload: Record<string, unknown> = { pain_recovery_sessions: { id: 's1' }, pain_recovery_consents: { status: 'granted', main_consent: true, free_text_consent: false, medications_consent: false } };
  const b: any = new Proxy({}, {
    get(_t, prop) {
      if (prop === 'then') return (res: (v: unknown) => void) => res({ data: name === 'pain_recovery_consents' ? payload[name] : [], error: null });
      if (prop === 'maybeSingle') return () => Promise.resolve({ data: payload[name] ?? null, error: null });
      if (prop === 'update') return () => { updates.push(name); return b; };
      if (prop === 'insert') return (row: unknown) => { inserts.push(row); return Promise.resolve({ error: null }); };
      return () => b;
    },
  });
  return b;
}
vi.mock('@/lib/supabase-server', () => ({
  requireValidatedUser: async () => ({ id: 'user-1' }),
  createSupabaseServerClient: async () => ({ from: (t: string) => table(t) }),
}));

import { POST } from '../route';

const GOOD = JSON.stringify({ message: 'Take one small step.', next_action: 'Stand and stretch', choices: [], action_type: 'continue', safety_instruction: 'none', practice: null, resources: [] });
let urls: string[];
function stub(local: 'down' | string) {
  urls = [];
  vi.stubGlobal('fetch', vi.fn(async (u: string) => {
    const url = String(u); urls.push(url);
    if (url.includes('127.0.0.1:11434')) {
      if (local === 'down') throw new Error('ECONNREFUSED');
      return new Response(JSON.stringify({ message: { content: local } }), { status: 200 });
    }
    if (url.includes(':8891')) return new Response(JSON.stringify({ text: GOOD }), { status: 200 });
    return new Response('{}', { status: 500 });
  }));
}
const call = () => POST(new NextRequest('http://localhost/api/pain-recovery-studio/guide', { method: 'POST', body: JSON.stringify({ current_stage: 'morning', user_request: 'plan my day' }) }));

beforeEach(() => { inserts.length = 0; updates.length = 0; vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', ''); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe('pain recovery guide: local-only by default', () => {
  it('local down + no opt-in: authored fallback, the Model Router is never called', async () => {
    stub('down');
    const json = await (await call()).json();
    expect(json.source).toBe('safe_fallback');
    expect(json.response.message).toBeTruthy();
    expect(urls.some((u) => u.includes(':8891'))).toBe(false);
    expect((inserts[0] as any).provider).toBe('safe_fallback');
  });
  it('local model answers: used and labelled local, no router call', async () => {
    stub(GOOD);
    const json = await (await call()).json();
    expect(json.source).toBe('local');
    expect(urls.some((u) => u.includes(':8891'))).toBe(false);
    expect((inserts[0] as any).provider).toBe('local-ollama');
  });
  it('explicit opt-in: router used only after local fails', async () => {
    vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', '1');
    stub('down');
    const json = await (await call()).json();
    expect(json.source).toBe('gemini');
    expect(urls.some((u) => u.includes(':8891'))).toBe(true);
  });
});


describe('pain recovery guide: deadline handling', () => {
  it('bounds the local attempt to ~7 s so the fallback can answer inside the client\'s 10 s deadline', async () => {
    stub('down');
    const spy = vi.spyOn(AbortSignal, 'timeout');
    await call();
    const ms = spy.mock.calls.map((c) => c[0]);
    expect(ms).toContain(7000);
    expect(ms).not.toContain(20000);
    spy.mockRestore();
  });
  it('does not advance the session for a request the client already abandoned', async () => {
    stub(GOOD);
    const ac = new AbortController();
    ac.abort();
    await POST(new NextRequest('http://localhost/api/pain-recovery-studio/guide', { method: 'POST', body: JSON.stringify({ current_stage: 'morning' }), signal: ac.signal }));
    expect(updates).not.toContain('pain_recovery_sessions');
  });
  it('still advances the session for a live request', async () => {
    stub(GOOD);
    await call();
    expect(updates).toContain('pain_recovery_sessions');
  });
});
