/**
 * ROS-001 v1.1 — Phase 2 live data fetchers.
 *
 * Each function fetches from Supabase and maps onto the existing TypeScript
 * types used by all ROS pages. When the underlying env vars are absent or a
 * query fails, the function returns null — callers fall back to mock data.
 *
 * Sources:
 *   get_recovery_posture(date)     → RecoveryPosture
 *   analytics_health_daily (today) → BodyContext
 *   analytics_health_daily (7d)    → PostureHistory
 *   analytics_health_daily (21d)   → WeeklyPatternSummary + EmotionalLoadFlag
 */

import { createSupabaseBrowserClient } from './supabase-browser';
import { checkinNsState } from './human-systems';

// Session-aware client (WORKBENCH-REVIEW.md follow-up, 2026-07-18): the old
// plain `./supabase` client sent the anon key with no user JWT attached, so
// every query here ran as `anon`, not `authenticated`. That was silently
// covered by health_daily_logs' own anon_read policy until tonight's RLS fix
// (advisory_sessions leak closure) correctly dropped it - which broke every
// analytics_health_daily/get_recovery_posture(_range) call in this file with
// a real 401, not a graceful empty-data fallback. createSupabaseBrowserClient
// carries the real session cookie, so these now run as the actual user.
// Constructed fresh per call (matches every other caller in this codebase -
// @supabase/ssr's browser client isn't meant to be hoisted to module scope).
function client() {
  return createSupabaseBrowserClient();
}
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
  const supabase = client();
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
  const supabase = client();
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
  const supabase = client();
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

interface RawPostureDayRow {
  log_date:                 string;
  sleep_hours:              number | null;
  sleep_quality:            string | null;
  nervous_system_state:     string | null;
  energy:                   string | null;
  pain_score:               number | null;
  captain_capacity_rating:  string | null;
}

/**
 * Derive a recovery posture band from a single day's real check-in row.
 *
 * MSN-0351: the previous fallback labelled *every* day UNKNOWN even when a real
 * check-in existed for that day — hiding recorded data and reporting it as
 * absent. This derives an honest per-day posture from whatever signals the row
 * actually carries (sleep, nervous system, energy, pain, and the Captain's own
 * capacity rating). A day with a row but genuinely no usable signal — and a day
 * with no row at all — still resolve to UNKNOWN, which is the honest outcome.
 */
function derivePostureFromRow(row: RawPostureDayRow): { posture: RecoveryPostureBand; score: number | null } {
  const signals: number[] = [];

  if (row.sleep_hours != null && !Number.isNaN(Number(row.sleep_hours))) {
    signals.push(Math.max(0, Math.min(100, (Number(row.sleep_hours) / 7.5) * 100)));
  } else if (row.sleep_quality) {
    const q = row.sleep_quality.toLowerCase();
    signals.push(q === 'good' ? 85 : q === 'fair' ? 60 : q === 'poor' ? 30 : 50);
  }

  const ns = row.nervous_system_state?.toLowerCase();
  if (ns) signals.push(ns === 'calm' ? 90 : ns === 'activated' ? 52 : ns === 'dysregulated' ? 22 : 60);

  const en = row.energy?.toLowerCase();
  if (en) signals.push(en === 'high' ? 90 : en === 'moderate' ? 60 : en === 'low' ? 28 : 55);

  if (row.pain_score != null && !Number.isNaN(Number(row.pain_score))) {
    signals.push(Math.max(0, 100 - Number(row.pain_score) * 10));
  }

  const cap = row.captain_capacity_rating?.toLowerCase();

  // No usable signal and no self-rating → honestly unknown.
  if (!signals.length && !(cap === 'green' || cap === 'amber' || cap === 'red')) {
    return { posture: 'UNKNOWN', score: null };
  }

  let score = signals.length ? signals.reduce((a, b) => a + b, 0) / signals.length : 60;

  // Blend the Captain's own capacity rating when present (mirrors the weighting
  // interpretCapacity uses for captain_capacity_rating).
  if (cap === 'green' || cap === 'amber' || cap === 'red') {
    const self = cap === 'green' ? 85 : cap === 'amber' ? 55 : 25;
    score = signals.length ? 0.6 * score + 0.4 * self : self;
  }

  const rounded = Math.round(score);
  const posture: RecoveryPostureBand =
    score >= 75 ? 'STRONG' :
    score >= 55 ? 'STABLE' :
    score >= 35 ? 'FRAGILE' : 'REST';
  return { posture, score: rounded };
}

