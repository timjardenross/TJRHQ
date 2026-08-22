// Human Systems Workbench — unified API (Recovery / Medical / Readiness).
// Domain-aware: ?domain=recovery (default) | medical | readiness.
//
// This route does NOT invent a data model. It reads the sources that are
// already live in the platform, so the workbench shows the same figures the
// scattered (app) health pages show:
//
//   Recovery  — get_recovery_posture(date) RPC (the ROS-001 Posture Engine,
//               migration 0018) + capacity_checkins / capacity_checkins_today
//               (the current Telegram-fed "MY CAPACITY TODAY" signal,
//               2026-08-21 — recovery_pulses / recovery_confidence_today are
//               retired, the bot no longer writes to them) + health_insights.
//   Medical   — analytics_health_daily (Life Participation + 30d trends),
//               human_systems_daily (four energy domains), recovery_indexes
//               derived from the same daily row.
//   Readiness — physical_workout_sessions (last session + 7d completed count)
//               and physical_readiness_checkins.
//
// The Life Participation and Recovery-Index derivations mirror the canonical
// logic in src/lib/ros-data.ts / the compute_life_participation SQL function so
// the workbench and the Medical Bay never disagree.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import type {
  Band,
  CapacityBalance,
  CapacityLoad,
  Kpis,
  NextMove,
  Payload,
  PostureBand,
  RecoveryIndex,
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
function computeRecoveryIndexes(d: DailyRow | null, blended: BlendedSignals): RecoveryIndex[] {
  const sleepHrs = d?.sleep_hours ?? 0;
  const sleepBand: Band = !d?.sleep_hours ? 'unknown' : sleepHrs >= 7 ? 'good' : sleepHrs >= 5.5 ? 'moderate' : 'limited';
  const cpapNote = d?.cpap_status?.toLowerCase() === 'yes' ? ' · CPAP compliant' : '';

  const ns = blended.nervous_system;
  const nsBand: Band = ns === 'calm' ? 'good' : ns === 'activated' ? 'moderate' : ns === 'dysregulated' ? 'limited' : 'unknown';
  const nsDetail = ns === 'calm' ? 'Calm — settled baseline' : ns === 'activated' ? 'Activated — protect capacity' : ns === 'dysregulated' ? 'Dysregulated — rest priority' : 'Not recorded';

  const energy = blended.energy;
  const energyBand: Band = energy === 'High' ? 'good' : energy === 'Moderate' ? 'moderate' : energy === 'Low' ? 'limited' : 'unknown';

  // Capacity: capacity_checkins wins when present (mirrors
  // compute_recovery_score()'s SQL priority); falls back to the old
  // captains_log_entries field for historical days it still has data for.
  const cap = d?.captain_capacity_rating;
  const capBand: Band = capacityStateBand(blended.capacityState) ??
    (cap === 'Green' ? 'good' : cap === 'Amber' ? 'moderate' : cap === 'Red' ? 'limited' : 'unknown');
  const capDetail = capacityStateDetail(blended.capacityState) ??
    (cap === 'Green' ? 'Green — full operational window' : cap === 'Amber' ? 'Amber — moderate window' : cap === 'Red' ? 'Red — minimal window' : 'Not recorded');

  return [
    { key: 'sleep', label: 'Sleep', band: sleepBand, detail: d?.sleep_hours ? `${sleepHrs}h · ${d.sleep_quality ?? 'Unknown quality'}${cpapNote}` : 'Not recorded (no capacity-checkin equivalent)' },
    { key: 'nervous_system', label: 'Nervous System', band: nsBand, detail: nsDetail },
    { key: 'energy', label: 'Energy', band: energyBand, detail: energy ? `${energy} — subjective daily report` : 'Not recorded' },
    { key: 'capacity', label: 'Capacity', band: capBand, detail: capDetail },
  ];
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
  };
}

async function buildMedical(sb: any, ctx: Ctx, kpis: Kpis): Promise<Payload> {
  const lp = computeLifeParticipation(ctx.daily);
  // Nervous System / Energy / Capacity now blend in capacity_checkins the
  // same way buildRecovery() does — see computeRecoveryIndexes()'s own
  // comment for why Sleep and Life Participation can't follow (no
  // capacity_checkins equivalent for those fields).
  const recovery_indexes = computeRecoveryIndexes(ctx.daily, deriveBlendedSignals(ctx));

  // Four energy domains from the human_systems_daily view (today).
  const { data: hsRow } = await sb
    .from('human_systems_daily')
    .select('energy_physical,energy_cognitive,energy_emotional,energy_social,daily_capacity_score')
    .eq('log_date', today())
    .maybeSingle();

  const domainBand = (v: string | null): Band =>
    v === 'good' ? 'good' : v === 'moderate' ? 'moderate' : v === 'limited' ? 'limited' : v === 'depleted' ? 'rest' : 'unknown';
  const energy_domains = [
    { key: 'physical', label: 'Physical', band: domainBand(hsRow?.energy_physical ?? null), value: hsRow?.energy_physical ?? null },
    { key: 'cognitive', label: 'Cognitive', band: domainBand(hsRow?.energy_cognitive ?? null), value: hsRow?.energy_cognitive ?? null },
    { key: 'emotional', label: 'Emotional', band: domainBand(hsRow?.energy_emotional ?? null), value: hsRow?.energy_emotional ?? null },
    { key: 'social', label: 'Social', band: domainBand(hsRow?.energy_social ?? null), value: hsRow?.energy_social ?? null },
  ];

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
    energy_domains,
    recovery_indexes,
    trends,
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
