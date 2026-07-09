import type { SupabaseClient } from '@supabase/supabase-js';
import { TERMINAL_STATUSES } from './missionStatus';

// MSN-0349 Objective 2: Executive Interrupt Assembly. Answers exactly one
// question - "does anything currently justify interrupting the Captain?" -
// using only real, pre-existing, already-computed upstream fields. No new
// scoring, no invented thresholds beyond what's disclosed here, no
// confidence display.
//
// Deliberately narrower than the Change Assembly's domain list:
// Decide-adjacent, Captured Items, Captain's Log, Lessons Learned, and
// Communications do NOT nominate interrupts here, because their genuine
// "needs judgement" cases already surface via Decide's "Needs you" count -
// adding a second interrupt for the same underlying fact would be the
// duplicate truth this system exists to avoid.
//
// MSN-0354 correction: Missions used to be on that exclusion list too, on
// the documented assumption that Decide's queue already covered mission
// urgency. It doesn't, and the two are not interchangeable by design: Decide
// only lists missions sitting in a status the mission-approve API actually
// accepts (APPROVAL_ELIGIBLE in app/api/missions/[id]/approve/route.ts -
// 'Awaiting Captain Approval' | 'Awaiting XO Approval' | 'Validated' |
// 'Tested'). A P0 mission stuck in 'Designed' has no approve/reject action
// available at all - it is invisible to Decide by design, not by bug, and
// would 409 if that filter were simply widened to include it (verified live
// against the real approve route, MSN-0354). Home's Interrupt Assembly is
// the right home for that fact: passive awareness that something is stuck,
// with no claim that an action route exists. See missionNominator below.
//
// The completeness rule (STARSHIP-REDESIGN.md / MSN-0349 Objective 2):
// Home may only claim "Sure" if every domain below was actually reachable
// this pass. A domain that fails to respond counts toward Unsure, never
// toward Sure - this is enforced by the caller (executiveContext.ts)
// composing verification state with this assembly's `uncheckedDomains`.

export interface Interrupt {
  domain: string;
  text: string;
  evidenceAt: string;
}

export interface InterruptAssemblyResult {
  interrupts: Interrupt[];
  uncheckedDomains: string[];
  /** True only if every registered nominator was reachable this pass. */
  complete: boolean;
}

type Nominator = (supabase: SupabaseClient) => Promise<Interrupt | null>;

/** health_insights.risk_flags is a real field already written by the
 * existing weekly synthesis pipeline - currently empty on every historical
 * row (dormant, never yet populated), same honest-dormancy pattern as the
 * old Decisions Inbox's requires_approval field. Nominates only if a real
 * flag exists; never fabricates one. */
async function healthRiskNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('health_insights')
    .select('risk_flags, generated_at')
    .order('generated_at', { ascending: false })
    .limit(1);
  const row = data?.[0];
  if (!row) return null;
  const flags = row.risk_flags as unknown;
  if (!Array.isArray(flags) || flags.length === 0) return null;
  const first = typeof flags[0] === 'string' ? flags[0] : JSON.stringify(flags[0]);
  return { domain: 'Health', text: `Health flagged a risk: ${first}.`, evidenceAt: row.generated_at as string };
}

/** operational_relevance is a real 0-1 field already computed by the
 * existing intelligence pipeline (observed range in production: 0.20-1.00,
 * mean ~0.51). 0.9 is the disclosed threshold - roughly the top 5% of
 * historical events - not a tuned score, a plain "only the rare ones"
 * cutoff stated here in one sentence. */
const OPERATIONAL_RELEVANCE_THRESHOLD = 0.9;

async function intelligenceEventNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('intelligence_events')
    .select('raw_title, published_at, operational_relevance')
    .gte('operational_relevance', OPERATIONAL_RELEVANCE_THRESHOLD)
    // Postgres sorts NULLs first in a DESC order by default - without this,
    // rows with no published_at (real production rows exist) would outrank
    // a genuinely-recent, real event and silently bury it. Found via live
    // data during MSN-0349 validation: a same-day, relevance-1.00 Telstra
    // outage event was being shadowed by null-dated rows before this fix.
    .not('published_at', 'is', null)
    .order('published_at', { ascending: false })
    .limit(1);
  const row = data?.[0];
  if (!row) return null;
  return { domain: 'Operational intelligence', text: `${row.raw_title}.`, evidenceAt: row.published_at as string };
}

/** overall_risk is a real RED/AMBER/GREEN/UNKNOWN field already computed
 * by the existing brief pipeline. Only RED nominates.
 *
 * Every text field this table has - bottom_line, top_events[].so_what,
 * emerging_themes - is LLM-generated (llm_used=true on every observed row)
 * and written as directive advisory prose ("Ensure our cyber defences are
 * robust...", "Review the bank's incident response plan..."). Quoting any
 * of it verbatim would be exactly the fabricated-synthesis / hidden-advice
 * problem MSN-0349 bans, the same reason health_insights.summary is never
 * surfaced. So this nominates on the real overall_risk fact alone and
 * states it in Starship's own plain voice - no quoted narrative, no
 * "RED" label, no colour. */
