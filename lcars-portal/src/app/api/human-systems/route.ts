// Human Systems Workbench — unified API (Recovery / Medical / Readiness).
// Domain-aware: ?domain=recovery (default) | medical | readiness.
//
// This route does NOT invent a data model. It reads the sources that are
// already live in the platform, so the workbench shows the same figures the
// scattered (app) health pages show:
//
//   Recovery  — get_recovery_posture(date) RPC (the ROS-001 Posture Engine,
//               migration 0018, retained for its legacy `posture` field only
//               — System Posture, spec §6, is now the primary indicator,
//               deterministic from capacity_checkins, see
//               deriveSystemPosture()) + capacity_checkins /
//               capacity_checkins_today (the current Telegram-fed "MY
//               CAPACITY TODAY" signal, 2026-08-21 — recovery_pulses /
//               recovery_confidence_today are retired, the bot no longer
//               writes to them) + health_insights + capacity_intervention_
//               events/capacity_interventions (My Next Move, spec §10).
//   Medical   — analytics_health_daily (Life Participation + 30d trends),
//               human_systems_daily (four Capacity Domains) + a derived
//               fifth Sensory domain, Recovery Conditions (spec §16,
//               replaces Recovery Indexes) derived from the same daily
//               row plus capacity_checkins, Capacity Debt (evening
//               reflections), Recovery Duration (deep-check field),
//               intervention effectiveness ("What Helps Me", spec §18),
//               and auto-detected redesign candidates (spec §23).
//   Readiness — physical_workout_sessions (last session + 7d completed count)
//               and physical_readiness_checkins.
//
// The Life Participation and Recovery-Conditions derivations mirror the
// canonical logic in src/lib/ros-data.ts / the compute_life_participation
// SQL function so the workbench and the Medical Bay never disagree.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import type {
  Band,
  CapacityBalance,
  CapacityDebt,
  CapacityLoad,
  InterventionEffectiveness,
  Kpis,
  NextMove,
  Payload,
  PostureBand,
  RecoveryDurationSummary,
  RecoveryIndex,
  RedesignCandidate,
  SystemPostureBand,
  TrendRow,
} from '@/app/human-systems-workbench/_components/types';

function today(): string {
  return new Date().toISOString().slice(0, 10);
}
function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function capacityToBand(b: string | null | undefined): Band {
  switch ((b ?? '').toUpperCase()) {
    case 'GOOD': return 'good';
    case 'MODERATE': return 'moderate';
    case 'LIMITED': return 'limited';
    case 'REST': return 'rest';
    default: return 'unknown';
  }
}

function deriveBestWindow(capacity_band: string | null | undefined): string {
  switch ((capacity_band ?? '').toUpperCase()) {
    case 'GOOD': return '09:00–13:00';
    case 'MODERATE': return '09:00–12:30';
    case 'LIMITED': return '09:00–11:00';
    case 'REST': return 'Rest priority — minimal window';
    default: return 'No data';
  }
}

/**
 * Resolve a capacity check-in's nervous-system state — the same mapping as
 * the canonical `checkinNsState()` in lib/human-systems.ts, re-declared here
 * because that module pulls in supabase-browser.ts, a 'use client' file,
 * which this server Route Handler shouldn't depend on (same constraint
 * api/wellness/route.ts already documents and works around). Every consumer
 * of capacity_checkins data in this codebase must apply this same mapping or
 * they'll disagree on a given check-in's nervous-system reading.
 */
function checkinNsState(checkin: { regulation_state?: string | null } | null | undefined): string | null {
  const regulation = checkin?.regulation_state ?? null;
  if (!regulation) return null;
  return ({
    settled: 'calm',
    manageable: 'calm',
    activated: 'activated',
    overloaded: 'dysregulated',
  } as Record<string, string>)[regulation] ?? null;
}

/**
 * Energy proxy derived from capacity_state — the new "MY CAPACITY TODAY"
 * model has no direct energy measure, so green/orange/red is the closest
 * analogue (same reasoning as api/wellness/route.ts's capacityEnergy() and
 * lib/human-systems.ts's capacityStateToEnergy()). Title Case to match this
 * file's own analytics_health_daily `energy` comparisons in
 * computeRecoveryIndexes() ('High'/'Moderate'/'Low').
 */
function energyFromCapacityState(state: string | null | undefined): string | null {
  return ({ green: 'High', orange: 'Moderate', red: 'Low' } as Record<string, string>)[state ?? ''] ?? null;
}

/**
 * Capacity band/detail from a capacity_checkins.capacity_state reading —
 * same green/orange/red → good/moderate/limited mapping
 * compute_recovery_score() (migration 0150) uses for its capacity subscore.
 */
function capacityStateBand(state: string | null | undefined): Band | null {
  return ({ green: 'good', orange: 'moderate', red: 'limited' } as Record<string, Band>)[state ?? ''] ?? null;
}
function capacityStateDetail(state: string | null | undefined): string | null {
  return ({
    green: 'Green — full operational window (capacity check-in)',
    orange: 'Orange — moderate operational window (capacity check-in)',
    red: 'Red — minimal operational window (capacity check-in)',
  } as Record<string, string>)[state ?? ''] ?? null;
}

// ── VNext consolidation (WP02-04) — System Posture, Capacity Balance, Next Move ──
// Deterministic, no LLM (spec §35) — same discipline as the Capacity Bot's
// own intervention_engine.py. Rules mirror spec §36/§37 exactly; illustrative
// per the doc, tuned here against the same field vocabulary the bot writes.

