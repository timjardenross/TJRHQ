/**
 * Assessed Context — Human Systems' small, stable read boundary for other
 * workbenches (Human Execution Loop mission, brief §6/§39/§40).
 *
 * Human Systems owns capacity_checkins and everything derived from it
 * (posture, trajectory, loads, needs). Ready Room and Weekly Review are not
 * allowed to re-derive that themselves or query capacity_checkins directly
 * — they read this one small object instead. This keeps the boundary
 * "Human Systems informs, never vetoes" (brief §7) enforceable in one
 * place: this file decides what "constrained" looks like; consumers only
 * decide what to DO with it (smaller Today cap, cautious phrasing, etc.),
 * never whether to hide or cancel work.
 *
 * Reuses the two already-canonical, already-shared posture engines rather
 * than inventing a third taxonomy:
 *   - deriveSystemPosture()   — NOW (today's single latest check-in)
 *   - computeStrategicPosture() — TRAJECTORY (21-day window)
 * Both are already imported directly by /api/weekly-review/route.ts; this
 * module exists so weekly-review (and now Ready Room, via the /context
 * route below) stop each re-implementing the capacity_checkins query that
 * feeds them. One query shape, one place it can drift from the underlying
 * table.
 *
 * Sensitivity boundary (brief §48): this object is already the "minimum
 * necessary" cut — no pain score, no diagnostic/burnout narrative text, no
 * masking/compensation detail. Consumers needing more (e.g. the full
 * Recovery/Medical payload) keep using /api/human-systems?domain=... — this
 * is deliberately not a replacement for that route, just the small slice
 * meant to cross workbench boundaries.
 */

import { deriveSystemPosture, type TodayCheckinInput } from './derive-system-posture';
import { computeStrategicPosture, type BurnoutWindowRow, type StrategicPostureResult } from './strategic-posture';
import type { SystemPostureBand } from '@/app/human-systems-workbench/_components/types';

export const TRAJECTORY_WINDOW_DAYS = 21;

// Same field list fetchStrategicPosture() (weekly-review/route.ts) already
// selected for "today's row" — extended with active_loads/identified_needs,
// the two additional fields the assessed-context object exposes that the
// posture-only read never needed.
const TODAY_FIELDS =
  'capacity_state,regulation_state,executive_function,compensation_load,stimulation_state,pain_state,active_loads,identified_needs,captured_at,log_date';
const WINDOW_FIELDS =
  'checkin_type,capacity_state,executive_function,stimulation_state,compensation_load,recovery_duration,capacity_debt,log_date,captured_at';

interface TodayRow extends TodayCheckinInput {
  active_loads: string[] | null;
  identified_needs: string[] | null;
  captured_at: string;
  log_date: string;
}

export type CapacityDirection = 'too_much' | 'not_enough' | 'sustainable' | 'unknown';

/**
 * Mirrors route.ts's deriveCapacityBalance() (same field logic, same
 * values) — duplicated here rather than imported because Next.js route.ts
 * files may only export HTTP method handlers (see derive-system-posture.ts
 * and strategic-posture.ts header comments for the same constraint). Any
 * recalibration of one must be made in the other in the same change.
 */
function capacityDirection(c: TodayRow | null): CapacityDirection {
  if (!c || !c.capacity_state) return 'unknown';
  if (c.stimulation_state === 'high' || c.capacity_state === 'red') return 'too_much';
  if (c.stimulation_state === 'low' && c.capacity_state !== 'red') return 'not_enough';
  if (c.capacity_state === 'orange') return 'too_much';
  return 'sustainable';
}

export type Freshness = 'fresh' | 'stale' | 'none';