async function intelligenceBriefNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('intelligence_briefs')
    .select('generated_at, overall_risk')
    .eq('overall_risk', 'RED')
    .order('generated_at', { ascending: false })
    .limit(1);
  const row = data?.[0];
  if (!row) return null;
  return {
    domain: 'Intelligence briefs',
    text: 'The latest intelligence brief flagged elevated risk. Worth a look on the Intelligence page.',
    evidenceAt: row.generated_at as string,
  };
}

/** Priority + staleness thresholds, in days since `created_at`. P0 gets a
 * tight 3-day window, P1 a full week - the same escalation cadence already
 * disclosed and used elsewhere in this codebase for "a few days of no
 * movement is fine, a week isn't" (lib/delivery.ts's detectBottlenecks():
 * planned>3d -> medium severity, planned>7d -> high), applied here to
 * mission priority instead of delivery_state. Not a new invented scale. */
const MISSION_STALE_DAYS: Record<string, number> = { P0: 3, P1: 7 };

function daysSince(dateStr: string): number {
  const days = (Date.now() - new Date(dateStr).getTime()) / 86_400_000;
  return Number.isNaN(days) ? 0 : days;
}

interface StaleMissionRow {
  mission_id: string;
  title: string;
  status: string;
  priority: string | null;
  created_at: string;
}

/** missions is a real table already used throughout the product (Missions
 * board, Decide's mission queue). Nominates the single oldest P0/P1 mission
 * that has sat in a non-terminal status (TERMINAL_STATUSES, shared with the
 * hygiene checks - lib/missionStatus.ts) past its priority's staleness
 * threshold. Never fabricates urgency: only real priority + real created_at,
 * the same two fields Decide's own mission sort already uses
 * (lib/decisions.ts missionPriorityRank/ageBonus).
 *
 * evidenceAt is deliberately the evaluation time (now), not created_at: the
 * fact this nominates on - "this mission is still stuck, right now" - is
 * continuously true for as long as nothing changes, unlike the other three
 * nominators' evidenceAt (a real point-in-time event: when a brief/insight
 * was generated, when an intelligence event was published). Using
 * created_at here would make a multi-day-stale mission look like *older*
 * evidence than a same-day health/intel signal in selectPrimaryInterrupt's
 * "most recent wins" tie-break, which would bury the exact defect this
 * nominator exists to catch (MSN-0354: a 17-day-stale P0 mission). */
async function missionNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('missions')
    .select('mission_id, title, status, priority, created_at')
    .in('priority', Object.keys(MISSION_STALE_DAYS))
    .order('created_at', { ascending: true })
    .limit(50);
  const rows = (data ?? []) as StaleMissionRow[];
  const stale = rows.filter((m) => {
    if (TERMINAL_STATUSES.includes(m.status)) return false;
    const threshold = MISSION_STALE_DAYS[m.priority ?? ''];
    return threshold != null && daysSince(m.created_at) >= threshold;
  });
  // Rows already ascending by created_at, so the first stale row is the
  // oldest - the single most overdue mission, not just any qualifying one.
  const row = stale[0];
  if (!row) return null;
  const ageDays = Math.floor(daysSince(row.created_at));
  return {
    domain: 'Missions',
    text: `${row.priority} mission "${row.title}" has been ${row.status} for ${ageDays} day${ageDays === 1 ? '' : 's'} with no resolution.`,
    evidenceAt: new Date().toISOString(),
  };
}

// Exported (MSN-0357) so Integrity Audit / Redundancy Reconciliation
// investigations (lib/investigations/integrityAudit.ts) can read the real,
// live nominator wiring directly - by identity, not by re-declaring a
// parallel list that could itself drift from this one. Named function
// declarations are used deliberately so `fn.name` is a stable, real
// identifier those investigations can cross-reference against this
// registry's own text, without ever invoking the nominators themselves.
export const NOMINATORS: Nominator[] = [
  healthRiskNominator,
  intelligenceEventNominator,
  intelligenceBriefNominator,
  missionNominator,
];
export const DOMAIN_NAMES = ['Health', 'Operational intelligence', 'Intelligence briefs', 'Missions'];

export async function assembleInterrupts(supabase: SupabaseClient): Promise<InterruptAssemblyResult> {
  const settled = await Promise.allSettled(NOMINATORS.map((n) => n(supabase)));
  const interrupts: Interrupt[] = [];
  const uncheckedDomains: string[] = [];
  settled.forEach((result, i) => {
    if (result.status === 'fulfilled') {
      if (result.value) interrupts.push(result.value);
    } else {
      uncheckedDomains.push(DOMAIN_NAMES[i]);
    }
  });
  return { interrupts, uncheckedDomains, complete: uncheckedDomains.length === 0 };
}

/** Picks one interrupt to show, when more than one nominates. Simple,
 * disclosed tie-break: most recent evidence wins. Not a scored "engine" -
 * one sentence of logic, stated here, not hidden. */
export function selectPrimaryInterrupt(interrupts: Interrupt[]): Interrupt | null {
  if (interrupts.length === 0) return null;
  return [...interrupts].sort((a, b) => new Date(b.evidenceAt).getTime() - new Date(a.evidenceAt).getTime())[0];
}