async function fetchPostureHistoryFallback(days: number): Promise<PostureHistory | null> {
  const supabase = client();
  try {
    const from = daysAgo(days - 1);
    // The get_recovery_posture_range RPC is absent — derive each day's posture
    // directly from the real per-day rows in analytics_health_daily instead of
    // blanket-filling UNKNOWN (which would hide recorded check-ins).
    const { data, error } = await supabase
      .from('analytics_health_daily')
      .select([
        'log_date', 'sleep_hours', 'sleep_quality', 'nervous_system_state',
        'energy', 'pain_score', 'captain_capacity_rating'
      ].join(','))
      .gte('log_date', from)
      .lte('log_date', today())
      .order('log_date', { ascending: true });

    if (error) return null;

    const rowsByDate = new Map<string, RawPostureDayRow>(
      ((data ?? []) as unknown as RawPostureDayRow[]).map((r) => [r.log_date, r])
    );

    const history = buildDateRange(from, today()).map((d) => {
      const row = rowsByDate.get(d);
      if (!row) return { date: d, posture: 'UNKNOWN' as RecoveryPostureBand, score: null };
      const { posture, score } = derivePostureFromRow(row);
      return { date: d, posture, score };
    });

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

/** Severity order for reducing a day's nervous-system signal to a single state. */
const NS_SEVERITY: Record<string, number> = { calm: 0, activated: 1, dysregulated: 2 };

/** The more severe of two nervous-system states (nulls lose to any real value). */
function worseNsState(a: string | null, b: string | null): string | null {
  if (!a) return b;
  if (!b) return a;
  return (NS_SEVERITY[b] ?? -1) > (NS_SEVERITY[a] ?? -1) ? b : a;
}

/**
 * MSN-0355 (original), realigned 2026-08-22 for MY CAPACITY TODAY: this flag
 * previously read ONLY `analytics_health_daily`, a view over
 * `captains_log_entries` FULL JOIN `health_daily_logs` — both of which
 * stopped receiving rows well before `recovery_pulses` itself was retired
 * in favour of `capacity_checkins`. `analytics_health_daily` itself is not
 * broken — it is a live view correctly reflecting stale source tables — so
 * the fix is not a SQL repair. Per the Captain's instruction not to
 * silently prefer whichever table happens to have rows, this merges BOTH
 * sources per day rather than switching exclusively to one:
 *   - `analytics_health_daily.nervous_system_state` (may be present for
 *     older days, or again if the daily-log habit resumes)
 *   - `capacity_checkins` (the current real signal), resolved per row via
 *     `checkinNsState` — `regulation_state` is a direct real-time reading,
 *     not a derived heuristic
 * A day can carry several check-ins with different readings (spec allows
 * unlimited check-ins/day, unlike the retired pulse model's 3-slot cap).
 * Because this flag exists to catch sustained activation, a day's state is
 * the WORST (most activated/dysregulated) signal recorded that day, not the
 * latest — averaging or "most recent wins" would let an earlier
 * dysregulated check-in be masked by a later calmer one.
 */
export async function fetchEmotionalLoadFlag(): Promise<EmotionalLoadFlag | null> {
  const supabase = client();
  try {
    const from = daysAgo(6);
    const to = today();

    const [analyticsRes, checkinRes] = await Promise.all([
      supabase
        .from('analytics_health_daily')
        .select('log_date, nervous_system_state')
        .gte('log_date', from)
        .lte('log_date', to),
      supabase
        .from('capacity_checkins')
        .select('log_date, regulation_state')
        .eq('checkin_type', 'capacity')
        .gte('log_date', from)
        .lte('log_date', to)
    ]);

    if (analyticsRes.error || checkinRes.error) return null;

    const byDate = new Map<string, string | null>();

    const analyticsRows = (analyticsRes.data ?? []) as { log_date: string; nervous_system_state: string | null }[];
    for (const row of analyticsRows) {
      byDate.set(row.log_date, row.nervous_system_state ?? null);
    }

    const checkinRows = (checkinRes.data ?? []) as { log_date: string; regulation_state: string | null }[];
    for (const checkin of checkinRows) {
      const ns = checkinNsState(checkin);
      if (!ns) continue;
      byDate.set(checkin.log_date, worseNsState(byDate.get(checkin.log_date) ?? null, ns));
    }

    const states       = Array.from(byDate.values());
    const recordedDays = states.filter((s): s is string => !!s).length;
    const activated     = states.filter((s) => s === 'activated').length;
    const dysregulated  = states.filter((s) => s === 'dysregulated').length;
    const raised        = (activated + dysregulated) >= 3;
    const noRecentData  = recordedDays === 0;

    return {
      raised,
      activated_days:    activated,
      dysregulated_days: dysregulated,
      recorded_days:     recordedDays,
      noRecentData,
      period:            'Last 7 days',
      message: noRecentData
        ? 'No nervous-system signal recorded in the last 7 days — no check-ins or pulses logged. This is not a "clear" reading; there is nothing to evaluate.'
        : raised
          ? `Nervous system activation elevated — ${activated + dysregulated} of ${recordedDays} recorded day${recordedDays !== 1 ? 's' : ''} activated or dysregulated. Number One has reduced sprint commitments accordingly.`
          : `Nervous system activation within expected range across ${recordedDays} recorded day${recordedDays !== 1 ? 's' : ''}. No flag raised.`
    };
  } catch {
    return null;
  }
}

// ── Life Participation Score (today) ─────────────────────────────────────────

export async function fetchLifeParticipation(date?: string): Promise<LifeParticipationScore | null> {
  const supabase = client();
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
  const supabase = client();
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
