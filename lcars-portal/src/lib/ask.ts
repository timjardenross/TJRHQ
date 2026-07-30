'use client';

// STARSHIP-REDESIGN.md §6: Ask. Retrieval-first, not AI-first. A small,
// fixed set of regex/keyword-matched query intents, each backed by one or
// more real, already-RLS-governed Supabase queries. No LLM anywhere in
// this file - there is no synthesis step, only fetch -> format as plain
// fact-only prose -> attach a "based on" line. An unmatched query returns
// the honest fallback rather than attempting a fuzzy guess.
//
// Explicitly does NOT call /api/captain-brief (the execFile-into-Python-CLI
// route) - that path is documented elsewhere (docs/INVENTORY.md) as fragile
// and unsuited to a hot path. Ask has no dependency on it at all.
//
// Source safety, decided with the Captain (2026-07-09):
//   included: missions, intelligence_events, intelligence_briefs,
//     lessons_learned, captured_items, captains_log_entries, decide_ledger
//   included, scoped: knowledge_documents, filtered to
//     metadata->>'sensitivity' = 'standard' (or unset). This does NOT
//     bypass current_officer_clearance() - RLS still evaluates that
//     function on every row regardless of this filter; it is a client-side
//     narrowing to the subset every session can see, so Ask never assumes
//     an elevated clearance level it isn't entitled to.
//   excluded: core_events, mission_state_transitions - both have RLS
//     enabled with zero policies defined, which is Postgres's deny-all
//     default, not an ambiguous state. Confirmed via pg_policy /
//     pg_class.relrowsecurity, not guessed.

import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

export const ASK_FALLBACK = "I don't have anything reliable on that.";

export const SUGGESTED_QUERIES = [
  'What missions are active?',
  'What did I approve today?',
  'What changed recently?',
  'Show me Telstra intelligence.',
  'What did I capture recently?',
  'What do we know about [term]?',
];

export interface AskSourceStat {
  label: string;
  count: number;
  latest?: string | null;
}

export interface AskAnswer {
  prose: string;
  basedOn: AskSourceStat[];
  /** false only when no intent pattern matched at all - the ASK_FALLBACK case. A matched intent with zero results still has matched: true. */
  matched: boolean;
}

function fmtDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
}

function listWithMore(names: string[], max = 5): string {
  if (names.length <= max) return names.join(', ');
  return `${names.slice(0, max).join(', ')}, and ${names.length - max} more`;
}

// ── Intent: active missions ─────────────────────────────────────────────

const TERMINAL_MISSION_STATUSES = ['Closed', 'Archived'];

async function answerActiveMissions(): Promise<AskAnswer> {
  const supabase = createSupabaseBrowserClient();
  const { data, count, error } = await supabase
    .from('missions')
    .select('mission_id, title, status, created_at', { count: 'exact' })
    .not('status', 'in', `(${TERMINAL_MISSION_STATUSES.join(',')})`)
    .order('created_at', { ascending: false })
    .limit(20);

  if (error || !data) {
    return { prose: "I couldn't reach the mission registry right now.", basedOn: [], matched: true };
  }

  const n = count ?? data.length;
  const latest = data[0]?.created_at ?? null;
  if (n === 0) {
    return {
      prose: 'No missions are currently active.',
      basedOn: [{ label: 'Missions', count: 0 }],
      matched: true,
    };
  }
  const names = data.map((m) => `${m.title} (${m.status})`);
  return {
    prose: `${n} mission${n === 1 ? ' is' : 's are'} active: ${listWithMore(names)}.`,
    basedOn: [{ label: 'Missions', count: n, latest }],
    matched: true,
  };
}

// ── Intent: approved today ──────────────────────────────────────────────