export interface AssessedContext {
  /** NOW — today's single latest check-in, never blended with trajectory. */
  posture: SystemPostureBand;
  posture_message: string;
  available_capacity: 'green' | 'orange' | 'red' | 'unknown';
  capacity_direction: CapacityDirection;
  stimulation_context: string | null;
  executive_function_context: string | null;
  regulation_context: string | null;
  /** TRAJECTORY — a multi-day pattern, kept explicitly separate from NOW
   * per brief §8 ("a relatively good day must not automatically mean
   * recovery complete"). Callers should not fold this into `posture`. */
  strain_or_recovery_context: {
    trajectory: StrategicPostureResult['system_trajectory'];
    strategic_posture: StrategicPostureResult['strategic_posture'];
    message: string;
  };
  active_loads: string[];
  relevant_needs: string[];
  freshness: {
    status: Freshness;
    last_checkin_at: string | null;
  };
  /** Low whenever today has no check-in at all — a stale/absent check-in
   * should never be presented with the same confidence as a fresh one. */
  confidence: StrategicPostureResult['trajectory_confidence'];
  has_checkin_today: boolean;
}

function freshnessOf(lastCheckinAt: string | null): Freshness {
  if (!lastCheckinAt) return 'none';
  const ageMs = Date.now() - new Date(lastCheckinAt).getTime();
  if (ageMs <= 24 * 60 * 60 * 1000) return 'fresh';
  return 'stale';
}

/** Pure composition — no querying. Kept separate from getAssessedContext()
 * below so unit tests can exercise the freshness/posture/trajectory rules
 * without a Supabase client. */
export function buildAssessedContext(todayRow: TodayRow | null, windowRows: BurnoutWindowRow[]): AssessedContext {
  const { posture, message } = deriveSystemPosture(todayRow);
  const strategic = computeStrategicPosture(windowRows, TRAJECTORY_WINDOW_DAYS, posture);
  const lastCheckinAt = todayRow?.captured_at ?? null;
  const freshnessStatus = freshnessOf(lastCheckinAt);

  return {
    posture,
    posture_message: message,
    available_capacity: (todayRow?.capacity_state as 'green' | 'orange' | 'red' | null) ?? 'unknown',
    capacity_direction: capacityDirection(todayRow),
    stimulation_context: todayRow?.stimulation_state ?? null,
    executive_function_context: todayRow?.executive_function ?? null,
    regulation_context: todayRow?.regulation_state ?? null,
    strain_or_recovery_context: {
      trajectory: strategic.system_trajectory,
      strategic_posture: strategic.strategic_posture,
      message: strategic.strategic_posture_message,
    },
    active_loads: todayRow?.active_loads ?? [],
    relevant_needs: todayRow?.identified_needs ?? [],
    freshness: { status: freshnessStatus, last_checkin_at: lastCheckinAt },
    // A stale/absent today check-in caps confidence at 'low' regardless of
    // how much trajectory history exists — trajectory confidence describes
    // the window, not whether NOW is current (brief §42/§43).
    confidence: freshnessStatus === 'fresh' ? strategic.trajectory_confidence : 'low',
    has_checkin_today: freshnessStatus === 'fresh',
  };
}

// Matches the existing sb: any convention this domain's own route.ts already
// uses for every server-query helper (computeCapacityDebt, fetchBurnoutWindow, etc).
type SupabaseLike = { from: (table: string) => any };

/**
 * Server-side read boundary — the one place that queries capacity_checkins
 * for cross-workbench context. Callers (this domain's own /context route,
 * Weekly Review) get an AssessedContext back and never touch the table
 * directly (brief §39: "do not import one workbench's implementation
 * machinery into another").
 */
export async function getAssessedContext(sb: SupabaseLike): Promise<AssessedContext> {
  const today = new Date().toISOString().slice(0, 10);
  const windowStart = new Date(Date.now() - (TRAJECTORY_WINDOW_DAYS - 1) * 86_400_000).toISOString().slice(0, 10);

  const [todayResult, windowResult] = await Promise.all([
    sb
      .from('capacity_checkins')
      .select(TODAY_FIELDS)
      .eq('checkin_type', 'capacity')
      .eq('log_date', today)
      .order('captured_at', { ascending: false })
      .limit(1),
    sb
      .from('capacity_checkins')
      .select(WINDOW_FIELDS)
      .gte('log_date', windowStart)
      .lte('log_date', today),
  ]);

  const todayRow: TodayRow | null = (todayResult?.data ?? [])[0] ?? null;
  const windowRows: BurnoutWindowRow[] = windowResult?.data ?? [];

  return buildAssessedContext(todayRow, windowRows);
}
