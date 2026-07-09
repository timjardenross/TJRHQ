import type { SupabaseClient } from '@supabase/supabase-js';

// MSN-0349 Objective 2: Executive Interrupt Assembly. Answers exactly one
// question - "does anything currently justify interrupting the Captain?" -
// using only real, pre-existing, already-computed upstream fields. No new
// scoring, no invented thresholds beyond what's disclosed here, no
// confidence display.
//
// Deliberately narrower than the Change Assembly's domain list: Missions,
// Decide-adjacent, Captured Items, Captain's Log, Lessons Learned, and
// Communications do NOT nominate interrupts here, because their genuine
// "needs judgement" cases already surface via Decide's "Needs you" count -
// adding a second interrupt for the same underlying fact would be the
// duplicate truth this system exists to avoid.
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
    .order('published_at', { ascending: false })
    .limit(1);
  const row = data?.[0];
  if (!row) return null;
  return { domain: 'Operational intelligence', text: `${row.raw_title}.`, evidenceAt: row.published_at as string };
}

/** overall_risk is a real RED/AMBER/GREEN/UNKNOWN field already computed
 * by the existing brief pipeline. Only RED nominates. The Captain-facing
 * text uses the brief's own plain-language bottom_line, never the raw
 * "RED" label or a colour badge - STARSHIP-REDESIGN.md bans red/alarm
 * styling; this is a real upstream classification informing a calm
 * sentence, not a UI alert. */
async function intelligenceBriefNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('intelligence_briefs')
    .select('bottom_line, generated_at, overall_risk')
    .eq('overall_risk', 'RED')
    .order('generated_at', { ascending: false })
    .limit(1);
  const row = data?.[0];
  if (!row || !row.bottom_line) return null;
  return { domain: 'Intelligence briefs', text: row.bottom_line as string, evidenceAt: row.generated_at as string };
}

const NOMINATORS: Nominator[] = [healthRiskNominator, intelligenceEventNominator, intelligenceBriefNominator];
const DOMAIN_NAMES = ['Health', 'Operational intelligence', 'Intelligence briefs'];

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