async function answerApprovedToday(): Promise<AskAnswer> {
  const supabase = createSupabaseBrowserClient();
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);

  const { data, count, error } = await supabase
    .from('decide_ledger')
    .select('question, source, decided_at', { count: 'exact' })
    .eq('action', 'approve')
    .gte('decided_at', startOfDay.toISOString())
    .order('decided_at', { ascending: false })
    .limit(20);

  if (error || !data) {
    return { prose: "I couldn't reach the decisions ledger right now.", basedOn: [], matched: true };
  }

  const n = count ?? data.length;
  const latest = data[0]?.decided_at ?? null;
  if (n === 0) {
    return {
      prose: "You haven't approved anything today.",
      basedOn: [{ label: 'Decide ledger', count: 0 }],
      matched: true,
    };
  }
  return {
    prose: `You approved ${n} decision${n === 1 ? '' : 's'} today: ${listWithMore(data.map((d) => d.question))}.`,
    basedOn: [{ label: 'Decide ledger', count: n, latest }],
    matched: true,
  };
}

// ── Intent: what changed recently (scoped to the approved source list -
// core_events, the platform's actual event bus, is not readable under RLS
// today, so "recently" here means recent decide/capture/log activity, not
// a full event-bus view. Named honestly in the prose, not silently narrowed.)

async function answerRecentChanges(): Promise<AskAnswer> {
  const supabase = createSupabaseBrowserClient();
  const since = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();

  const [decisions, captures, logs] = await Promise.all([
    supabase.from('decide_ledger').select('question, action, decided_at', { count: 'exact' }).gte('decided_at', since).order('decided_at', { ascending: false }).limit(5),
    supabase.from('captured_items').select('title, captured_at', { count: 'exact' }).gte('captured_at', since).order('captured_at', { ascending: false }).limit(5),
    supabase.from('captains_log_entries').select('log_date, created_at', { count: 'exact' }).gte('created_at', since).order('created_at', { ascending: false }).limit(5),
  ]);

  const decisionsCount = decisions.count ?? decisions.data?.length ?? 0;
  const capturesCount = captures.count ?? captures.data?.length ?? 0;
  const logsCount = logs.count ?? logs.data?.length ?? 0;

  const clauses: string[] = [];
  if (decisionsCount > 0) clauses.push(`${decisionsCount} decision${decisionsCount === 1 ? '' : 's'} actioned`);
  if (capturesCount > 0) clauses.push(`${capturesCount} item${capturesCount === 1 ? '' : 's'} captured`);
  if (logsCount > 0) clauses.push(`${logsCount} log entr${logsCount === 1 ? 'y' : 'ies'} recorded`);

  const basedOn: AskSourceStat[] = [
    { label: 'Decide ledger', count: decisionsCount, latest: decisions.data?.[0]?.decided_at ?? null },
    { label: 'Captured items', count: capturesCount, latest: captures.data?.[0]?.captured_at ?? null },
    { label: "Captain's log", count: logsCount, latest: logs.data?.[0]?.created_at ?? null },
  ];

  if (clauses.length === 0) {
    return {
      prose: 'Nothing recorded as changed in the last 48 hours across decisions, captures, or log entries.',
      basedOn,
      matched: true,
    };
  }
  return {
    prose: `In the last 48 hours: ${clauses.join(', ')}. (Scoped to decisions, captures, and log entries - the platform event bus isn't queryable from here yet.)`,
    basedOn,
    matched: true,
  };
}

// ── Intent: show me X intelligence ──────────────────────────────────────

async function answerIntelligenceSearch(term: string): Promise<AskAnswer> {
  const supabase = createSupabaseBrowserClient();
  const like = `%${term}%`;
  const { data, count, error } = await supabase
    .from('intelligence_events')
    .select('raw_title, organisation, published_at', { count: 'exact' })
    .or(`raw_title.ilike.${like},raw_summary.ilike.${like},enriched_summary.ilike.${like},organisation.ilike.${like}`)
    .order('published_at', { ascending: false })
    .limit(10);

  if (error || !data) {
    return { prose: "I couldn't reach intelligence events right now.", basedOn: [], matched: true };
  }

  const n = count ?? data.length;
  const latest = data[0]?.published_at ?? null;
  if (n === 0) {
    return {
      prose: `I don't have anything reliable on ${term} intelligence.`,
      basedOn: [{ label: 'Intelligence events', count: 0 }],
      matched: true,
    };
  }
  const names = data.slice(0, 5).map((e) => e.raw_title).filter(Boolean) as string[];
  return {
    prose: `${n} intelligence item${n === 1 ? '' : 's'} on ${term}: ${listWithMore(names)}.`,
    basedOn: [{ label: 'Intelligence events', count: n, latest }],
    matched: true,
  };
}

