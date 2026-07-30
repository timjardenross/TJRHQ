import type { SupabaseClient } from '@supabase/supabase-js';

// MSN-0349 Objective 1: Executive Change Assembly. Answers exactly one
// question - "what meaningfully changed since the Captain last looked?" -
// as a short, fact-based summary. Never a raw event list, never a
// timeline, never a replay. Each domain contributes at most one clause;
// the composer joins them into one or two sentences.
//
// health_insights.summary is deliberately never used here - it's an
// LLM-generated weekly narrative written in third-person "crew of USS TJR"
// bridge-crew-fiction voice, exactly the register STARSHIP-REDESIGN.md
// bans from Captain-facing copy. Health's contribution is computed from
// raw health_daily_logs numbers instead - a real, auditable, first-person
// statement, not a quoted narrative.

export interface ChangeClause {
  domain: string;
  text: string;
  count: number;
  latest: string | null;
}

export interface ChangeAssemblyResult {
  clauses: ChangeClause[];
  /** Domains whose query failed this pass - disclosed, never silently dropped. */
  uncheckedDomains: string[];
}

type Detector = (supabase: SupabaseClient, sinceISO: string) => Promise<ChangeClause | null>;

async function missionsChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('missions')
    .select('title, closed_at', { count: 'exact' })
    .gte('closed_at', sinceISO)
    .order('closed_at', { ascending: false })
    .limit(3);
  if (!data || count === 0) return null;
  const text = count === 1 ? `Mission completed: ${data[0].title}.` : `${count} missions completed.`;
  return { domain: 'Missions', text, count: count ?? 0, latest: data[0]?.closed_at ?? null };
}

async function decisionsChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('decide_ledger')
    .select('action, decided_at', { count: 'exact' })
    .gte('decided_at', sinceISO)
    .order('decided_at', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text = `${count} decision${count === 1 ? '' : 's'} actioned.`;
  return { domain: 'Decide ledger', text, count: count ?? 0, latest: data[0]?.decided_at ?? null };
}

async function captainsLogChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('captains_log_entries')
    .select('created_at', { count: 'exact' })
    .gte('created_at', sinceISO)
    .order('created_at', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text = `${count} log entr${count === 1 ? 'y' : 'ies'} recorded.`;
  return { domain: "Captain's log", text, count: count ?? 0, latest: data[0]?.created_at ?? null };
}

async function capturedItemsChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('captured_items')
    .select('captured_at', { count: 'exact' })
    .gte('captured_at', sinceISO)
    .order('captured_at', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text = `${count} item${count === 1 ? '' : 's'} captured.`;
  return { domain: 'Captured items', text, count: count ?? 0, latest: data[0]?.captured_at ?? null };
}

async function intelligenceEventsChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('intelligence_events')
    .select('raw_title, published_at, operational_relevance', { count: 'exact' })
    .not('raw_title', 'ilike', 'CVE-%')
    .gte('published_at', sinceISO)
    .order('operational_relevance', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text =
    count === 1
      ? `New intelligence: ${data[0].raw_title}.`
      : `${count} new intelligence events, most notably "${data[0].raw_title}".`;
  return { domain: 'Intelligence events', text, count: count ?? 0, latest: data[0]?.published_at ?? null };
}

async function intelligenceBriefsChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('intelligence_briefs')
    .select('generated_at', { count: 'exact' })
    .gte('generated_at', sinceISO)
    .order('generated_at', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text = `${count} intelligence brief${count === 1 ? '' : 's'} generated.`;
  return { domain: 'Intelligence briefs', text, count: count ?? 0, latest: data[0]?.generated_at ?? null };
}

async function lessonsLearnedChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('lessons_learned')
    .select('created_at', { count: 'exact' })
    .gte('created_at', sinceISO)
    .order('created_at', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text = `${count} lesson${count === 1 ? '' : 's'} recorded.`;
  return { domain: 'Lessons learned', text, count: count ?? 0, latest: data[0]?.created_at ?? null };
}