function deriveSystemPosture(c: CheckinRow | null): { posture: SystemPostureBand; message: string } {
  if (!c || !c.capacity_state) {
    return { posture: 'UNKNOWN', message: 'No capacity check-in recorded for today yet.' };
  }
  const cap = c.capacity_state; // green | orange | red
  const reg = c.regulation_state; // settled | manageable | activated | overloaded
  const ef = c.executive_function; // good | strained | difficult | very_difficult
  const comp = c.compensation_load; // low | moderate | high | extreme
  const stim = c.stimulation_state; // low | balanced | high
  const painElevated = c.pain_state === 'elevated' || c.pain_state === 'high';
  const highPain = c.pain_state === 'high';

  if (cap === 'red' || (reg === 'overloaded' && ef === 'very_difficult') || (highPain && cap === 'red')) {
    return { posture: 'RECOVER', message: 'Capacity is depleted or recovery debt is high. Recovery is the primary objective.' };
  }
  // RESET: stimulation significantly mismatched AND dysregulated — a short
  // regulation intervention before deciding the rest of the day.
  if ((stim === 'low' || stim === 'high') && (reg === 'overloaded' || reg === 'activated') && cap !== 'green') {
    return { posture: 'RESET', message: 'The system appears mismatched or dysregulated — a short regulation step before deciding what comes next.' };
  }
  if (cap === 'orange' || comp === 'high' || comp === 'extreme' || reg === 'activated' || (painElevated && cap !== 'green')) {
    return { posture: 'PROTECT', message: 'Capacity is stretched. Reduce unnecessary demand and intervene early.' };
  }
  if (cap === 'green' && (stim === 'balanced' || !stim) && !painElevated && comp !== 'high' && comp !== 'extreme') {
    return { posture: 'ENGAGE', message: 'Capacity is available and the system can tolerate meaningful demand.' };
  }
  if (cap === 'green') {
    return { posture: 'STEADY', message: 'Maintain current pace. Avoid unnecessary load increases.' };
  }
  return { posture: 'STEADY', message: 'Maintain current pace. Avoid unnecessary load increases.' };
}

function deriveCapacityBalance(c: CheckinRow | null): CapacityBalance {
  if (!c || !c.capacity_state) return 'unknown';
  // "Too much" and "not enough" are about stimulation direction relative to
  // capacity, not capacity alone (spec §11 — regulation may mean reducing
  // OR adding input).
  if (c.stimulation_state === 'high' || c.capacity_state === 'red') return 'too_much';
  if (c.stimulation_state === 'low' && c.capacity_state !== 'red') return 'not_enough';
  if (c.capacity_state === 'green' && (c.stimulation_state === 'balanced' || !c.stimulation_state)) return 'sustainable';
  if (c.capacity_state === 'orange') return 'too_much';
  return 'sustainable';
}

