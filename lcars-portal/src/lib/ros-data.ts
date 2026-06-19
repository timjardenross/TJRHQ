/**
 * ROS-001 v1.1 — Phase 2 live data fetchers.
 *
 * Each function fetches from Supabase and maps onto the existing TypeScript
 * types used by all ROS pages. When supabase client is null (env vars absent)
 * or a query fails, the function returns null — callers fall back to mock data.
 *
 * Sources:
 *   get_recovery_posture(date)     → RecoveryPosture
 *   analytics_health_daily (today) → BodyContext
 *   analytics_health_daily (7d)    → PostureHistory
 *   analytics_health_daily (21d)   → WeeklyPatternSummary + EmotionalLoadFlag
 */

import { supabase } from './supabase';
import type {
  BodyContext,
  CapacityBand,
  EmotionalLoadFlag,
  LifeParticipationScore,
  NervousSystemState,
  PostureHistory,
  RecoveryIndex,
  RecoveryPosture,
  RecoveryPostureBand,
  StatusTone,
  WeeklyPatternSummary
} from './types';

// ── helpers ──────────────────────────────────────────────────────────────────

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

// ── get_recovery_posture ─────────────────────────────────────────────────────

interface RawPostureRow {
  posture:          string;
  posture_message:  string;
  capacity_band:    string;
  capacity_message: string;
  mission_guidance: string;
  score:            number | null;
  data_available:   boolean;
}

export async function fetchRecoveryPosture(date?: string): Promise<RecoveryPosture | null> {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .rpc('get_recovery_posture', { p_date: date ?? today() })
      .single<RawPostureRow>();
    if (error || !data) return null;

    return {
      posture:          (data.posture as RecoveryPostureBand) ?? 'UNKNOWN',
      posture_message:  data.posture_message,
      capacity_band:    (data.capacity_band as CapacityBand) ?? 'UNKNOWN',
      capacity_message: data.capacity_message,
      best_window:      deriveBestWindow(data.capacity_band),
      mission_guidance: data.mission_guidance,
      data_available:   data.data_available
    };
  } catch {
    return null;
  }
}

function deriveBestWindow(capacity_band: string): string {
  switch (capacity_band) {
    case 'GOOD':     return '09:00–13:00';
    case 'MODERATE': return '09:00–12:30';
    case 'LIMITED':  return '09:00–11:00';
    case 'REST':     return 'Rest priority — minimal window';
    default:         return 'No data';
  }
}

// ── analytics_health_daily (today) → BodyContext ─────────────────────────────

interface RawHealthRow {
  sleep_hours:              number | null;
  sleep_quality:            string | null;
  cpap_status:              string | null;
  cpap_hours:               number | null;
  nervous_system_state:     string | null;
  energy:                   string | null;
  pain_score:               number | null;
  sitting_tolerance_minutes: number | null;
  workload_constraint:      string | null;
  movement_notes:           string | null;
  pleasure_creativity_marker: string | null;
  what_happened:            string | null;
  captain_capacity_rating:  string | null;
}

export async function fetchBodyContext(date?: string): Promise<BodyContext | null> {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from('analytics_health_daily')
      .select([
        'sleep_hours', 'sleep_quality', 'cpap_status', 'cpap_hours',
        'nervous_system_state', 'energy', 'pain_score',
        'sitting_tolerance_minutes', 'workload_constraint'
      ].join(','))
      .eq('log_date', date ?? today())
      .maybeSingle<RawHealthRow>();
    if (error || !data) return null;

    const cpap_compliant =
      (data.cpap_hours != null && data.sleep_hours != null && data.sleep_hours > 0
        ? data.cpap_hours >= data.sleep_hours * 0.9
        : data.cpap_status?.toLowerCase() === 'yes') ?? false;

    const ns = (data.nervous_system_state as NervousSystemState | null) ?? 'calm';

    const pain = data.pain_score;
    const body_signals: BodyContext['body_signals'] =
      pain == null ? 'Low' :
      pain <= 3    ? 'Low' :
      pain <= 6    ? 'Moderate' : 'High';

    return {
      sleep_hours:          data.sleep_hours ?? 0,
      sleep_quality:        (data.sleep_quality as BodyContext['sleep_quality']) ?? 'Fair',
      cpap_compliant,
      nervous_system_state: ns,
      energy:               (data.energy as BodyContext['energy']) ?? 'Moderate',
      body_signals,
      sitting_window_minutes: data.sitting_tolerance_minutes ?? 0
    };
  } catch {
    return null;
  }
}

