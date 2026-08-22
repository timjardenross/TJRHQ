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
  Kpis,
  Payload,
  PostureBand,
  RecoveryIndex,
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

function computeRecoveryIndexes(d: DailyRow | null): RecoveryIndex[] {
  if (!d) return [];
  const sleepHrs = d.sleep_hours ?? 0;
  const sleepBand: Band = sleepHrs >= 7 ? 'good' : sleepHrs >= 5.5 ? 'moderate' : 'limited';
  const cpapNote = d.cpap_status?.toLowerCase() === 'yes' ? ' · CPAP compliant' : '';

  const ns = d.nervous_system_state;
  const nsBand: Band = ns === 'calm' ? 'good' : ns === 'activated' ? 'moderate' : ns === 'dysregulated' ? 'limited' : 'unknown';
  const nsDetail = ns === 'calm' ? 'Calm — settled baseline' : ns === 'activated' ? 'Activated — protect capacity' : ns === 'dysregulated' ? 'Dysregulated — rest priority' : 'Not recorded';

  const energy = d.energy;
  const energyBand: Band = energy === 'High' ? 'good' : energy === 'Moderate' ? 'moderate' : energy === 'Low' ? 'limited' : 'unknown';

  const cap = d.captain_capacity_rating;
  const capBand: Band = cap === 'Green' ? 'good' : cap === 'Amber' ? 'moderate' : cap === 'Red' ? 'limited' : 'unknown';
  const capDetail = cap === 'Green' ? 'Green — full operational window' : cap === 'Amber' ? 'Amber — moderate window' : cap === 'Red' ? 'Red — minimal window' : 'Not recorded';

  return [
    { key: 'sleep', label: 'Sleep', band: sleepBand, detail: `${sleepHrs}h · ${d.sleep_quality ?? 'Unknown quality'}${cpapNote}` },
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
}

async function loadCtx(sb: any): Promise<Ctx> {
  const t = today();
  const sevenDaysAgo = new Date(Date.now() - 7 * 86_400_000).toISOString();

  const [postureRes, dailyRes, checkinRes, checkinsTodayRes, sessionCountRes] = await Promise.all([
    sb.rpc('get_recovery_posture', { p_date: t }).single(),
    sb.from('analytics_health_daily')
      .select('sleep_hours,sleep_quality,cpap_status,nervous_system_state,energy,pain_score,movement_notes,pleasure_creativity_marker,what_happened,sitting_tolerance_minutes,workload_constraint,captain_capacity_rating')
      .eq('log_date', t).maybeSingle(),
    sb.from('capacity_checkins')
      // capacity_state/regulation_state/executive_function are the canonical
      // Telegram-bot "MY CAPACITY TODAY" fields (recovery_pulses is
      // retired, 2026-08-21). Quick check-ins only — checkin_type also
      // covers 'evening' rows, which this route doesn't merge in here.
      .select('captured_at,capacity_state,regulation_state,pain_score,executive_function')
      .eq('checkin_type', 'capacity')
      .eq('log_date', t).order('captured_at', { ascending: false }).limit(1).maybeSingle(),
    sb.from('capacity_checkins_today').select('*').maybeSingle(),
    sb.from('physical_workout_sessions')
      .select('id', { count: 'exact', head: true })
      .eq('status', 'completed').gte('started_at', sevenDaysAgo),
  ]);

  return {
    posture: (postureRes.data as RawPostureRow) ?? null,
    daily: (dailyRes.data as DailyRow) ?? null,
    latestCheckin: (checkinRes.data as CheckinRow) ?? null,
    checkinsToday: (checkinsTodayRes.data as CheckinsTodayRow) ?? null,
    sessions7d: sessionCountRes.count ?? 0,
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
  };
}

// ── Domain builders ──────────────────────────────────────────────────────────

async function buildRecovery(sb: any, ctx: Ctx, kpis: Kpis): Promise<Payload> {
  const p = ctx.posture;
  const c = ctx.checkinsToday;

  // Energy / nervous-system: prefer today's daily row, fall back to the
  // latest capacity check-in (the current signal), then the today-view's own
  // latest reading — exactly as /api/wellness does.
  const energy =
    ctx.daily?.energy ??
    energyFromCapacityState(ctx.latestCheckin?.capacity_state) ??
    energyFromCapacityState(c?.latest_capacity_state) ??
    null;
  const nervous_system =
    ctx.daily?.nervous_system_state ??
    checkinNsState(ctx.latestCheckin) ??
    checkinNsState({ regulation_state: c?.latest_regulation_state ?? null }) ??
    null;

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
      narrative: ins?.llm_narrative ?? null,
      // Guard: these columns are arrays in the live schema, but coerce
      // defensively so a null / unexpected shape can never crash the view's map.
      risk_flags: Array.isArray(ins?.risk_flags) ? ins!.risk_flags : [],
      positive_flags: Array.isArray(ins?.positive_flags) ? ins!.positive_flags : [],
      wins: Array.isArray(ins?.wins_this_week) ? ins!.wins_this_week : [],
      insight_date: ins?.created_at ?? null,
    },
    data_available: !!p?.data_available,
  };
}

async function buildMedical(sb: any, ctx: Ctx, kpis: Kpis): Promise<Payload> {
  const lp = computeLifeParticipation(ctx.daily);
  const recovery_indexes = computeRecoveryIndexes(ctx.daily);

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

  // 30-day trends.
  const { data: trendRows } = await sb
    .from('analytics_health_daily')
    .select('log_date,energy,sleep_quality,nervous_system_state,pain_score')
    .gte('log_date', daysAgo(29))
    .lte('log_date', today())
    .order('log_date', { ascending: true });

  const trends: TrendRow[] = (trendRows ?? []).map((r: any) => ({
    log_date: r.log_date,
    energy: r.energy ?? null,
    sleep_quality: r.sleep_quality ?? null,
    nervous_system_state: r.nervous_system_state ?? null,
    pain_score: r.pain_score ?? null,
  }));

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
