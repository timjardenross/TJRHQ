// computeStrategicPosture() — TypeScript mirror of core/health/
// burnout_trajectory.py's compute_burnout_trajectory(). See that file's
// header comment for the full spec context
// (TJR_Human_Systems_Workbench_V3_Mission_and_Change_Proposal.md,
// "V3 Mission 1"). This module exists as a sibling file rather than living
// in route.ts for the same reason computeInterventionEffectiveness() does
// (see intervention-effectiveness.ts's header comment): Next.js App Router
// route files only permit HTTP-method exports, and a directly-testable
// helper needs a home a unit test can import without mocking the whole GET
// handler's auth/session plumbing.
//
// LOCK-STEP REQUIREMENT: every named threshold constant and every branch
// below has a 1:1 counterpart in burnout_trajectory.py, same name
// (snake_case there, camelCase here), same value. Any recalibration must
// be made in BOTH files in the same change — this is the same discipline
// intervention_engine.py/computeInterventionEffectiveness() already
// document as siblings, just for a rules engine instead of a data
// passthrough. Do not let this drift — the workbench (this file) and the
// Capacity Bot / any future scheduled burnout_profile writer (the Python
// engine) must never disagree about what trajectory a given window of
// check-ins implies.

import type {
  RecoveryStage,
  StrategicPosture,
  SystemPostureBand,
  SystemTrajectory,
  TrajectoryConfidence,
} from '@/app/human-systems-workbench/_components/types';

export interface BurnoutWindowRow {
  checkin_type: string | null;
  capacity_state: string | null;
  executive_function: string | null;
  stimulation_state: string | null;
  compensation_load: string | null;
  recovery_duration: string | null;
  capacity_debt: string | null;
  log_date: string | null;
  captured_at: string | null;
}

export interface StrategicPostureResult {
  window_days: number;
  system_trajectory: SystemTrajectory;
  trajectory_confidence: TrajectoryConfidence;
  relevant_checkin_count: number;
  exhaustion_level: string | null;
  tolerance_change: string | null;
  recovery_trajectory: 'improving' | 'stable' | 'volatile' | 'deteriorating' | 'insufficient_data';
  current_recovery_stage: RecoveryStage | null;
  strategic_posture: StrategicPosture;
  strategic_posture_message: string;
  contributing_signals: Record<string, unknown>;
}

// ── Thresholds — mirror burnout_trajectory.py's module-level constants ──────

const MIN_CHECKINS_FOR_TRAJECTORY = 5;
const MIN_CHECKINS_FOR_MODERATE_CONFIDENCE = 8;
const MIN_CHECKINS_FOR_HIGH_CONFIDENCE = 12;
const MIN_EVENING_ROWS_FOR_HIGH_CONFIDENCE = 5;

const BURNOUT_LIKE_ORANGE_RED_PCT = 0.75;
const BURNOUT_LIKE_RED_PCT = 0.4;
const BURNOUT_LIKE_EVENING_DEBT_YES = 2;

const SUSTAINED_HIGH_ORANGE_RED_PCT = 0.6;
const SUSTAINED_HIGH_EVENING_DEBT_YES = 2;

const ACCUMULATING_ORANGE_RED_PCT = 0.4;
const ACCUMULATING_COMPENSATION_HIGH_PCT = 0.5;
const ACCUMULATING_EVENING_DEBT_YES_OR_MAYBE = 3;

const MIN_ROWS_PER_HALF_FOR_TREND = 2;

const EF_ORDINAL: Record<string, number> = { good: 0, strained: 1, difficult: 2, very_difficult: 3 };
const EF_WORSENING_DELTA = 0.5;

const TOLERANCE_EXTREME_RATE_RISE = 0.25;

const ELEVATED_RECOVERY_DURATION_LABELS = new Set(['Half a day', 'Full day', 'Multiple days']);
const ELEVATED_RECOVERY_DURATION_CODES = new Set(['hd', 'fd', 'md']);
const RECOVERY_DURATION_RISE_DELTA = 0.34;

