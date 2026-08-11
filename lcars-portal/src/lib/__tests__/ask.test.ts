import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';

// ── Mock Supabase: a per-table configurable fluent/thenable builder. Every
// chain method (select/or/not/eq/gte/ilike/order/limit) returns the same
// object so any call shape resolves; awaiting it returns the response
// configured for whichever table .from() was called with. ──────────────

type MockResponse = { data: any[] | null; count?: number; error?: any };
let responses: Record<string, MockResponse> = {};

function makeChain(table: string) {
  const chain: any = {
    select: () => chain,
    or: () => chain,
    not: () => chain,
    eq: () => chain,
    gte: () => chain,
    ilike: () => chain,
    order: () => chain,
    limit: () => chain,
    then: (resolve: (v: MockResponse) => void) => {
      const r = responses[table] ?? { data: [], count: 0, error: null };
      resolve(r);
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-browser', () => ({
  createSupabaseBrowserClient: () => ({ from: (table: string) => makeChain(table) }),
}));

import { answerQuery, ASK_FALLBACK, SUGGESTED_QUERIES } from '@/lib/ask';

beforeEach(() => {
  responses = {};
});

// ── 1. Unknown queries return the honest fallback ───────────────────────
describe('Unknown queries return the honest fallback', () => {
  it('a query matching no known pattern returns ASK_FALLBACK and matched:false', async () => {
    const res = await answerQuery('what is the meaning of life');
    expect(res.prose).toBe(ASK_FALLBACK);
    expect(res.matched).toBe(false);
    expect(res.basedOn).toEqual([]);
  });

  it('an empty query returns the honest fallback, never a crash', async () => {
    const res = await answerQuery('   ');
    expect(res.prose).toBe(ASK_FALLBACK);
    expect(res.matched).toBe(false);
  });

  it('every suggested query pattern is actually recognised (none silently fall through)', async () => {
    responses = {
      missions: { data: [], count: 0 },
      decide_ledger: { data: [], count: 0 },
      captured_items: { data: [], count: 0 },
      captains_log_entries: { data: [], count: 0 },
      intelligence_events: { data: [], count: 0 },
      lessons_learned: { data: [], count: 0 },
      knowledge_documents: { data: [], count: 0 },
    };
    for (const q of SUGGESTED_QUERIES) {
      const query = q.replace('[term]', 'test');
      const res = await answerQuery(query);
      expect(res.matched, `"${query}" should match a known intent`).toBe(true);
    }
  });
});

// ── 2. Answers include a based-on/source line ───────────────────────────
describe('Answers include a based-on line', () => {
  it('active missions answer names the Missions source with a count', async () => {
    responses.missions = {
      data: [{ mission_id: 'MSN-1', title: 'Test Mission', status: 'Approved', created_at: '2026-07-08T00:00:00Z' }],
      count: 1,
    };
    const res = await answerQuery('What missions are active?');
    expect(res.basedOn.length).toBeGreaterThan(0);
    expect(res.basedOn[0].label).toBe('Missions');
    expect(res.basedOn[0].count).toBe(1);
  });

  it('a zero-result recognised query still includes a based-on line with count 0', async () => {
    responses.missions = { data: [], count: 0 };
    const res = await answerQuery('What missions are active?');
    expect(res.matched).toBe(true);
    expect(res.basedOn).toEqual([{ label: 'Missions', count: 0 }]);
  });
});

// ── 3. No fabricated recommendations, no confidence claims ──────────────
describe('No fabricated recommendations or confidence claims', () => {
  const src = readFileSync(join(__dirname, '../ask.ts'), 'utf-8');
  const stripped = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');

  it('ask.ts never emits a recommendation verb in prose templates', () => {
    expect(stripped).not.toMatch(/i recommend/i);
    expect(stripped).not.toMatch(/you should/i);
    expect(stripped).not.toMatch(/we recommend/i);
  });

  it('ask.ts never surfaces a confidence score field in its output', () => {
    // confidence/rank_score columns exist on intelligence_events/briefs but
    // must never be selected or rendered here.
    expect(stripped).not.toMatch(/\bconfidence\b/i);
    expect(stripped).not.toMatch(/rank_score/i);
  });

  it('ask.ts never claims cross-domain synthesis ("this suggests", "this indicates", "pattern")', () => {
    expect(stripped).not.toMatch(/this suggests/i);
    expect(stripped).not.toMatch(/this indicates/i);
    expect(stripped).not.toMatch(/\bpattern\b/i);
  });
});