async function knowledgeChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('knowledge_documents')
    .select('created_at', { count: 'exact' })
    .gte('created_at', sinceISO)
    .or('metadata->>sensitivity.eq.standard,metadata->>sensitivity.is.null')
    .order('created_at', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text = `${count} document${count === 1 ? '' : 's'} reviewed into Knowledge.`;
  return { domain: 'Knowledge', text, count: count ?? 0, latest: data[0]?.created_at ?? null };
}

async function commsChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('comms_content')
    .select('updated_at', { count: 'exact' })
    .eq('status', 'published')
    .gte('updated_at', sinceISO)
    .order('updated_at', { ascending: false })
    .limit(1);
  if (!data || count === 0) return null;
  const text = `${count} piece${count === 1 ? '' : 's'} of content published.`;
  return { domain: 'Communications', text, count: count ?? 0, latest: data[0]?.updated_at ?? null };
}

/** Computed from raw health_daily_logs numbers only - never the LLM
 * narrative in health_insights.summary. A trend is only stated if there
 * are at least 2 entries with a real pain_score to compare - otherwise
 * this domain contributes nothing rather than guessing. */
async function healthChanged(supabase: SupabaseClient, sinceISO: string): Promise<ChangeClause | null> {
  const { data, count } = await supabase
    .from('health_daily_logs')
    .select('pain_score, logged_at', { count: 'exact' })
    .gte('logged_at', sinceISO)
    .not('pain_score', 'is', null)
    .order('logged_at', { ascending: true })
    .limit(10);
  if (!data || data.length === 0) return null;
  if (data.length < 2) {
    return { domain: 'Health', text: '1 health log entry recorded.', count: count ?? data.length, latest: data[0].logged_at };
  }
  const first = data[0].pain_score as number;
  const last = data[data.length - 1].pain_score as number;
  const latest = data[data.length - 1].logged_at as string;
  let text: string;
  if (last < first) text = `Pain trending down over your last ${data.length} entries.`;
  else if (last > first) text = `Pain trending up over your last ${data.length} entries.`;
  else text = `${data.length} health log entries recorded, pain steady.`;
  return { domain: 'Health', text, count: count ?? data.length, latest };
}

const DETECTORS: Detector[] = [
  missionsChanged,
  decisionsChanged,
  captainsLogChanged,
  capturedItemsChanged,
  intelligenceEventsChanged,
  intelligenceBriefsChanged,
  lessonsLearnedChanged,
  knowledgeChanged,
  commsChanged,
  healthChanged,
];

const DOMAIN_NAMES = [
  'Missions', 'Decide ledger', "Captain's log", 'Captured items', 'Intelligence events',
  'Intelligence briefs', 'Lessons learned', 'Knowledge', 'Communications', 'Health',
];

export async function assembleChanges(supabase: SupabaseClient, sinceISO: string): Promise<ChangeAssemblyResult> {
  const settled = await Promise.allSettled(DETECTORS.map((d) => d(supabase, sinceISO)));
  const clauses: ChangeClause[] = [];
  const uncheckedDomains: string[] = [];
  settled.forEach((result, i) => {
    if (result.status === 'fulfilled') {
      if (result.value) clauses.push(result.value);
    } else {
      uncheckedDomains.push(DOMAIN_NAMES[i]);
    }
  });
  return { clauses, uncheckedDomains };
}

/** Plain prose composition. Caps at 4 clauses so this never becomes a list
 * masquerading as a sentence - if more than 4 domains report a change,
 * name the top 4 by count and note the rest exist without itemising them. */
export function composeChangeText(result: ChangeAssemblyResult): string {
  const { clauses, uncheckedDomains } = result;
  if (clauses.length === 0) {
    return uncheckedDomains.length > 0
      ? "Nothing notable changed since your last session, as far as I could check."
      : 'Nothing notable changed since your last session.';
  }
  const sorted = [...clauses].sort((a, b) => b.count - a.count);
  const shown = sorted.slice(0, 4);
  const rest = sorted.length - shown.length;
  let text = shown.map((c) => c.text).join(' ');
  if (rest > 0) text += ` (${rest} more source${rest === 1 ? '' : 's'} also had activity.)`;
  if (uncheckedDomains.length > 0) text += ` I couldn't check ${uncheckedDomains.join(', ')} just now.`;
  return text;
}