const RECOVERY_IMPROVING_DELTA = -0.2;
const RECOVERY_DETERIORATING_DELTA = 0.2;

const POSTURE_RANK: Record<StrategicPosture, number> = {
  recover: 0, protect: 1, stabilise: 2, steady: 3, re_engage: 4, rebuild: 5, engage: 6, redesign: -1,
};
const RANK_TO_POSTURE: Record<number, StrategicPosture> = {
  0: 'recover', 1: 'protect', 2: 'stabilise', 3: 'steady', 4: 're_engage', 5: 'rebuild', 6: 'engage',
};

// redesign is never emitted by rank lookup — see burnout_trajectory.py's
// POSTURE_RANK comment for why it's excluded from this axis entirely.

const TODAY_POSTURE_TO_STRATEGIC: Record<SystemPostureBand, StrategicPosture> = {
  ENGAGE: 'engage', STEADY: 'steady', PROTECT: 'protect', RECOVER: 'recover', RESET: 'protect', UNKNOWN: 'steady',
};

const TRAJECTORY_FLOOR: Partial<Record<SystemTrajectory, StrategicPosture>> = {
  burnout_like_depletion: 'recover',
  sustained_high_strain: 'protect',
  accumulating_strain: 'protect',
  recovery_signals_emerging: 'stabilise',
  rebuilding: 're_engage',
};

const TRAJECTORY_TO_RECOVERY_STAGE: Partial<Record<SystemTrajectory, RecoveryStage>> = {
  accumulating_strain: 'protect',
  sustained_high_strain: 'stabilise',
  burnout_like_depletion: 'recover',
  recovery_signals_emerging: 're_engage',
  rebuilding: 'rebuild',
};

const STRATEGIC_MESSAGES: Record<SystemTrajectory, string> = {
  insufficient_data:
    "Not enough recent check-ins yet to read a sustained-strain trend — today's own posture is what's guiding this.",
  stable:
    "No sustained-strain pattern showing in the recent window — today's own posture applies without a trajectory adjustment.",
  accumulating_strain:
    'Sustained strain appears to be building. Favour steady or protective pacing even on an easier day.',
  sustained_high_strain:
    "Recent recovery demand has stayed high. Strategic posture stays protective — a better day today isn't evidence the wider strain has resolved.",
  burnout_like_depletion:
    'Sustained strain and recovery demand have stayed high for a while. Recovery is the priority — use any extra capacity selectively rather than as proof of recovery.',
  recovery_signals_emerging:
    'Some early signs of easing strain in the recent window — worth stabilising conditions before adding load back in.',
  rebuilding:
    'Recovery has been holding across the recent window — capacity can be reintroduced gradually, watching for recovery demand to rise again.',
};

// ── Helpers ───────────────────────────────────────────────────────────────

function sortKey(row: BurnoutWindowRow): string {
  return row.captured_at || row.log_date || '';
}

function splitHalves<T extends BurnoutWindowRow>(rows: T[]): [T[], T[]] {
  const ordered = [...rows].sort((a, b) => sortKey(a).localeCompare(sortKey(b)));
  const mid = Math.floor(ordered.length / 2);
  return [ordered.slice(0, mid), ordered.slice(mid)];
}

function rate<T>(rows: T[], predicate: (r: T) => boolean): number | null {
  if (rows.length === 0) return null;
  return rows.filter(predicate).length / rows.length;
}