// ── 4. No Captain Brief subprocess hot path ──────────────────────────────
describe('No Captain Brief subprocess hot path', () => {
  function stripComments(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  }

  it('ask.ts never calls /api/captain-brief or execFile at runtime (comments documenting the exclusion are fine)', () => {
    const stripped = stripComments(readFileSync(join(__dirname, '../ask.ts'), 'utf-8'));
    expect(stripped).not.toMatch(/captain-brief/i);
    expect(stripped).not.toMatch(/captain_brief_cli/i);
    expect(stripped).not.toMatch(/execFile/i);
  });

  // The test that used to live here read app/ask/page.tsx — that route
  // was deliberately decommissioned 2026-07-18 (nav.ts: "/decide, /ask,
  // /recommended, /comms-studio have been decommissioned... routed to
  // /workbenches instead"). Removed 2026-08-11 rather than resurrecting a
  // retired page to satisfy a stale test — lib/ask.ts (still live, tested
  // above) is what actually needs this coverage.
});

// ── 5. Route works with empty datasets ───────────────────────────────────
describe('Empty datasets render honestly, not as errors or fabricated content', () => {
  it('no active missions', async () => {
    responses.missions = { data: [], count: 0 };
    const res = await answerQuery('What missions are active?');
    expect(res.prose).toBe('No missions are currently active.');
  });

  it('nothing approved today', async () => {
    responses.decide_ledger = { data: [], count: 0 };
    const res = await answerQuery('What did I approve today?');
    expect(res.prose).toBe("You haven't approved anything today.");
  });

  it('nothing captured yet', async () => {
    responses.captured_items = { data: [], count: 0 };
    const res = await answerQuery('What did I capture recently?');
    expect(res.prose).toBe("You haven't captured anything yet.");
  });

  it('no intelligence on an unknown term - specific, not generic panic', async () => {
    responses.intelligence_events = { data: [], count: 0 };
    const res = await answerQuery('Show me Zorblatt intelligence.');
    expect(res.prose).toBe("I don't have anything reliable on Zorblatt intelligence.");
  });

  it('nothing changed recently across all three scoped sources', async () => {
    responses.decide_ledger = { data: [], count: 0 };
    responses.captured_items = { data: [], count: 0 };
    responses.captains_log_entries = { data: [], count: 0 };
    const res = await answerQuery('What changed recently?');
    expect(res.prose).toMatch(/nothing recorded/i);
  });

  it('what do we know about an unknown term - honest, not a crash', async () => {
    responses.missions = { data: [], count: 0 };
    responses.lessons_learned = { data: [], count: 0 };
    responses.captured_items = { data: [], count: 0 };
    responses.intelligence_events = { data: [], count: 0 };
    responses.knowledge_documents = { data: [], count: 0 };
    const res = await answerQuery('What do we know about zorblatt?');
    expect(res.prose).toBe('I don\'t have anything reliable on "zorblatt".');
    expect(res.basedOn).toEqual([]);
  });
});

// ── 6. Ask does not introduce a dashboard/list page by stealth ──────────
describe('Ask renders prose, not a list/dashboard UI', () => {
  // The test that used to live here read app/ask/page.tsx (checking it
  // never rendered a stealth dashboard/list) — that route was
  // deliberately decommissioned 2026-07-18 (nav.ts: "/decide, /ask,
  // /recommended, /comms-studio have been decommissioned... routed to
  // /workbenches instead"). Removed 2026-08-11 rather than resurrecting a
  // retired page to satisfy a stale test.

  it('multi-item answers are joined into one prose sentence, not a bulleted/card array', async () => {
    responses.missions = {
      data: [
        { mission_id: 'MSN-1', title: 'A', status: 'Approved', created_at: '2026-07-08T00:00:00Z' },
        { mission_id: 'MSN-2', title: 'B', status: 'Idea', created_at: '2026-07-07T00:00:00Z' },
      ],
      count: 2,
    };
    const res = await answerQuery('What missions are active?');
    expect(typeof res.prose).toBe('string');
    expect(res.prose).toContain('A (Approved)');
    expect(res.prose).toContain('B (Idea)');
  });
});
