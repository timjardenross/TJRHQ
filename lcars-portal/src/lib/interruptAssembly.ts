import type { SupabaseClient } from '@supabase/supabase-js';
import { TERMINAL_STATUSES } from './missionStatus';
import { scanEscalation } from './human-systems';

// MSN-0349 Objective 2: Executive Interrupt Assembly. Answers exactly one
// question - "does anything currently justify interrupting the Captain?" -
// using only real, pre-existing, already-computed upstream fields. No new
// scoring, no invented thresholds beyond what's disclosed here, no
// confidence display.
//
// Deliberately narrower than the Change Assembly's domain list:
// Decide-adjacent, Captain's Log, Lessons Learned, and Communications do
// NOT nominate interrupts here, because their genuine "needs judgement"
// cases already surface via Decide's "Needs you" count - adding a second
// interrupt for the same underlying fact would be the duplicate truth this
// system exists to avoid.
//
// MSN-0358 correction: Captured Items used to be on that exclusion list
// too, on the same documented assumption as the MSN-0354 Missions
// correction below - that Decide's queue already covered its "needs
// judgement" case. It didn't: fetchDecideQueue() (lib/decide.ts) and its
// mission source, fetchMissionDecisions() (lib/decisions.ts), only ever
// read `missions` and `build_request_inbox`, never `captured_items` - a
// captured item flagged as a mission but not yet triaged was invisible to
// Decide by design, not by bug. The fix is a new nominator here
// (capturedMissionNominator below), not a widened Decide query: triaging a
// capture is a routing decision (review/route/promote via /capture), not
// an approve/reject action, and decide.ts's own header already declines to
// invent a mapping onto its Approve/Hold/Undo model for exactly this shape
// of item (Knowledge Library review). Home's passive "this needs your
// attention" nominator is the right fit; Decide's governed queue is
// intentionally not widened to cover it.
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

// ── alerts.ts reconciliation (EOS Canonical Architecture Decisions §1) ────────
//
// lib/alerts.ts's computeAlerts() is real, live production logic that powers
// /captains-chair (now a supporting experience, not Home - see the Canonical
// Architecture Decisions doc). It is not deleted here - captains-chair still
// depends on it - but its five real alert classes (decision / escalation /
// delivery_failure / eng_review / wellness) are checked below against what
// this file and Decide (lib/decisions.ts / lib/decide.ts) already surface,
// and reconciled as new nominators only where the underlying condition is
// genuinely not visible anywhere else today:
//
//   decision (captured missions awaiting triage, captured_items table) -
//   MSN-0358: ADDED as capturedMissionNominator below, resolving the design
//   call this note used to leave open (a new nominator here, or a widened
//   Decide query - two different fixes with different implications for the
//   "duplicate truth" goal this file exists to serve). Direction: a new
//   nominator, for two grounded reasons, not a coin flip. (1) EOS Canonical
//   Architecture Decisions §1 directs alerts.ts's real logic to be
//   "reconciled into interruptAssembly.ts's nominator pattern (as additional
//   nominators)" - this is exactly that, for the one alert class this file's
//   own header incorrectly claimed was already covered. (2) decide.ts's own
//   header states its sources are "exactly the two governed, already-real
//   approve/reject routes" and already declines to fold in Knowledge Library
//   review items for the identical reason: no governed approve/reject action
//   exists for them, and collapsing a different action shape onto Decide's
//   Approve/Hold/Undo model would be inventing governance, not reusing it.
//   Captured-item triage is that same shape - review/route/promote via
//   /capture, not approve/reject - so it fails Decide's own stated inclusion
//   bar exactly as Knowledge Library did. Home's passive nominator is the
//   correct fit; Decide's queue is intentionally left unwidened.
//
//   escalation / wellness (lib/alerts.ts wellnessAlerts()) - genuinely new.
//   These read capacity_checkins (recovery_pulses' successor) / the
//   get_recovery_posture RPC, sources healthRiskNominator above never
//   touches (it reads health_insights.
//   risk_flags only, which is a separate, currently-dormant table). Three
//   nominators added below, one per real condition already disclosed in
//   alerts.ts: recoveryEscalationNominator, recoveryPostureNominator,
//   painTrendNominator. alerts.ts's remaining two wellness/escalation
//   conditions (recovery-debt-high, emotional-load-raised) require
//   multi-day derived bands (recoveryDebt()/fetchEmotionalLoadFlag() in
//   lib/human-systems.ts and lib/ros-data.ts) rather than a single real
//   field - left running as-is on /captains-chair rather than re-derived
//   here, consistent with the Canonical Architecture Decisions' note that
//   Human Systems & Recovery already has its own quiet Home-level pattern
//   that should be kept, not multiplied.
//
//   delivery_failure (lib/alerts.ts engineeringAlerts()) - genuinely new.
//   Two real conditions, two nominators: deliveryBlockedNominator (mission_
//   delivery view, delivery_state='blocked') and failedDispatchNominator
//   (mission_execution_events, status='failed' in the last 3 days). Neither
//   table is read by Decide or any existing nominator.
//
//   eng_review (lib/alerts.ts engineeringAlerts()) - split findings. The
//   build_request_inbox half (alerts.ts's build-review-* condition, status
//   in ('in_review','awaiting_review')) IS already covered: Decide's
//   fetchEngineeringDecisions()/fetchDecideQueue() (lib/decisions.ts,
//   lib/decide.ts) reads the same table via fetchEngineeringQueue()
//   (lib/engineering-queue.ts), whose normalizeLifecycle() maps those exact
//   status strings to 'awaiting_review' - a real, already-counted duplicate,
//   so no nominator is added for it. The mission_delivery half (alerts.ts's
//   eng-review-* condition, delivery_state='in_review' with P0/P1 priority)
//   is NOT covered: fetchEngineeringQueue() only counts build_request_inbox
//   rows toward Decide's engineering source (`source === 'build'` is
//   filtered explicitly), so a P0/P1 mission sitting in a delivery-source
//   in_review row is invisible to Decide today - the same shape of gap
//   MSN-0354 found for stale missions. engineeringReviewNominator below
//   covers that real, uncovered half only.

