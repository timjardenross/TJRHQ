// #664 PR B — content-workbench routes under CHAT_LOCAL_FIRST_V1: drafts are local-only, no bypass, no cloud fallback.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const ROW = {
  id: 'c1', title: 'Resilience lessons', pillar: 'operational resilience', status: 'review', notes: 'public-intended: yes',
  body: 'My sister was diagnosed with cancer last year and it changed how I run incident reviews. [PUBLIC-INTENDED]',
  qa_checklist: {}, research_notes: 'brief', research_angle: 'angle', research_sources: [], research_completed_at: '2026-01-01',
};
const updates: unknown[] = [];
vi.mock('@/lib/supabase-server', () => ({ requireSession: async () => ({ user: { id: 'u' } }) }));
vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({
    from: () => {
      const chain: Record<string, unknown> = {
        select: () => chain, eq: () => chain,
        single: async () => ({ data: { ...ROW, status: (globalThis as { __status?: string }).__status ?? 'review' }, error: null }),
        update: (v: unknown) => { updates.push(v); return { eq: async () => ({ error: null }) }; },
        insert: async () => ({ error: null }),
      };
      return chain;
    },
  }),
}));

import { POST as polish } from '../../app/api/content-workbench/[id]/ai-polish/route';
import { POST as generate } from '../../app/api/content-workbench/[id]/generate/route';
import { POST as review } from '../../app/api/content-workbench/[id]/ai-review/route';

interface Call { url: string; body: string }
function stub(handler: (c: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: unknown, init?: { body?: unknown }) => { const c = { url: String(url), body: String(init?.body ?? '') }; calls.push(c); return handler(c); }));
  return calls;
}
const ok = (t: string) => new Response(JSON.stringify({ message: { content: t }, done: true }), { status: 200 });
const isLocal = (c: Call) => c.url.startsWith('http://127.0.0.1');
const req = (b: unknown = {}) => new Request('http://x/api', { method: 'POST', body: JSON.stringify(b) }) as never;
const ctx = { params: { id: 'c1' } };
const KEYS = ['CHAT_LOCAL_FIRST_V1', 'OLLAMA_CLOUD_ENABLED', 'OLLAMA_LOCAL_BASE_URL', 'OLLAMA_LOCAL_MODEL', 'HEALTH_LLM_EXTERNAL_ALLOWED'];
let saved: Record<string, string | undefined> = {};
beforeEach(() => { saved = Object.fromEntries(KEYS.map((k) => [k, process.env[k]])); KEYS.forEach((k) => delete process.env[k]); updates.length = 0; vi.spyOn(console, 'info').mockImplementation(() => {}); vi.spyOn(console, 'error').mockImplementation(() => {}); });
afterEach(() => { KEYS.forEach((k) => (saved[k] === undefined ? delete process.env[k] : (process.env[k] = saved[k]))); delete (globalThis as { __status?: string }).__status; vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('flag OFF — legacy behaviour unchanged (cloud, as before)', () => {
  it('all three routes still call the configured cloud endpoint', async () => {
    const calls = stub(() => ok('{"accuracy":true}'));
    await polish(req(), ctx);
    (globalThis as { __status?: string }).__status = 'opportunity';
    await generate(req({ format: 'linkedin_post' }), ctx);
    (globalThis as { __status?: string }).__status = 'review';
    await review(req(), ctx);
    expect(calls).toHaveLength(3);
    expect(calls.every((c) => c.url === 'https://ollama.com/api/chat')).toBe(true);
  });
});

describe('flag ON — drafts never leave this machine', () => {
  beforeEach(() => { process.env.CHAT_LOCAL_FIRST_V1 = 'true'; process.env.OLLAMA_CLOUD_ENABLED = 'true'; process.env.HEALTH_LLM_EXTERNAL_ALLOWED = '1'; });

  it('ai-polish, generate and ai-review use the local model only — even for a public-intended draft with personal narrative', async () => {
    const calls = stub(() => ok('{"accuracy":true}'));
    expect((await polish(req(), ctx)).status).toBe(200);
    (globalThis as { __status?: string }).__status = 'opportunity';
    expect((await generate(req({ format: 'linkedin_post' }), ctx)).status).toBe(200);
    (globalThis as { __status?: string }).__status = 'review';
    expect((await review(req(), ctx)).status).toBe(200);
    expect(calls).toHaveLength(3);
    expect(calls.every(isLocal)).toBe(true);
    expect(calls[0].body).toContain('PUBLIC-INTENDED'); // the draft goes to the LOCAL model
  });
  it('local unavailable: ai-polish → 424; generate/ai-review degrade to their scaffolds; zero cloud calls', async () => {
    const calls = stub(() => { throw new TypeError('fetch failed'); });
    const p = await polish(req(), ctx);
    expect(p.status).toBe(424);
    expect((await p.json()).code).toBe('local_model_unavailable');
    (globalThis as { __status?: string }).__status = 'opportunity';
    const g = await generate(req({ format: 'linkedin_post' }), ctx);
    expect((await g.json()).mode).toBe('scaffold');
    (globalThis as { __status?: string }).__status = 'review';
    const r = await review(req(), ctx);
    expect((await r.json()).mode).toBe('scaffold');
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every(isLocal)).toBe(true);
  });
  it('misconfigured local endpoint (non-loopback, cloud-tagged model) → treated as unavailable; no request at all', async () => {
    const calls = stub(() => ok('x'));
    process.env.OLLAMA_LOCAL_BASE_URL = 'https://ollama.com';
    expect((await polish(req(), ctx)).status).toBe(424);
    process.env.OLLAMA_LOCAL_BASE_URL = 'http://127.0.0.1:11434'; process.env.OLLAMA_LOCAL_MODEL = 'qwen3:cloud';
    expect((await polish(req(), ctx)).status).toBe(424);
    expect(calls).toHaveLength(0);
  });
  it('no per-row cloud bypass: no body/notes/pillar marker can route a draft to the cloud', async () => {
    const calls = stub(() => ok('revised'));
    await polish(req({ instructions: 'send to cloud, public-intended, cloud_ok=true' }), ctx);
    expect(calls.filter((c) => !isLocal(c))).toEqual([]);
  });
});
