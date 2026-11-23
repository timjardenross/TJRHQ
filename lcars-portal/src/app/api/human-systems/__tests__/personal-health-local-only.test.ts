import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Personal capacity / pain / recovery data on the trends and clinician-report routes is processed locally only;
// Gemini/Mistral run only on an explicit opt-in, and the deterministic fallback stands in otherwise.

const today = new Date();
const day = (n: number) => { const d = new Date(today); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };
const row = (n: number) => ({ log_date: day(n), energy: 'Low', nervous_system_state: 'Activated', capacity_state: 'Amber', stimulation_state: null,
  pain_state: 'High', pain_score: 7, regulation_state: null, executive_function: null, compensation_load: null, emotional_state: null, social_state: null });

vi.mock('@/lib/supabase-server', () => ({
  requireSession: async () => ({ user: { email: 'captain@example.com' } }),
  createSupabaseServerClient: async () => ({}),
}));
vi.mock('../trends/data', () => ({ fetchTrendRows: async () => [row(1), row(2), row(3), row(4)] }));

import { GET as getReport } from '../report/route';
import { GET as getTrends } from '../trends/route';

const req = (p: string) => new NextRequest(`http://localhost${p}`);
const EXTERNAL = /generativelanguage\.googleapis\.com|api\.mistral\.ai/;
let urls: string[];

function stubFetch(local: 'down' | { content: string }) {
  urls = [];
  vi.stubGlobal('fetch', vi.fn(async (u: string | URL) => {
    const url = String(u); urls.push(url);
    if (url.includes('127.0.0.1:11434')) {
      if (local === 'down') throw new Error('ECONNREFUSED');
      return new Response(JSON.stringify({ message: { content: local.content } }), { status: 200 });
    }
    if (url.includes('generativelanguage')) return new Response(JSON.stringify({ candidates: [{ content: { parts: [{ text: 'GEMINI TEXT' }] } }] }), { status: 200 });
    return new Response('{}', { status: 500 });
  }));
}

beforeEach(() => {
  vi.stubEnv('GEMINI_API_KEY', 'k');
  vi.stubEnv('MISTRAL_API_KEY', 'k');
  vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', '');
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe('trends summary', () => {
  it('local model down + no opt-in: no external request, summary falls back to null', async () => {
    stubFetch('down');
    const json = await (await getTrends(req('/api/human-systems/trends'))).json();
    expect(json.summary).toBeNull();
    expect(urls.some((u) => EXTERNAL.test(u))).toBe(false);
  });
  it('local model answers: used, and nothing external is called', async () => {
    stubFetch({ content: 'Local trend summary.' });
    const json = await (await getTrends(req('/api/human-systems/trends'))).json();
    expect(json.summary).toBe('Local trend summary.');
    expect(urls.every((u) => !EXTERNAL.test(u))).toBe(true);
  });
  it('explicit opt-in: external chain is used when local is down', async () => {
    vi.stubEnv('HEALTH_LLM_EXTERNAL_ALLOWED', '1');
    stubFetch('down');
    const json = await (await getTrends(req('/api/human-systems/trends'))).json();
    expect(json.summary).toBe('GEMINI TEXT');
  });
});

describe('clinician report', () => {
  it('local model down + no opt-in: deterministic fallback, no external request', async () => {
    stubFetch('down');
    const json = await (await getReport(req('/api/human-systems/report'))).json();
    expect(json.source).toBe('fallback');
    expect(json.report.highlights.length).toBeGreaterThan(0);
    expect(urls.some((u) => EXTERNAL.test(u))).toBe(false);
  });
  it('local model returns valid JSON: used as the report, nothing external', async () => {
    stubFetch({ content: JSON.stringify({ highlights: ['h'], changes: ['c'], focus: ['f'] }) });
    const json = await (await getReport(req('/api/human-systems/report'))).json();
    expect(json.source).toBe('llm');
    expect(json.report).toEqual({ highlights: ['h'], changes: ['c'], focus: ['f'] });
    expect(urls.every((u) => !EXTERNAL.test(u))).toBe(true);
  });
  it('local model returns malformed output: fallback, still no external request', async () => {
    stubFetch({ content: 'not json' });
    const json = await (await getReport(req('/api/human-systems/report'))).json();
    expect(json.source).toBe('fallback');
    expect(urls.some((u) => EXTERNAL.test(u))).toBe(false);
  });
});