// ── analytics_health_daily (7d) → PostureHistory ────────────────────────────

export async function fetchPostureHistory(days = 7): Promise<PostureHistory | null> {
  if (!supabase) return null;
  try {
    const from = daysAgo(days - 1);
    const to   = today();

    const { data, error } = await supabase
      .rpc('get_recovery_posture_range', { p_from: from, p_to: to })
      .select('date,posture,score');

    if (error) {
      // Fallback: build history from individual daily calls
      return fetchPostureHistoryFallback(days);
    }

    const rows = (data ?? []) as { date: string; posture: string; score: number | null }[];
    // Fill in missing days as UNKNOWN
    const history = buildDateRange(from, to).map((d) => {
      const row = rows.find((r) => r.date === d);
      return {
        date:    d,
        posture: (row?.posture as RecoveryPostureBand) ?? 'UNKNOWN',
        score:   row?.score ?? null
      };
    });

    return { days: history, period_label: `Last ${days} days` };
  } catch {
    return null;
  }
}

async function fetchPostureHistoryFallback(days: number): Promise<PostureHistory | null> {
  if (!supabase) return null;
  try {
    const from = daysAgo(days - 1);
    // Query analytics_health_daily and compute posture via the score function
    // Simpler: just query the view for the date range and return UNKNOWN for each day
    // (the RPC function doesn't exist yet — this will return nulls gracefully)
    const { data, error } = await supabase
      .from('analytics_health_daily')
      .select('log_date')
      .gte('log_date', from)
      .lte('log_date', today())
      .order('log_date', { ascending: true });

    if (error) return null;

    const recordedDates = new Set((data ?? []).map((r: { log_date: string }) => r.log_date));
    const history = buildDateRange(from, today()).map((d) => ({
      date:    d,
      posture: recordedDates.has(d) ? ('UNKNOWN' as RecoveryPostureBand) : ('UNKNOWN' as RecoveryPostureBand),
      score:   null
    }));

    return { days: history, period_label: `Last ${days} days` };
  } catch {
    return null;
  }
}

// ── WeeklyPatternSummary from posture history ────────────────────────────────

export async function fetchWeeklyPatternSummary(): Promise<WeeklyPatternSummary | null> {
  const history7  = await fetchPostureHistory(7);
  const history21 = await fetchPostureHistory(21);
  if (!history7 || !history21) return null;

  const count7 = countPostures(history7.days.map((d) => d.posture));
  const stableOrStrong21 = history21.days.filter(
    (d) => d.posture === 'STABLE' || d.posture === 'STRONG'
  ).length;
  const recorded21 = history21.days.filter((d) => d.posture !== 'UNKNOWN').length;

  const direction = deriveDirection(history7.days.map((d) => d.posture));

  return {
    period_7d:   count7,
    period_30d:  { stable_or_strong: stableOrStrong21, total_recorded: recorded21 },
    direction,
    direction_label: DIRECTION_LABEL[direction]
  };
}

function countPostures(postures: RecoveryPostureBand[]) {
  return {
    strong:  postures.filter((p) => p === 'STRONG').length,
    stable:  postures.filter((p) => p === 'STABLE').length,
    fragile: postures.filter((p) => p === 'FRAGILE').length,
    rest:    postures.filter((p) => p === 'REST').length,
    unknown: postures.filter((p) => p === 'UNKNOWN').length
  };
}