/** get_recovery_posture is the same real RPC lib/ros-data.ts's
 * fetchRecoveryPosture() already calls for the daily posture panel. REST is
 * that RPC's own worst band (STRONG/STABLE/FRAGILE/REST - ros-data.ts's
 * derivePostureFromRow) - not a threshold invented here. Mirrors alerts.ts's
 * wellness-capacity-critical restPosture branch. evidenceAt is the
 * evaluation time, same rationale as missionNominator above: posture is a
 * continuously-true-until-it-changes fact, not a point-in-time event. */
async function recoveryPostureNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const todayIso = new Date().toISOString().slice(0, 10);
  const { data } = await supabase
    .rpc('get_recovery_posture', { p_date: todayIso })
    .single<{ posture: string; posture_message: string }>();
  if (!data || data.posture !== 'REST') return null;
  return {
    domain: 'Recovery posture',
    text: data.posture_message || 'Recovery posture is REST - minimal capacity today.',
    evidenceAt: new Date().toISOString(),
  };
}

/** scanEscalation is the exact existing red-flag detector (lib/human-
 * systems.ts) alerts.ts already runs over the day's merged human-systems
 * row - reused verbatim, no new keyword/negation logic. Reads the single
 * most recent capacity_checkins entry directly (realigned 2026-08-22;
 * recovery_pulses was the actively-written real-time channel until MY
 * CAPACITY TODAY replaced it) - scans both `notes` (deep-check general
 * note) and `trigger_note` (deep-check "what happened before" note), since
 * either free-text field could carry a red-flag phrase. Mirrors alerts.ts's
 * wellness-redflag condition, described there as "highest priority of all". */
async function recoveryEscalationNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('capacity_checkins')
    .select('notes, trigger_note, captured_at')
    .order('captured_at', { ascending: false })
    .limit(1);
  const row = data?.[0] as { notes: string | null; trigger_note: string | null; captured_at: string } | undefined;
  if (!row) return null;
  const escalation = scanEscalation(row.notes) ?? scanEscalation(row.trigger_note);
  if (!escalation) return null;
  return { domain: 'Recovery escalation', text: escalation, evidenceAt: row.captured_at };
}

/** Average pain_score over the last 5 capacity_checkins, thresholds 8/6 -
 * the exact same disclosed thresholds alerts.ts's own pain-trend check
 * already uses (lib/alerts.ts wellnessAlerts(), "MSN-0335: folded in from
 * the now-retired duplicate check in /api/proactive-signals"). Not a new
 * scale. Realigned 2026-08-22: recovery_pulses -> capacity_checkins. */
const PAIN_CRITICAL_THRESHOLD = 8;
const PAIN_ELEVATED_THRESHOLD = 6;

async function painTrendNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('capacity_checkins')
    .select('pain_score, captured_at')
    .eq('checkin_type', 'capacity')
    .order('captured_at', { ascending: false })
    .limit(5);
  const rows = (data ?? []) as { pain_score: number | null; captured_at: string }[];
  if (rows.length === 0) return null;
  const avg = rows.reduce((sum, r) => sum + (r.pain_score ?? 0), 0) / rows.length;
  if (avg <= PAIN_ELEVATED_THRESHOLD) return null;
  const level = avg > PAIN_CRITICAL_THRESHOLD ? 'critically high' : 'elevated';
  return {
    domain: 'Recovery pain trend',
    text: `Average pain score over the last ${rows.length} check-ins is ${avg.toFixed(1)} - ${level}.`,
    evidenceAt: rows[0].captured_at,
  };
}