// ── Intent: what did I capture recently ─────────────────────────────────

async function answerRecentCaptures(): Promise<AskAnswer> {
  const supabase = createSupabaseBrowserClient();
  const { data, count, error } = await supabase
    .from('captured_items')
    .select('title, summary, captured_at', { count: 'exact' })
    .order('captured_at', { ascending: false })
    .limit(10);

  if (error || !data) {
    return { prose: "I couldn't reach captured items right now.", basedOn: [], matched: true };
  }

  const n = count ?? data.length;
  const latest = data[0]?.captured_at ?? null;
  if (n === 0) {
    return {
      prose: "You haven't captured anything yet.",
      basedOn: [{ label: 'Captured items', count: 0 }],
      matched: true,
    };
  }
  const names = data.slice(0, 5).map((c) => c.title || c.summary || 'Untitled capture');
  return {
    prose: `You've captured ${n} item${n === 1 ? '' : 's'}. Most recent: ${listWithMore(names)}.`,
    basedOn: [{ label: 'Captured items', count: n, latest }],
    matched: true,
  };
}

// ── Intent: what do we know about [term] - the one genuinely cross-source
// query. Deliberately NOT a synthesis: each source is searched
// independently and reported as its own fact (count + example), never
// combined into an inferred narrative. ─────────────────────────────────

interface SourceSearchResult {
  label: string;
  count: number;
  latest: string | null;
  examples: string[];
}

type SupabaseClient = ReturnType<typeof createSupabaseBrowserClient>;

async function searchMissions(supabase: SupabaseClient, like: string): Promise<SourceSearchResult> {
  const { data, count, error } = await supabase
    .from('missions').select('title, created_at', { count: 'exact' })
    .ilike('title', like).order('created_at', { ascending: false }).limit(3);
  if (error || !data) return { label: 'Missions', count: 0, latest: null, examples: [] };
  return { label: 'Missions', count: count ?? data.length, latest: data[0]?.created_at ?? null, examples: data.map((r) => String(r.title ?? '')).filter(Boolean) };
}

async function searchLessons(supabase: SupabaseClient, like: string): Promise<SourceSearchResult> {
  const { data, count, error } = await supabase
    .from('lessons_learned').select('title, created_at', { count: 'exact' })
    .or(`title.ilike.${like},lesson_text.ilike.${like}`).order('created_at', { ascending: false }).limit(3);
  if (error || !data) return { label: 'Lessons learned', count: 0, latest: null, examples: [] };
  return { label: 'Lessons learned', count: count ?? data.length, latest: data[0]?.created_at ?? null, examples: data.map((r) => String(r.title ?? '')).filter(Boolean) };
}

async function searchCaptures(supabase: SupabaseClient, like: string): Promise<SourceSearchResult> {
  const { data, count, error } = await supabase
    .from('captured_items').select('title, captured_at', { count: 'exact' })
    .or(`title.ilike.${like},summary.ilike.${like}`).order('captured_at', { ascending: false }).limit(3);
  if (error || !data) return { label: 'Captured items', count: 0, latest: null, examples: [] };
  return { label: 'Captured items', count: count ?? data.length, latest: data[0]?.captured_at ?? null, examples: data.map((r) => String(r.title ?? '')).filter(Boolean) };
}