function deriveDirection(postures: RecoveryPostureBand[]): WeeklyPatternSummary['direction'] {
  const recorded = postures.filter((p) => p !== 'UNKNOWN');
  if (recorded.length < 3) return 'insufficient_data';
  const good = recorded.filter((p) => p === 'STABLE' || p === 'STRONG').length;
  const ratio = good / recorded.length;
  if (ratio >= 0.7) return 'settling';
  if (ratio >= 0.4) return 'steady';
  return 'variable';
}

const DIRECTION_LABEL: Record<WeeklyPatternSummary['direction'], string> = {
  settling:          'Pattern is settling — majority of recorded days stable or strong',
  steady:            'Pattern is steady — mixed posture days, no sustained decline',
  variable:          'Pattern is variable — more fragile or rest days than stable or strong',
  insufficient_data: 'Insufficient data — pattern will clarify as check-ins are recorded'
};

// ── EmotionalLoadFlag ────────────────────────────────────────────────────────

export async function fetchEmotionalLoadFlag(): Promise<EmotionalLoadFlag | null> {
  if (!supabase) return null;
  try {
    const from = daysAgo(6);
    const { data, error } = await supabase
      .from('analytics_health_daily')
      .select('log_date, nervous_system_state')
      .gte('log_date', from)
      .lte('log_date', today())
      .order('log_date', { ascending: true });

    if (error || !data) return null;

    const rows = data as { log_date: string; nervous_system_state: string | null }[];
    const activated    = rows.filter((r) => r.nervous_system_state === 'activated').length;
    const dysregulated = rows.filter((r) => r.nervous_system_state === 'dysregulated').length;
    const raised       = (activated + dysregulated) >= 3;

    return {
      raised,
      activated_days:    activated,
      dysregulated_days: dysregulated,
      period:            'Last 7 days',
      message: raised
        ? `Nervous system activation elevated — ${activated + dysregulated} of 7 days activated or dysregulated. Number One has reduced sprint commitments accordingly.`
        : `Nervous system activation within expected range. No flag raised.`
    };
  } catch {
    return null;
  }
}

// ── Life Participation Score (today) ─────────────────────────────────────────

export async function fetchLifeParticipation(date?: string): Promise<LifeParticipationScore | null> {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from('analytics_health_daily')
      .select([
        'movement_notes', 'pleasure_creativity_marker', 'what_happened',
        'sitting_tolerance_minutes', 'workload_constraint'
      ].join(','))
      .eq('log_date', date ?? today())
      .maybeSingle<RawHealthRow>();

    if (error || !data) return null;

    const movement_done    = !!(data.movement_notes?.trim());
    const pleasure_marker  = data.pleasure_creativity_marker?.trim() || null;
    const social_noted     = !!(data.what_happened?.trim());
    const sitting_minutes  = data.sitting_tolerance_minutes ?? 0;
    const sitting_baseline = 120;
    const constraint       = (data.workload_constraint ?? 'unknown') as LifeParticipationScore['workload_constraint'];

    // Mirror SQL compute_life_participation logic
    const v_movement  = movement_done ? 100 : 0;
    const v_pleasure  = pleasure_marker ? 100 : 0;
    const v_social    = social_noted ? 50 : 25;
    const v_sitting   = Math.min((sitting_minutes / sitting_baseline) * 100, 100);
    const v_workload  =
      constraint === 'none'     ? 100 :
      constraint === 'light'    ? 70  :
      constraint === 'moderate' ? 40  :
      constraint === 'severe'   ? 10  : 50;

    const score = Math.round(
      v_movement * 0.25 +
      v_pleasure * 0.20 +
      v_social   * 0.20 +
      v_sitting  * 0.20 +
      v_workload * 0.15
    );

    const band: LifeParticipationScore['band'] =
      score >= 75 ? 'good' :
      score >= 55 ? 'moderate' :
      score >= 35 ? 'limited' : 'rest';

    return {
      score, band, movement_done, pleasure_marker, social_noted,
      sitting_minutes, sitting_baseline_minutes: sitting_baseline,
      workload_constraint: constraint
    };
  } catch {
    return null;
  }
}