/** mission_delivery is the same real view lib/delivery.ts already reads for
 * the EDO delivery dashboard (migration 0023). 'blocked' fires immediately,
 * no age threshold - the same zero-day rule delivery.ts's own
 * detectBottlenecks() already applies to the blocked state. Mirrors
 * alerts.ts's delivery-blocked-* condition; picks the single
 * longest-blocked row rather than alerts.ts's "up to 4" list, matching
 * missionNominator's own reduction of a multi-row source to one nominee. */
async function deliveryBlockedNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('mission_delivery')
    .select('title, delivery_state, age_days')
    .eq('delivery_state', 'blocked')
    .order('age_days', { ascending: false })
    .limit(1);
  const row = data?.[0] as { title: string; age_days: number | null } | undefined;
  if (!row) return null;
  return {
    domain: 'Delivery',
    text: `"${row.title}" is blocked${row.age_days != null ? ` (${row.age_days}d)` : ''} - work cannot progress until cleared.`,
    evidenceAt: new Date().toISOString(),
  };
}

/** mission_execution_events is the same real table alerts.ts already counts
 * failed dispatches from, over the same disclosed 3-day window (lib/
 * alerts.ts engineeringAlerts()). Not a new window. */
const FAILED_DISPATCH_WINDOW_DAYS = 3;

async function failedDispatchNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const since = new Date(Date.now() - FAILED_DISPATCH_WINDOW_DAYS * 86_400_000).toISOString();
  const { count } = await supabase
    .from('mission_execution_events')
    .select('*', { count: 'exact', head: true })
    .eq('status', 'failed')
    .gte('created_at', since);
  if (!count || count <= 0) return null;
  return {
    domain: 'Delivery dispatch',
    text: `${count} mission dispatch${count > 1 ? 'es' : ''} failed in the last ${FAILED_DISPATCH_WINDOW_DAYS} days.`,
    evidenceAt: new Date().toISOString(),
  };
}

/** mission_delivery is the same view deliveryBlockedNominator above reads.
 * priority_norm P0/P1 + delivery_state='in_review' mirrors alerts.ts's
 * eng-review-* condition exactly (lib/alerts.ts engineeringAlerts(),
 * `/p0|p1/.test(priority_norm.toLowerCase())`). Deliberately NOT the
 * build_request_inbox half of that same alerts.ts function - see the
 * reconciliation note above this section for why that half is already
 * covered by Decide's own engineering count and would be duplicate truth
 * here. */
async function engineeringReviewNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { data } = await supabase
    .from('mission_delivery')
    .select('title, delivery_state, priority_norm, pr_url')
    .eq('delivery_state', 'in_review')
    .order('title', { ascending: true })
    .limit(50);
  const rows = (data ?? []) as { title: string; priority_norm: string | null; pr_url: string | null }[];
  const row = rows.find((r) => /p0|p1/.test((r.priority_norm ?? '').toLowerCase()));
  if (!row) return null;
  return {
    domain: 'Engineering review',
    text: `${(row.priority_norm ?? '').toUpperCase()} item "${row.title}" is awaiting review${(row.pr_url ?? '').trim() ? '' : ' (no PR/evidence)'}.`,
    evidenceAt: new Date().toISOString(),
  };
}

/** captured_items is the real "Quick Capture" table (EOS Canonical
 * Architecture Decisions §3). Mirrors lib/alerts.ts's decisionAlerts()
 * exactly - same two-field filter (classification='mission',
 * review_status='unreviewed'), same count-only query - the captains-chair
 * companion of this nominator, not a re-derived threshold. evidenceAt is
 * the evaluation time, same rationale as failedDispatchNominator above: the
 * count of unreviewed captured missions is a continuously-true-until-it-
 * changes fact, not a point-in-time event. See the reconciliation note
 * above this section for why this is a new nominator rather than a widened
 * Decide query. */
async function capturedMissionNominator(supabase: SupabaseClient): Promise<Interrupt | null> {
  const { count } = await supabase
    .from('captured_items')
    .select('*', { count: 'exact', head: true })
    .eq('classification', 'mission')
    .eq('review_status', 'unreviewed');
  if (!count || count <= 0) return null;
  return {
    domain: 'Captured missions',
    text: `${count} captured mission${count > 1 ? 's' : ''} awaiting triage - flagged as missions but not yet routed into the pipeline.`,
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
  recoveryEscalationNominator,
  recoveryPostureNominator,
  painTrendNominator,
  deliveryBlockedNominator,
  failedDispatchNominator,
  engineeringReviewNominator,
  capturedMissionNominator,
];
export const DOMAIN_NAMES = [
  'Health',
  'Operational intelligence',
  'Intelligence briefs',
  'Missions',
  'Recovery escalation',
  'Recovery posture',
  'Recovery pain trend',
  'Delivery',
  'Delivery dispatch',
  'Engineering review',
  'Captured missions',
];

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