function rankCapacityLoads(rows: Pick<CheckinRow, 'active_loads'>[]): CapacityLoad[] {
  const counts = new Map<string, number>();
  for (const r of rows) {
    for (const load of r.active_loads ?? []) {
      counts.set(load, (counts.get(load) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count);
}

function buildNextMove(
  event: InterventionEventRow | null,
  intervention: InterventionRow | null,
  fallbackSelectedAction: string | null,
): NextMove {
  if (event && intervention) {
    return {
      lever: intervention.management_lever,
      intervention_title: intervention.title,
      intervention_description: intervention.full_description,
      event_id: event.id,
      event_source: event.source,
      accepted_at: event.started_at,
      outcome: event.outcome,
    };
  }
  // No intervention_events row yet (bot's WP04-06 just shipped, or the
  // Captain hasn't accepted a suggestion today) — fall back to the older
  // capacity_checkins.selected_action text the Q9 flow has always written,
  // so "My Next Move" isn't empty on day one of this integration.
  if (fallbackSelectedAction) {
    return {
      lever: null,
      intervention_title: fallbackSelectedAction,
      intervention_description: null,
      event_id: null,
      event_source: null,
      accepted_at: null,
      outcome: null,
    };
  }
  return {
    lever: null,
    intervention_title: null,
    intervention_description: null,
    event_id: null,
    event_source: null,
    accepted_at: null,
    outcome: null,
  };
}

/**
 * health_insights.llm_narrative (migration 0008) is JSONB — legacy rows
 * store a plain string, the documented/current shape is a structured object
 * {situation, patterns_noticed, what_it_means, recommended_focus,
 * watch_items}. RecoveryView.tsx renders `wellness.narrative` directly as
 * JSX text (typed `string | null`) — an object row hits React error #31.
 * Normalize at the API boundary so the client stays safe either way.
 */
function narrativeText(raw: unknown): string | null {
  if (!raw) return null;
  if (typeof raw === 'string') return raw;
  if (typeof raw === 'object') {
    const o = raw as Record<string, unknown>;
    const parts = [o.situation, o.what_it_means, o.recommended_focus].filter(
      (v): v is string => typeof v === 'string' && v.trim().length > 0,
    );
    return parts.length ? parts.join(' ') : null;
  }
  return null;
}

interface RawPostureRow {
  posture: string;
  posture_message: string;
  capacity_band: string;
  capacity_message: string;
  mission_guidance: string;
  score: number | null;
  data_available: boolean;
}

interface DailyRow {
  sleep_hours: number | null;
  sleep_quality: string | null;
  cpap_status: string | null;
  nervous_system_state: string | null;
  energy: string | null;
  pain_score: number | null;
  movement_notes: string | null;
  pleasure_creativity_marker: string | null;
  what_happened: string | null;
  sitting_tolerance_minutes: number | null;
  workload_constraint: string | null;
  captain_capacity_rating: string | null;
}

interface CheckinRow {
  captured_at: string;
  capacity_state: string | null;
  regulation_state: string | null;
  pain_score: number | null;
  executive_function: string | null;
  // VNext consolidation additions (WP02-03) — already written by the
  // Capacity Bot since its V01 launch, never previously read here.
  stimulation_state: string | null;
  pain_state: string | null;
  compensation_load: string | null;
  active_loads: string[] | null;
  identified_needs: string[] | null;
  selected_action: string | null;
}

interface InterventionEventRow {
  id: number;
  source: 'capacity_q9' | 'helpme' | 'guide' | 'manual';
  intervention_id: string;
  started_at: string;
  outcome: 'better' | 'same' | 'worse' | 'not_completed' | 'unknown' | null;
}

interface InterventionRow {
  intervention_id: string;
  title: string;
  full_description: string | null;
  management_lever: 'reduce_load' | 'regulate' | 'recover' | 'redesign';
}

interface CheckinsTodayRow {
  assessment_date: string;
  checkins_today: number;
  has_checked_in: boolean;
  checkin_label: string;
  last_checkin_at: string | null;
  latest_capacity_state: string | null;
  latest_regulation_state: string | null;
  latest_pain_score: number | null;
  latest_executive_function: string | null;
}

// ── Life Participation (mirror of compute_life_participation / fetchLifeParticipation) ──

function computeLifeParticipation(d: DailyRow | null): { score: number | null; band: Band; components: {
  movement: boolean; pleasure: string | null; social: boolean; sitting_minutes: number; sitting_baseline: number; workload: string;
} } {
  const sitting_baseline = 120;
  if (!d) {
    return { score: null, band: 'unknown', components: { movement: false, pleasure: null, social: false, sitting_minutes: 0, sitting_baseline, workload: 'unknown' } };
  }
  const movement = !!(d.movement_notes?.trim());
  const pleasure = d.pleasure_creativity_marker?.trim() || null;
  const social = !!(d.what_happened?.trim());
  const sitting_minutes = d.sitting_tolerance_minutes ?? 0;
  const workload = (d.workload_constraint ?? 'unknown').toLowerCase();

  const vMovement = movement ? 100 : 0;
  const vPleasure = pleasure ? 100 : 0;
  const vSocial = social ? 50 : 25;
  const vSitting = Math.min((sitting_minutes / sitting_baseline) * 100, 100);
  const vWorkload = workload === 'none' ? 100 : workload === 'light' ? 70 : workload === 'moderate' ? 40 : workload === 'severe' ? 10 : 50;

  const score = Math.round(vMovement * 0.25 + vPleasure * 0.2 + vSocial * 0.2 + vSitting * 0.2 + vWorkload * 0.15);
  const band: Band = score >= 75 ? 'good' : score >= 55 ? 'moderate' : score >= 35 ? 'limited' : 'rest';
  return { score, band, components: { movement, pleasure, social, sitting_minutes, sitting_baseline, workload } };
}

// ── Recovery indexes (mirror of fetchRecoveryIndexes) ────────────────────────
//
// Nervous System, Energy, and Capacity now prefer a live capacity_checkins
// reading over the (likely-frozen, post manual-capture-retirement)
// analytics_health_daily row — same blend priority buildRecovery() and
// compute_recovery_score() (migration 0150) already use. Sleep has no
// capacity_checkins equivalent (spec doesn't track it) and stays sourced
// from analytics_health_daily alone — this index will not update once that
// table stops receiving new manual check-in rows.
/**
 * Recovery CONDITIONS (spec §16, replaces "Recovery Indexes") — the
 * inputs that influence replenishment, not the outcome (Capacity) they
 * produce. Sleep and Nervous System carry over unchanged; Energy and
 * Capacity are dropped per spec ("do not re-display Capacity here —
 * Capacity is the outcome these conditions influence"); Pain Burden,
 * Sensory Load, and Recovery Time are new.
 */
function computeRecoveryConditions(
  d: DailyRow | null,
  blended: BlendedSignals,
  latestCheckin: CheckinRow | null,
  recoveryDuration: RecoveryDurationSummary,
): RecoveryIndex[] {
  const sleepHrs = d?.sleep_hours ?? 0;
  const sleepBand: Band = !d?.sleep_hours ? 'unknown' : sleepHrs >= 7 ? 'good' : sleepHrs >= 5.5 ? 'moderate' : 'limited';
  const cpapNote = d?.cpap_status?.toLowerCase() === 'yes' ? ' · CPAP compliant' : '';

  const ns = blended.nervous_system;
  const nsBand: Band = ns === 'calm' ? 'good' : ns === 'activated' ? 'moderate' : ns === 'dysregulated' ? 'limited' : 'unknown';
  const nsDetail = ns === 'calm' ? 'Calm — settled baseline' : ns === 'activated' ? 'Activated — protect capacity' : ns === 'dysregulated' ? 'Dysregulated — rest priority' : 'Not recorded';

  const painState = latestCheckin?.pain_state ?? null;
  const painBand: Band = painState === 'low' ? 'good' : painState === 'baseline' ? 'good' :
    painState === 'elevated' ? 'moderate' : painState === 'high' ? 'limited' : 'unknown';
  const painDetail = painState
    ? `${{ low: 'Lower than usual', baseline: 'Around baseline', elevated: 'Higher than usual', high: 'Much higher than usual' }[painState] ?? painState}${latestCheckin?.pain_score != null ? ` (${latestCheckin.pain_score}/10)` : ''}`
    : 'Not recorded';

  const stim = latestCheckin?.stimulation_state ?? null;
  const sensoryBand: Band = stim === 'balanced' ? 'good' : (stim === 'low' || stim === 'high') ? 'moderate' : 'unknown';
  const sensoryDetail = stim === 'balanced' ? 'Balanced' : stim === 'low' ? 'Not enough — understimulated' : stim === 'high' ? 'Too much — overstimulated' : 'Not recorded';

  const rdBand: Band = !recoveryDuration.most_common ? 'unknown' :
    recoveryDuration.most_common === 'No recovery needed' || recoveryDuration.most_common === 'Under 30 minutes' ? 'good' :
    recoveryDuration.most_common === '1-2 hours' ? 'moderate' :
    recoveryDuration.most_common === 'Half a day' ? 'limited' : 'rest';
  const rdDetail = recoveryDuration.sample_size < 3
    ? 'Not enough deep-check records yet'
    : `${recoveryDuration.most_common} most common (${recoveryDuration.most_common_count}/${recoveryDuration.sample_size} records)`;

  return [
    { key: 'sleep', label: 'Sleep', band: sleepBand, detail: d?.sleep_hours ? `${sleepHrs}h · ${d.sleep_quality ?? 'Unknown quality'}${cpapNote}` : 'Not recorded (no capacity-checkin equivalent)' },
    { key: 'nervous_system', label: 'Nervous-system regulation', band: nsBand, detail: nsDetail },
    { key: 'pain_burden', label: 'Pain burden', band: painBand, detail: painDetail },
    { key: 'sensory_load', label: 'Sensory load', band: sensoryBand, detail: sensoryDetail },
    { key: 'recovery_time', label: 'Recovery time', band: rdBand, detail: rdDetail },
  ];
}

/** Sensory — the 5th Capacity Domain (spec §15: "too important to hide
 *  inside other domains"). No dedicated source table exists yet, so this
 *  is derived from today's latest stimulation_state + whether a
 *  sensory-tagged load was actively selected — same honest-proxy pattern
 *  energyFromCapacityState() already uses for Energy. */
function deriveSensoryBand(c: CheckinRow | null): { band: Band; value: string | null } {
  if (!c || !c.stimulation_state) return { band: 'unknown', value: null };
  const sensoryLoadActive = (c.active_loads ?? []).some((l) => l.includes('sensory') || l.includes('stimulation'));
  if (c.stimulation_state === 'balanced' && !sensoryLoadActive) return { band: 'good', value: 'balanced' };
  if (sensoryLoadActive && c.stimulation_state !== 'balanced') return { band: 'limited', value: c.stimulation_state };
  return { band: 'moderate', value: c.stimulation_state };
}

/** Capacity debt (spec §19) — from evening reflections' capacity_debt
 *  field ('no'|'maybe'|'yes'). 'maybe' counts as debt, matching the
 *  bot's own render_trend_summary()'s yes_maybe grouping. */
async function computeCapacityDebt(sb: any, windowDays: number): Promise<CapacityDebt> {
  const { data } = await sb
    .from('capacity_checkins')
    .select('capacity_debt')
    .eq('checkin_type', 'evening')
    .gte('log_date', daysAgo(windowDays - 1))
    .lte('log_date', today());
  const rows = (data ?? []) as { capacity_debt: string | null }[];
  const days_with_debt = rows.filter((r) => r.capacity_debt === 'yes' || r.capacity_debt === 'maybe').length;
  return { days_with_debt, days_total: rows.length, window_days: windowDays };
}

const RECOVERY_DURATION_LABEL: Record<string, string> = {
  n: 'No recovery needed', '30': 'Under 30 minutes', '2h': '1-2 hours', hd: 'Half a day', fd: 'Full day', md: 'Multiple days',
  'No recovery needed': 'No recovery needed', 'Under 30 minutes': 'Under 30 minutes', '1-2 hours': '1-2 hours',
  'Half a day': 'Half a day', 'Full day': 'Full day', 'Multiple days': 'Multiple days',
};

/** Recovery duration summary (spec §20) — most common value from deep-check
 *  capacity_checkins.recovery_duration over the window. Spec: "only
 *  produce summary when enough records exist" — sample_size lets the
 *  caller decide the cutoff (this route doesn't hide the raw count). */
async function computeRecoveryDuration(sb: any, windowDays: number): Promise<RecoveryDurationSummary> {
  const { data } = await sb
    .from('capacity_checkins')
    .select('recovery_duration')
    .eq('checkin_type', 'capacity')
    .not('recovery_duration', 'is', null)
    .gte('log_date', daysAgo(windowDays - 1))
    .lte('log_date', today());
  const rows = (data ?? []) as { recovery_duration: string }[];
  if (rows.length === 0) return { most_common: null, most_common_count: 0, sample_size: 0 };
  const counts = new Map<string, number>();
  for (const r of rows) {
    const label = RECOVERY_DURATION_LABEL[r.recovery_duration] ?? r.recovery_duration;
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const [most_common, most_common_count] = Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0];
  return { most_common, most_common_count, sample_size: rows.length };
}

const MIN_SAMPLE_FOR_EFFECTIVENESS = 3; // mirrors the bot's intervention_engine.py MIN_SAMPLE_FOR_WEIGHTING

/** What Helps Me (spec §18) — TypeScript mirror of the Capacity Bot's
 *  personal_effectiveness_summary() (intervention_engine.py). All-time,
 *  same as the bot (no window filter) — counts accumulate meaning over
 *  time, and this is exactly the same query the bot's /actions and this
 *  workbench should never disagree on. */
async function computeInterventionEffectiveness(sb: any): Promise<InterventionEffectiveness[]> {
  const [{ data: events }, { data: catalogueRows }] = await Promise.all([
    sb.from('capacity_intervention_events').select('intervention_id,outcome,help_state'),
    sb.from('capacity_interventions').select('intervention_id,title'),
  ]);
  const catalogue = new Map<string, string>((catalogueRows ?? []).map((r: any) => [r.intervention_id, r.title]));
  const byId = new Map<string, { outcome: string | null; help_state: string | null }[]>();
  for (const e of (events ?? []) as any[]) {
    const arr = byId.get(e.intervention_id) ?? [];
    arr.push({ outcome: e.outcome, help_state: e.help_state });
    byId.set(e.intervention_id, arr);
  }
  const out: InterventionEffectiveness[] = [];
  for (const [intervention_id, rows] of byId) {
    const attempts = rows.length;
    const better = rows.filter((r) => r.outcome === 'better').length;
    const same = rows.filter((r) => r.outcome === 'same').length;
    const worse = rows.filter((r) => r.outcome === 'worse').length;
    const not_completed = rows.filter((r) => !r.outcome || r.outcome === 'not_completed').length;
    const stateCounts = new Map<string, number>();
    for (const r of rows) if (r.help_state) stateCounts.set(r.help_state, (stateCounts.get(r.help_state) ?? 0) + 1);
    const common_context = stateCounts.size
      ? Array.from(stateCounts.entries()).sort((a, b) => b[1] - a[1])[0][0].replace(/_/g, ' ')
      : null;
    out.push({
      intervention_id, title: catalogue.get(intervention_id) ?? intervention_id, attempts, better, same, worse, not_completed,
      meets_sample_threshold: attempts >= MIN_SAMPLE_FOR_EFFECTIVENESS, common_context,
    });
  }
  return out.sort((a, b) => b.attempts - a.attempts);
}

/** Redesign candidates (spec §23) — loads that recur often enough on
 *  stretched/depleted days over the last 30 days to be worth changing
 *  rather than repeatedly regulating around. Read-only auto-detection
 *  only, no manual-entry form (deferred — spec frames V02 as "capture as
 *  they become obvious", not a full redesign-log CRUD surface). Threshold
 *  of 3 is a starting point, same conservatism as the bot's own
 *  MIN_SAMPLE_FOR_WEIGHTING — a load seen once or twice isn't "recurring".
 */
async function computeRedesignCandidates(sb: any, windowDays: number, threshold = 3): Promise<RedesignCandidate[]> {
  const { data } = await sb
    .from('capacity_checkins')
    .select('active_loads')
    .eq('checkin_type', 'capacity')
    .in('capacity_state', ['orange', 'red'])
    .gte('log_date', daysAgo(windowDays - 1))
    .lte('log_date', today());
  const counts = new Map<string, number>();
  for (const r of (data ?? []) as { active_loads: string[] | null }[]) {
    for (const load of r.active_loads ?? []) counts.set(load, (counts.get(load) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .filter(([, count]) => count >= threshold)
    .map(([load, count]) => ({ load, stretched_or_depleted_count: count, window_days: windowDays }))
    .sort((a, b) => b.stretched_or_depleted_count - a.stretched_or_depleted_count);
}

// ── Shared fetch: today's context reused across KPIs + every domain ──────────

interface Ctx {
  posture: RawPostureRow | null;
  daily: DailyRow | null;
  latestCheckin: CheckinRow | null;
  checkinsToday: CheckinsTodayRow | null;
  sessions7d: number;
  /** Every capacity check-in logged today (not just the latest) — needed
   *  for WP03's "today's capacity load" ranking across all of today's
   *  active_loads selections, not just the most recent one. */
  checkinsTodayRows: Pick<CheckinRow, 'active_loads'>[];
  /** Most recent capacity_intervention_events row across ALL sources
   *  (capacity_q9/helpme/guide/manual) — WP04's "My Next Move" (spec §10)
   *  shows whatever was actually last accepted, not a re-ranked
   *  suggestion, so the workbench never disagrees with what the bot just
   *  offered. */
  latestInterventionEvent: InterventionEventRow | null;
  latestInterventionCatalogue: InterventionRow | null;
}

async function loadCtx(sb: any): Promise<Ctx> {
  const t = today();
  const sevenDaysAgo = new Date(Date.now() - 7 * 86_400_000).toISOString();
  const CHECKIN_FIELDS =
    'captured_at,capacity_state,regulation_state,pain_score,executive_function,stimulation_state,pain_state,compensation_load,active_loads,identified_needs,selected_action';

  const [postureRes, dailyRes, checkinRes, checkinsTodayRes, sessionCountRes, checkinsTodayRowsRes, eventRes] =
    await Promise.all([
      sb.rpc('get_recovery_posture', { p_date: t }).single(),
      sb.from('analytics_health_daily')
        .select('sleep_hours,sleep_quality,cpap_status,nervous_system_state,energy,pain_score,movement_notes,pleasure_creativity_marker,what_happened,sitting_tolerance_minutes,workload_constraint,captain_capacity_rating')
        .eq('log_date', t).maybeSingle(),
      sb.from('capacity_checkins')
        // capacity_state/regulation_state/executive_function are the canonical
        // Telegram-bot "MY CAPACITY TODAY" fields (recovery_pulses is
        // retired, 2026-08-21). Quick check-ins only — checkin_type also
        // covers 'evening' rows, which this route doesn't merge in here.
        .select(CHECKIN_FIELDS)
        .eq('checkin_type', 'capacity')
        .eq('log_date', t).order('captured_at', { ascending: false }).limit(1).maybeSingle(),
      sb.from('capacity_checkins_today').select('*').maybeSingle(),
      sb.from('physical_workout_sessions')
        .select('id', { count: 'exact', head: true })
        .eq('status', 'completed').gte('started_at', sevenDaysAgo),
      sb.from('capacity_checkins')
        .select('active_loads')
        .eq('checkin_type', 'capacity')
        .eq('log_date', t),
      sb.from('capacity_intervention_events')
        .select('id,source,intervention_id,started_at,outcome')
        .order('started_at', { ascending: false })
        .limit(1).maybeSingle(),
    ]);

  let latestInterventionCatalogue: InterventionRow | null = null;
  const event = (eventRes.data as InterventionEventRow) ?? null;
  if (event) {
    const { data: interventionRow } = await sb
      .from('capacity_interventions')
      .select('intervention_id,title,full_description,management_lever')
      .eq('intervention_id', event.intervention_id)
      .maybeSingle();
    latestInterventionCatalogue = (interventionRow as InterventionRow) ?? null;
  }

  return {
    posture: (postureRes.data as RawPostureRow) ?? null,
    daily: (dailyRes.data as DailyRow) ?? null,
    latestCheckin: (checkinRes.data as CheckinRow) ?? null,
    checkinsToday: (checkinsTodayRes.data as CheckinsTodayRow) ?? null,
    sessions7d: sessionCountRes.count ?? 0,
    checkinsTodayRows: (checkinsTodayRowsRes.data as Pick<CheckinRow, 'active_loads'>[]) ?? [],
    latestInterventionEvent: event,
    latestInterventionCatalogue,
  };
}

interface BlendedSignals {
  energy: string | null;
  nervous_system: string | null;
  capacityState: string | null;
}

/**
 * Energy / nervous-system / capacity, blended capacity_checkins-first —
 * shared by buildRecovery() and buildMedical() (previously buildRecovery
 * alone had this fallback chain; buildMedical's Recovery Indexes card
 * still read analytics_health_daily exclusively, so it went stale the
 * moment health_daily_logs stopped receiving new manual check-in rows).
 */
function deriveBlendedSignals(ctx: Ctx): BlendedSignals {
  const c = ctx.checkinsToday;
  const capacityState = ctx.latestCheckin?.capacity_state ?? c?.latest_capacity_state ?? null;
  return {
    energy:
      ctx.daily?.energy ??
      energyFromCapacityState(ctx.latestCheckin?.capacity_state) ??
      energyFromCapacityState(c?.latest_capacity_state) ??
      null,
    nervous_system:
      ctx.daily?.nervous_system_state ??
      checkinNsState(ctx.latestCheckin) ??
      checkinNsState({ regulation_state: c?.latest_regulation_state ?? null }) ??
      null,
    capacityState,
  };
}

function buildKpis(ctx: Ctx, lp: { score: number | null; band: Band }): Kpis {
  return {
    posture: ((ctx.posture?.posture as PostureBand) ?? 'UNKNOWN'),
    lp_score: lp.score,
    lp_band: lp.band,
    sessions_7d: ctx.sessions7d,
    capacity_band: capacityToBand(ctx.posture?.capacity_band),
    sleep_hours: ctx.daily?.sleep_hours ?? null,
    checkins_today: ctx.checkinsToday?.checkins_today ?? 0,
    latest_capacity_state: ctx.checkinsToday?.latest_capacity_state ?? null,
    system_posture: deriveSystemPosture(ctx.latestCheckin).posture,
  };
}

// ── Domain builders ──────────────────────────────────────────────────────────

async function buildRecovery(sb: any, ctx: Ctx, kpis: Kpis): Promise<Payload> {
  const p = ctx.posture;
  const c = ctx.checkinsToday;
  const { energy, nervous_system } = deriveBlendedSignals(ctx);

  // health_insights has no `insight_date` column (the existing /api/wellness
  // route selects one that doesn't exist and silently gets nothing) — the real
  // recency column is created_at. risk_flags / positive_flags / wins_this_week /
  // llm_narrative are genuine columns (verified against the live schema).
  const { data: insightRows } = await sb
    .from('health_insights')
    .select('created_at,llm_narrative,risk_flags,positive_flags,wins_this_week')
    .order('created_at', { ascending: false })
    .limit(1);
  const ins = insightRows?.[0] ?? null;
  const { posture: system_posture, message: system_posture_message } = deriveSystemPosture(ctx.latestCheckin);

  // WP09 System Learning "What I Know" fact (spec §17 example: "8
  // check-ins recorded in the last 7 days").
  const { count: checkins_last_7d } = await sb
    .from('capacity_checkins')
    .select('id', { count: 'exact', head: true })
    .eq('checkin_type', 'capacity')
    .gte('log_date', daysAgo(6));

  return {
    domain: 'recovery',
    kpis,
    posture: (p?.posture as PostureBand) ?? 'UNKNOWN',
    posture_message: p?.posture_message ?? 'No health data recorded for today.',
    capacity_band: capacityToBand(p?.capacity_band),
    capacity_message: p?.capacity_message ?? 'Record a check-in to receive capacity guidance.',
    mission_guidance: p?.mission_guidance ?? 'No capacity data available — proceed with care.',
    best_window: deriveBestWindow(p?.capacity_band),
    sleep_hours: ctx.daily?.sleep_hours ?? null,
    sleep_quality: ctx.daily?.sleep_quality ?? null,
    nervous_system,
    energy,
    checkins_today: c?.checkins_today ?? 0,
    latest_capacity_state: c?.latest_capacity_state ?? null,
    latest_regulation_state: c?.latest_regulation_state ?? null,
    confidence_label: c?.checkin_label ?? 'No telemetry today',
    wellness: {
      narrative: narrativeText(ins?.llm_narrative),
      // Guard: these columns are arrays in the live schema, but coerce
      // defensively so a null / unexpected shape can never crash the view's map.
      risk_flags: Array.isArray(ins?.risk_flags) ? ins!.risk_flags : [],
      positive_flags: Array.isArray(ins?.positive_flags) ? ins!.positive_flags : [],
      wins: Array.isArray(ins?.wins_this_week) ? ins!.wins_this_week : [],
      insight_date: ins?.created_at ?? null,
    },
    data_available: !!p?.data_available,

    // ── VNext consolidation (WP02-04) ────────────────────────────────────
    system_posture,
    system_posture_message,
    stimulation_state: ctx.latestCheckin?.stimulation_state ?? null,
    pain_state: ctx.latestCheckin?.pain_state ?? null,
    pain_score: ctx.latestCheckin?.pain_score ?? null,
    executive_function: ctx.latestCheckin?.executive_function ?? null,
    compensation_load: ctx.latestCheckin?.compensation_load ?? null,
    capacity_balance: deriveCapacityBalance(ctx.latestCheckin),
    active_loads_today: rankCapacityLoads(ctx.checkinsTodayRows),
    identified_needs_latest: ctx.latestCheckin?.identified_needs ?? [],
    next_move: buildNextMove(
      ctx.latestInterventionEvent,
      ctx.latestInterventionCatalogue,
      ctx.latestCheckin?.selected_action ?? null,
    ),
    checkins_last_7d: checkins_last_7d ?? 0,
  };
}

async function buildMedical(sb: any, ctx: Ctx, kpis: Kpis): Promise<Payload> {
  const lp = computeLifeParticipation(ctx.daily);

  // Four energy domains from the human_systems_daily view (today), plus a
  // fifth Sensory domain derived from capacity_checkins (spec §15 — no
  // dedicated source table exists for this yet).
  const { data: hsRow } = await sb
    .from('human_systems_daily')
    .select('energy_physical,energy_cognitive,energy_emotional,energy_social,daily_capacity_score')
    .eq('log_date', today())
    .maybeSingle();

  const domainBand = (v: string | null): Band =>
    v === 'good' ? 'good' : v === 'moderate' ? 'moderate' : v === 'limited' ? 'limited' : v === 'depleted' ? 'rest' : 'unknown';
  const sensory = deriveSensoryBand(ctx.latestCheckin);

  // Cognitive: capacity_checkins.executive_function is a direct, dedicated
  // cognitive-capacity question every /capacity check-in asks ("how easy
  // is it to think, decide, start, switch tasks?") — real signal that was
  // sitting unused while this domain read the dead human_systems_daily
  // source. Same 4-value scale the bot itself uses (capacity_today.py's
  // EF_CODE_TO_STATE), mapped to this workbench's band vocabulary.
  const efBand = (ef: string | null | undefined): Band => ({
    good: 'good', strained: 'moderate', difficult: 'limited', very_difficult: 'rest',
  } as Record<string, Band>)[ef ?? ''] ?? 'unknown';
  const efLabel: Record<string, string> = {
    good: 'Working well', strained: 'More effort than usual', difficult: 'Difficult', very_difficult: 'Very difficult',
  };
  const ef = ctx.latestCheckin?.executive_function ?? null;

  // Physical dropped (Captain directive, 2026-08-22) — human_systems_daily
  // is dead and, unlike Cognitive, capacity_checkins has no dedicated
  // physical-capacity field to substitute (only a weak active_loads tag
  // presence signal), so this domain is removed rather than shown empty
  // or backed by a low-confidence proxy.
  const capacity_domains = [
    { key: 'cognitive', label: 'Cognitive', band: efBand(ef), value: ef ? efLabel[ef] ?? ef : null },
    { key: 'emotional', label: 'Emotional', band: domainBand(hsRow?.energy_emotional ?? null), value: hsRow?.energy_emotional ?? null },
    { key: 'social', label: 'Social', band: domainBand(hsRow?.energy_social ?? null), value: hsRow?.energy_social ?? null },
    { key: 'sensory', label: 'Sensory', band: sensory.band, value: sensory.value },
  ];

  // VNext consolidation (WP07-08) — capacity debt, recovery duration,
  // intervention effectiveness, redesign candidates. Recovery Conditions
  // needs recovery_duration first, so it's computed before the rest.
  const recovery_duration = await computeRecoveryDuration(sb, 30);
  const recovery_indexes = computeRecoveryConditions(ctx.daily, deriveBlendedSignals(ctx), ctx.latestCheckin, recovery_duration);
  const [capacity_debt, intervention_effectiveness, redesign_candidates] = await Promise.all([
    computeCapacityDebt(sb, 7),
    computeInterventionEffectiveness(sb),
    computeRedesignCandidates(sb, 30),
  ]);

  // 30-day trends — backfilled with capacity_checkins so a day with only a
  // Telegram check-in (no analytics_health_daily row at all, or a row with
  // a null energy/pain field) still shows up instead of silently vanishing
  // from the sparklines. Previously this queried analytics_health_daily
  // exclusively, so trends would visibly stop moving the day the manual
  // check-in form (health_daily_logs' only writer) was retired.
  const [{ data: trendRows }, { data: checkinTrendRows }] = await Promise.all([
    sb.from('analytics_health_daily')
      .select('log_date,energy,sleep_quality,nervous_system_state,pain_score')
      .gte('log_date', daysAgo(29))
      .lte('log_date', today())
      .order('log_date', { ascending: true }),
    sb.from('capacity_checkins')
      .select('log_date,captured_at,capacity_state,regulation_state,pain_score')
      .eq('checkin_type', 'capacity')
      .gte('log_date', daysAgo(29))
      .lte('log_date', today())
      .order('captured_at', { ascending: true }),
  ]);

  // Ascending by captured_at, so the last write per log_date wins — same
  // most-recent-reading priority deriveBlendedSignals() uses for today.
  const checkinByDate = new Map<string, { capacity_state: string | null; regulation_state: string | null; pain_score: number | null }>();
  for (const r of (checkinTrendRows ?? []) as any[]) {
    checkinByDate.set(r.log_date, { capacity_state: r.capacity_state, regulation_state: r.regulation_state, pain_score: r.pain_score });
  }

  const trendByDate = new Map<string, TrendRow>();
  for (const r of (trendRows ?? []) as any[]) {
    trendByDate.set(r.log_date, {
      log_date: r.log_date,
      energy: r.energy ?? null,
      sleep_quality: r.sleep_quality ?? null,
      nervous_system_state: r.nervous_system_state ?? null,
      pain_score: r.pain_score ?? null,
    });
  }
  for (const [date, chk] of checkinByDate) {
    const existing = trendByDate.get(date);
    const chkEnergy = energyFromCapacityState(chk.capacity_state);
    const chkNs = checkinNsState({ regulation_state: chk.regulation_state });
    trendByDate.set(date, existing ? {
      ...existing,
      energy: existing.energy ?? chkEnergy,
      nervous_system_state: existing.nervous_system_state ?? chkNs,
      pain_score: existing.pain_score ?? chk.pain_score,
    } : {
      log_date: date,
      energy: chkEnergy,
      sleep_quality: null,
      nervous_system_state: chkNs,
      pain_score: chk.pain_score,
    });
  }
  const trends: TrendRow[] = Array.from(trendByDate.values()).sort((a, b) => a.log_date.localeCompare(b.log_date));

  return {
    domain: 'medical',
    kpis,
    life_participation: { score: lp.score, band: lp.band, components: lp.components },
    capacity_domains,
    recovery_conditions: recovery_indexes,
    trends,
    capacity_debt,
    recovery_duration,
    intervention_effectiveness,
    redesign_candidates,
  };
}

async function buildReadiness(sb: any, ctx: Ctx, kpis: Kpis): Promise<Payload> {
  const [{ data: last }, { data: checkin }] = await Promise.all([
    sb.from('physical_workout_sessions')
      .select('id,session_type,status,started_at,duration_minutes')
      .order('started_at', { ascending: false }).limit(1).maybeSingle(),
    sb.from('physical_readiness_checkins')
      .select('created_at')
      .order('created_at', { ascending: false }).limit(1).maybeSingle(),
  ]);

  return {
    domain: 'readiness',
    kpis,
    last_session: last
      ? { id: last.id, type: last.session_type, status: last.status, date: last.started_at, duration: last.duration_minutes }
      : null,
    weekly_count: ctx.sessions7d,
    last_checkin_at: checkin?.created_at ?? null,
  };
}

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const domain = (req.nextUrl.searchParams.get('domain') ?? 'recovery') as 'recovery' | 'medical' | 'readiness';
  try {
    const sb = await createSupabaseServerClient();
    const ctx = await loadCtx(sb);
    const lp = computeLifeParticipation(ctx.daily);
    const kpis = buildKpis(ctx, lp);

    if (domain === 'medical') return NextResponse.json(await buildMedical(sb, ctx, kpis));
    if (domain === 'readiness') return NextResponse.json(await buildReadiness(sb, ctx, kpis));
    return NextResponse.json(await buildRecovery(sb, ctx, kpis));
  } catch (err) {
    console.error('[human-systems] read failed:', err);
    return NextResponse.json({ error: 'human_systems_read_failed', domain }, { status: 500 });
  }
}
