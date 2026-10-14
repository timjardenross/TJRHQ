// Pain signal for the wellness alert + the EOS interrupt (R2 alignment,
// Phase 2 step 3). Newest-first capacity check-in rows in, one signal out.
//
// Red flag (PO decision, replaces pain_score 9-or-10): the latest check-in's
// pain_state is "high" ("Much higher than usual"), REGARDLESS OF CAPACITY.
// Deliberately no capacity condition — the old rule had none, and one would
// stop the flag for severe pain at Sustainable capacity.
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
  | { kind: 'trend_critical' | 'trend_elevated'; avg: number; n: number; evidenceAt: string };

export const PAIN_TREND_CRITICAL = 8;
export const PAIN_TREND_ELEVATED = 6;

export function evaluatePainSignal(rows: PainCheckinRow[]): PainSignal | null {
  if (rows.length === 0) return null;
  if (rows[0].pain_state === 'high') {
    return { kind: 'state_high', evidenceAt: rows[0].captured_at };
  }
  const recorded = rows
    .map((r) => r.pain_score)
    .filter((v): v is number => typeof v === 'number' && !Number.isNaN(v));
  if (recorded.length === 0) return null; // unknown, not "no pain" — and not a zero
  const avg = recorded.reduce((a, b) => a + b, 0) / recorded.length;
  if (avg > PAIN_TREND_CRITICAL) return { kind: 'trend_critical', avg, n: recorded.length, evidenceAt: rows[0].captured_at };
  if (avg > PAIN_TREND_ELEVATED) return { kind: 'trend_elevated', avg, n: recorded.length, evidenceAt: rows[0].captured_at };
  return null;
}
