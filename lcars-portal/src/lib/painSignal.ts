// Pain signal for the wellness alert + the EOS interrupt (R2 alignment,
// Phase 2 step 3). Newest-first capacity check-in rows in, one signal out.
//
// Red flag (PO decision, replaces pain_score 9-or-10): the latest check-in's
// pain_state is "high" ("Much higher than usual"), REGARDLESS OF CAPACITY.
// Deliberately no capacity condition — the old rule had none, and one would
// stop the flag for severe pain at Sustainable capacity.
//
// State-based trend (PO decision 2026-10-15, replaces "pain trend elevated" for new
// data): 3 or more of the last 5 check-ins at "higher than usual" (elevated) or
// "much higher than usual" (high), when the latest is not itself "high" (that case
// is the red flag above). Same 5-check-in window as before; a check-in with no pain
// state is simply not counted — it is neither elevated nor "no pain".
//
// Legacy numeric trend (history only): average of the 0-10 values that were
// actually recorded in the window, thresholds 8 (critical) / 6 (elevated) as
// before. A missing number is skipped, NEVER counted as 0 — new check-ins no
// longer carry a number and must not dilute the average toward "no pain".

export interface PainCheckinRow {
  pain_state?: string | null;
  pain_score?: number | null;
  captured_at: string;
}

export type PainSignal =
  | { kind: 'state_high'; evidenceAt: string }
  | { kind: 'state_trend_elevated'; count: number; window: number; evidenceAt: string }
  | { kind: 'trend_critical' | 'trend_elevated'; avg: number; n: number; evidenceAt: string };

export const PAIN_TREND_CRITICAL = 8;
export const PAIN_TREND_ELEVATED = 6;
/** State-based trend: this many of the last PAIN_STATE_WINDOW check-ins at elevated or high. */
export const PAIN_STATE_TREND_MIN = 3;
export const PAIN_STATE_WINDOW = 5;

export function evaluatePainSignal(rows: PainCheckinRow[]): PainSignal | null {
  if (rows.length === 0) return null;
  if (rows[0].pain_state === 'high') {
    return { kind: 'state_high', evidenceAt: rows[0].captured_at };
  }
  // Numeric history can still escalate to critical (avg > 8); check it first so that
  // stronger legacy signal is not hidden by the softer state trend below.
  const numeric = evaluateNumericTrend(rows);
  if (numeric?.kind === 'trend_critical') return numeric;

  const window = rows.slice(0, PAIN_STATE_WINDOW);
  const elevatedCount = window.filter((r) => r.pain_state === 'elevated' || r.pain_state === 'high').length;
  if (elevatedCount >= PAIN_STATE_TREND_MIN) {
    return { kind: 'state_trend_elevated', count: elevatedCount, window: window.length, evidenceAt: rows[0].captured_at };
  }
  return numeric;
}

function evaluateNumericTrend(rows: PainCheckinRow[]): PainSignal | null {
  const recorded = rows
    .map((r) => r.pain_score)
    .filter((v): v is number => typeof v === 'number' && !Number.isNaN(v));
  if (recorded.length === 0) return null; // unknown, not "no pain" — and not a zero
  const avg = recorded.reduce((a, b) => a + b, 0) / recorded.length;
  if (avg > PAIN_TREND_CRITICAL) return { kind: 'trend_critical', avg, n: recorded.length, evidenceAt: rows[0].captured_at };
  if (avg > PAIN_TREND_ELEVATED) return { kind: 'trend_elevated', avg, n: recorded.length, evidenceAt: rows[0].captured_at };
  return null;
}