async function searchIntelligenceEvents(supabase: SupabaseClient, like: string): Promise<SourceSearchResult> {
  const { data, count, error } = await supabase
    .from('intelligence_events').select('raw_title, published_at', { count: 'exact' })
    .or(`raw_title.ilike.${like},raw_summary.ilike.${like}`).order('published_at', { ascending: false }).limit(3);
  if (error || !data) return { label: 'Intelligence events', count: 0, latest: null, examples: [] };
  return { label: 'Intelligence events', count: count ?? data.length, latest: data[0]?.published_at ?? null, examples: data.map((r) => String(r.raw_title ?? '')).filter(Boolean) };
}

/** Scoped to standard-sensitivity documents only - see file header. RLS's
 * own clearance check still applies underneath this filter regardless. */
async function searchKnowledgeDocuments(supabase: SupabaseClient, like: string): Promise<SourceSearchResult> {
  const { data, count, error } = await supabase
    .from('knowledge_documents').select('title, created_at, metadata', { count: 'exact' })
    .or(`title.ilike.${like},content.ilike.${like}`)
    .or('metadata->>sensitivity.eq.standard,metadata->>sensitivity.is.null')
    .order('created_at', { ascending: false }).limit(3);
  if (error || !data) return { label: 'Knowledge library', count: 0, latest: null, examples: [] };
  return { label: 'Knowledge library', count: count ?? data.length, latest: data[0]?.created_at ?? null, examples: data.map((r) => String(r.title ?? '')).filter(Boolean) };
}

async function answerKnowledgeSearch(term: string): Promise<AskAnswer> {
  const supabase = createSupabaseBrowserClient();
  const like = `%${term}%`;

  const results = await Promise.all([
    searchMissions(supabase, like),
    searchLessons(supabase, like),
    searchCaptures(supabase, like),
    searchIntelligenceEvents(supabase, like),
    searchKnowledgeDocuments(supabase, like),
  ]);

  const withHits = results.filter((r) => r.count > 0);
  const basedOn: AskSourceStat[] = results
    .filter((r) => r.count > 0)
    .map((r) => ({ label: r.label, count: r.count, latest: r.latest }));

  if (withHits.length === 0) {
    return {
      prose: `I don't have anything reliable on "${term}".`,
      basedOn: [],
      matched: true,
    };
  }

  const clauses = withHits.map((r) => `${r.label}: ${r.count} match${r.count === 1 ? '' : 'es'} (e.g. "${r.examples[0]}")`);
  return {
    prose: `Here's what I found on "${term}" — ${clauses.join('. ')}.`,
    basedOn,
    matched: true,
  };
}

// ── Router ───────────────────────────────────────────────────────────────

export async function answerQuery(raw: string): Promise<AskAnswer> {
  const query = raw.trim();
  if (!query) return { prose: ASK_FALLBACK, basedOn: [], matched: false };

  if (/\bmissions?\b/i.test(query) && /\bactive\b/i.test(query)) {
    return answerActiveMissions();
  }

  if (/\bapprov(ed|e)?\b/i.test(query) && /\btoday\b/i.test(query)) {
    return answerApprovedToday();
  }

  if (/\bchang(ed|e|es)\b/i.test(query) && /\brecent(ly)?\b/i.test(query)) {
    return answerRecentChanges();
  }

  const intelMatch = query.match(/^(?:show me\s+)?(.+?)\s+intelligence\.?$/i);
  if (intelMatch && intelMatch[1].trim()) {
    return answerIntelligenceSearch(intelMatch[1].trim());
  }

  if (/\bcaptur(ed?|e)\b/i.test(query) && /\brecent(ly)?\b/i.test(query)) {
    return answerRecentCaptures();
  }

  const knowMatch = query.match(/(?:what do we know about|tell me about|what do you know about)\s+(.+)/i);
  if (knowMatch && knowMatch[1].trim()) {
    return answerKnowledgeSearch(knowMatch[1].replace(/[?.]+$/, '').trim());
  }

  return { prose: ASK_FALLBACK, basedOn: [], matched: false };
}