function efOrdinalAvg(rows: BurnoutWindowRow[]): number | null {
  const vals = rows
    .map((r) => (r.executive_function ? EF_ORDINAL[r.executive_function] : undefined))
    .filter((v): v is number => v !== undefined);
  if (vals.length === 0) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function isElevatedRecoveryDuration(value: string | null | undefined): boolean {
  if (!value) return false;
  return ELEVATED_RECOVERY_DURATION_LABELS.has(value) || ELEVATED_RECOVERY_DURATION_CODES.has(value);
}

// ── Public API ────────────────────────────────────────────────────────────

/**
 * Derive the burnout_profile-shaped TRAJECTORY read from a window of
 * capacity_checkins rows — never called on a single row, and never
 * collapsed into deriveSystemPosture()'s NOW-only result (route.ts, V3
 * doc §2). See core/health/burnout_trajectory.py's
 * compute_burnout_trajectory() for the full rule-by-rule rationale; every
 * branch below mirrors it 1:1.
 */
export function computeStrategicPosture(
  checkins: BurnoutWindowRow[],
  windowDays: number,
  todayPosture: SystemPostureBand | null,
): StrategicPostureResult {
  const capacityRows = checkins.filter((c) => c.capacity_state);
  const eveningRows = checkins.filter((c) => c.checkin_type === 'evening');
  const deepRows = checkins.filter((c) => c.recovery_duration);

  const relevantCheckinCount = capacityRows.length;

  const contributingSignals: Record<string, unknown> = {
    window_days: windowDays,
    relevant_checkin_count: relevantCheckinCount,
    evening_row_count: eveningRows.length,
    deep_checkin_count: deepRows.length,
  };

  // ── Rule F — insufficient data, never fabricate a trajectory ─────────
  if (relevantCheckinCount < MIN_CHECKINS_FOR_TRAJECTORY) {
    const strategicPosture = TODAY_POSTURE_TO_STRATEGIC[todayPosture ?? 'UNKNOWN'];
    return {
      window_days: windowDays,
      system_trajectory: 'insufficient_data',
      trajectory_confidence: 'low',
      relevant_checkin_count: relevantCheckinCount,
      exhaustion_level: null,
      tolerance_change: null,
      recovery_trajectory: 'insufficient_data',
      current_recovery_stage: null,
      strategic_posture: strategicPosture,
      strategic_posture_message: STRATEGIC_MESSAGES.insufficient_data,
      contributing_signals: contributingSignals,
    };
  }

  // ── Whole-window aggregates ───────────────────────────────────────────
  const orangeRedPct = rate(capacityRows, (r) => r.capacity_state === 'orange' || r.capacity_state === 'red') ?? 0;
  const redPct = rate(capacityRows, (r) => r.capacity_state === 'red') ?? 0;
  const eveningDebtYes = eveningRows.filter((r) => r.capacity_debt === 'yes').length;
  const eveningDebtYesOrMaybe = eveningRows.filter((r) => r.capacity_debt === 'yes' || r.capacity_debt === 'maybe').length;
  const compensationHighPct =
    rate(capacityRows, (r) => r.compensation_load === 'high' || r.compensation_load === 'extreme') ?? 0;

  // ── Executive-function trend (Rule C) ─────────────────────────────────
  const [efEarlier, efLater] = splitHalves(capacityRows);
  const efAvgEarlier = efOrdinalAvg(efEarlier);
  const efAvgLater = efOrdinalAvg(efLater);
  const efWorsening =
    efEarlier.length >= MIN_ROWS_PER_HALF_FOR_TREND &&
    efLater.length >= MIN_ROWS_PER_HALF_FOR_TREND &&
    efAvgEarlier !== null &&
    efAvgLater !== null &&
    efAvgLater - efAvgEarlier >= EF_WORSENING_DELTA;

  // ── Tolerance / stimulation-extreme trend ─────────────────────────────
  const [stimEarlier, stimLater] = splitHalves(capacityRows);
  const extremeRateEarlier = rate(stimEarlier, (r) => r.stimulation_state === 'low' || r.stimulation_state === 'high');
  const extremeRateLater = rate(stimLater, (r) => r.stimulation_state === 'low' || r.stimulation_state === 'high');
  const toleranceFalling =
    stimEarlier.length >= MIN_ROWS_PER_HALF_FOR_TREND &&
    stimLater.length >= MIN_ROWS_PER_HALF_FOR_TREND &&
    extremeRateEarlier !== null &&
    extremeRateLater !== null &&
    extremeRateLater - extremeRateEarlier >= TOLERANCE_EXTREME_RATE_RISE;

  // ── Recovery-duration trend (Rule D) ──────────────────────────────────
  const [rdEarlier, rdLater] = splitHalves(deepRows);
  const rdRateEarlier = rate(rdEarlier, (r) => isElevatedRecoveryDuration(r.recovery_duration));
  const rdRateLater = rate(rdLater, (r) => isElevatedRecoveryDuration(r.recovery_duration));
  const recoveryDurationRising =
    rdEarlier.length >= MIN_ROWS_PER_HALF_FOR_TREND &&
    rdLater.length >= MIN_ROWS_PER_HALF_FOR_TREND &&
    rdRateEarlier !== null &&
    rdRateLater !== null &&
    rdRateLater - rdRateEarlier >= RECOVERY_DURATION_RISE_DELTA;

  // ── recovery_trajectory — capacity-state halves comparison ─────────────
  const [capEarlier, capLater] = splitHalves(capacityRows);
  const orangeRedEarlier = rate(capEarlier, (r) => r.capacity_state === 'orange' || r.capacity_state === 'red');
  const orangeRedLater = rate(capLater, (r) => r.capacity_state === 'orange' || r.capacity_state === 'red');
  let recoveryTrajectory: StrategicPostureResult['recovery_trajectory'];
  if (
    capEarlier.length < MIN_ROWS_PER_HALF_FOR_TREND ||
    capLater.length < MIN_ROWS_PER_HALF_FOR_TREND ||
    orangeRedEarlier === null ||
    orangeRedLater === null
  ) {
    recoveryTrajectory = 'insufficient_data';
  } else {
    const delta = orangeRedLater - orangeRedEarlier;
    if (delta <= RECOVERY_IMPROVING_DELTA) recoveryTrajectory = 'improving';
    else if (delta >= RECOVERY_DETERIORATING_DELTA) recoveryTrajectory = 'deteriorating';
    else if (efWorsening || toleranceFalling) recoveryTrajectory = 'volatile';
    else recoveryTrajectory = 'stable';
  }

  Object.assign(contributingSignals, {
    orange_red_pct: Math.round(orangeRedPct * 1000) / 1000,
    red_pct: Math.round(redPct * 1000) / 1000,
    evening_debt_yes_count: eveningDebtYes,
    evening_debt_yes_or_maybe_count: eveningDebtYesOrMaybe,
    compensation_high_pct: Math.round(compensationHighPct * 1000) / 1000,
    ef_worsening: efWorsening,
    tolerance_falling: toleranceFalling,
    recovery_duration_rising: recoveryDurationRising,
    recovery_trajectory: recoveryTrajectory,
  });

  // ── system_trajectory bucket — first matching rule wins ────────────────
  let systemTrajectory: SystemTrajectory;
  if (
    orangeRedPct >= BURNOUT_LIKE_ORANGE_RED_PCT &&
    redPct >= BURNOUT_LIKE_RED_PCT &&
    eveningDebtYes >= BURNOUT_LIKE_EVENING_DEBT_YES &&
    (efWorsening || toleranceFalling || compensationHighPct >= ACCUMULATING_COMPENSATION_HIGH_PCT)
  ) {
    systemTrajectory = 'burnout_like_depletion';
  } else if (orangeRedPct >= SUSTAINED_HIGH_ORANGE_RED_PCT && eveningDebtYes >= SUSTAINED_HIGH_EVENING_DEBT_YES) {
    systemTrajectory = 'sustained_high_strain';
  } else if (
    orangeRedPct >= ACCUMULATING_ORANGE_RED_PCT ||
    (efWorsening && toleranceFalling) ||
    compensationHighPct >= ACCUMULATING_COMPENSATION_HIGH_PCT ||
    eveningDebtYesOrMaybe >= ACCUMULATING_EVENING_DEBT_YES_OR_MAYBE ||
    recoveryTrajectory === 'deteriorating'
  ) {
    // Rule C — elevate concern even when capacity_state alone still looks
    // acceptable (Scenario 3's acceptance test).
    systemTrajectory = 'accumulating_strain';
  } else if (recoveryTrajectory === 'improving' && orangeRedEarlier !== null && orangeRedEarlier >= ACCUMULATING_ORANGE_RED_PCT) {
    const laterIsGood = orangeRedLater !== null && orangeRedLater < ACCUMULATING_ORANGE_RED_PCT;
    const laterEveningClear = !splitHalves(eveningRows)[1].some((r) => r.capacity_debt === 'yes');
    if (laterIsGood && laterEveningClear && capLater.length >= MIN_ROWS_PER_HALF_FOR_TREND) {
      systemTrajectory = 'rebuilding';
    } else {
      systemTrajectory = 'recovery_signals_emerging';
    }
  } else {
    systemTrajectory = 'stable';
  }

  // ── trajectory_confidence — sample-size only ────────────────────────────
  let trajectoryConfidence: TrajectoryConfidence;
  if (relevantCheckinCount >= MIN_CHECKINS_FOR_HIGH_CONFIDENCE && eveningRows.length >= MIN_EVENING_ROWS_FOR_HIGH_CONFIDENCE) {
    trajectoryConfidence = 'high';
  } else if (relevantCheckinCount >= MIN_CHECKINS_FOR_MODERATE_CONFIDENCE) {
    trajectoryConfidence = 'moderate';
  } else {
    trajectoryConfidence = 'low';
  }

  // ── exhaustion_level / tolerance_change — plain-language descriptors ───
  let exhaustionLevel: string;
  if (redPct >= BURNOUT_LIKE_RED_PCT) exhaustionLevel = 'high';
  else if (orangeRedPct >= ACCUMULATING_ORANGE_RED_PCT) exhaustionLevel = 'elevated';
  else if (orangeRedPct > 0) exhaustionLevel = 'moderate';
  else exhaustionLevel = 'low';

  const toleranceChange = toleranceFalling ? 'reduced' : 'stable';
  const currentRecoveryStage = TRAJECTORY_TO_RECOVERY_STAGE[systemTrajectory] ?? null;

  // ── strategic_posture — Rule A/D, mechanically enforced via rank ───────
  const todayRank = POSTURE_RANK[TODAY_POSTURE_TO_STRATEGIC[todayPosture ?? 'UNKNOWN']];
  const floorName = TRAJECTORY_FLOOR[systemTrajectory];
  let finalRank = floorName ? Math.min(todayRank, POSTURE_RANK[floorName]) : todayRank;

  // Rule D — a rising recovery-duration trend clamps the ceiling.
  if (recoveryDurationRising) {
    finalRank = Math.min(finalRank, POSTURE_RANK.stabilise);
  }

  // V3 doc §8.5 — rebuild only reachable with multiple corroborating
  // positive signals: a sustained 'rebuilding' trajectory PLUS today's own
  // posture independently ENGAGE PLUS no rising recovery-duration trend.
  if (systemTrajectory === 'rebuilding' && todayPosture === 'ENGAGE' && !recoveryDurationRising) {
    finalRank = POSTURE_RANK.rebuild;
  }

  const strategicPosture = RANK_TO_POSTURE[finalRank];
  const strategicPostureMessage = STRATEGIC_MESSAGES[systemTrajectory];

  return {
    window_days: windowDays,
    system_trajectory: systemTrajectory,
    trajectory_confidence: trajectoryConfidence,
    relevant_checkin_count: relevantCheckinCount,
    exhaustion_level: exhaustionLevel,
    tolerance_change: toleranceChange,
    recovery_trajectory: recoveryTrajectory,
    current_recovery_stage: currentRecoveryStage,
    strategic_posture: strategicPosture,
    strategic_posture_message: strategicPostureMessage,
    contributing_signals: contributingSignals,
  };
}