// ── Recovery Indexes (derived from today's analytics_health_daily) ───────────

export async function fetchRecoveryIndexes(date?: string): Promise<RecoveryIndex[] | null> {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from('analytics_health_daily')
      .select([
        'sleep_hours', 'sleep_quality', 'cpap_status', 'cpap_hours',
        'nervous_system_state', 'energy', 'captain_capacity_rating'
      ].join(','))
      .eq('log_date', date ?? today())
      .maybeSingle<RawHealthRow>();

    if (error || !data) return null;

    const sleepHrs = data.sleep_hours ?? 0;
    const sleepBand = sleepHrs >= 7 ? 'good' : sleepHrs >= 5.5 ? 'moderate' : 'limited';
    const sleepTone: StatusTone = sleepBand === 'good' ? 'status' : sleepBand === 'moderate' ? 'command' : 'operations';
    const cpapNote = data.cpap_status?.toLowerCase() === 'yes' ? ' · CPAP compliant' : '';

    const ns = data.nervous_system_state;
    const nsBand = ns === 'calm' ? 'good' : ns === 'activated' ? 'moderate' : ns === 'dysregulated' ? 'limited' : 'unknown';
    const nsTone: StatusTone = nsBand === 'good' ? 'status' : nsBand === 'moderate' ? 'command' : nsBand === 'limited' ? 'operations' : 'neutral';
    const nsDetail = ns === 'calm' ? 'Calm — settled baseline' : ns === 'activated' ? 'Activated — protect capacity' : ns === 'dysregulated' ? 'Dysregulated — rest priority' : 'Not recorded';

    const energy = data.energy;
    const energyBand = energy === 'High' ? 'good' : energy === 'Moderate' ? 'moderate' : energy === 'Low' ? 'limited' : 'unknown';
    const energyTone: StatusTone = energyBand === 'good' ? 'status' : energyBand === 'moderate' ? 'command' : energyBand === 'limited' ? 'operations' : 'neutral';

    const cap = data.captain_capacity_rating;
    const capBand = cap === 'Green' ? 'good' : cap === 'Amber' ? 'moderate' : cap === 'Red' ? 'limited' : 'unknown';
    const capTone: StatusTone = capBand === 'good' ? 'status' : capBand === 'moderate' ? 'command' : capBand === 'limited' ? 'operations' : 'neutral';
    const capDetail = cap === 'Green' ? 'Green rating — full operational window' : cap === 'Amber' ? 'Amber rating — moderate operational window' : cap === 'Red' ? 'Red rating — minimal operational window' : 'Not recorded';

    return [
      { key: 'sleep',          label: 'Sleep',          band: sleepBand as RecoveryIndex['band'], detail: `${sleepHrs}h · ${data.sleep_quality ?? 'Unknown quality'}${cpapNote}`, tone: sleepTone },
      { key: 'nervous_system', label: 'Nervous System', band: nsBand    as RecoveryIndex['band'], detail: nsDetail,  tone: nsTone },
      { key: 'energy',         label: 'Energy',         band: energyBand as RecoveryIndex['band'], detail: energy ? `${energy} — subjective daily report` : 'Not recorded', tone: energyTone },
      { key: 'capacity',       label: 'Capacity',       band: capBand   as RecoveryIndex['band'], detail: capDetail, tone: capTone }
    ];
  } catch {
    return null;
  }
}

// ── Shared utility ───────────────────────────────────────────────────────────

function buildDateRange(from: string, to: string): string[] {
  const dates: string[] = [];
  const cur = new Date(from);
  const end = new Date(to);
  while (cur <= end) {
    dates.push(cur.toISOString().slice(0, 10));
    cur.setDate(cur.getDate() + 1);
  }
  return dates;
}
