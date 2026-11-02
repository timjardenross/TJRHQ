// TypeScript mirror of core/health/good_day.py (provisional "good day" rule, agreed 2026-11-02,
// revised 2026-11-03). Keep the two in step: __tests__/good-day.test.ts uses the same scenarios as
// telegram-bots/capacitybot/test_evening_checkin.py.
//
// A day is a likely good day when it stayed the same or improved and the whole-day compensation was
// moderate or lower. A missing answer is unknown and is never counted against the day. The Captain's
// own "Was today a good day?" answer, when given, always wins. Borrowed capacity is deliberately not
// part of the rule (still asked and stored; feeds the burnout trend and the day plan).

export interface EveningRow {
  log_date: string;
  captured_at?: string | null;
  day_trajectory?: string | null;
  day_compensation_load?: string | null;
  good_day?: string | null;
}

export interface GoodDaySummary {
  judged: number;
  good: number;
  longest_run: number;
}

const COMP_OK = ['low', 'moderate'];

/** true / false for a likely good / not-good day, or null when there's nothing to judge. */
export function provisionalGoodDay(evening: Partial<EveningRow> | null | undefined): boolean | null {
  if (!evening) return null;
  if (evening.good_day === 'yes') return true;
  if (evening.good_day === 'no') return false;
  // "kind_of" and a missing answer fall through to the rule.
  const checks: boolean[] = [];
  if (evening.day_trajectory != null) checks.push(['same', 'improved'].includes(evening.day_trajectory));
  if (evening.day_compensation_load != null) checks.push(COMP_OK.includes(evening.day_compensation_load));
  if (checks.length === 0) return null;
  return checks.every(Boolean);
}

/** The latest evening row for each calendar date. */
export function latestEveningByDate(rows: EveningRow[]): Map<string, EveningRow> {
  const latest = new Map<string, EveningRow>();
  for (const row of rows) {
    if (!row.log_date) continue;
    const day = String(row.log_date).slice(0, 10);
    const prev = latest.get(day);
    if (!prev || String(row.captured_at ?? '') >= String(prev.captured_at ?? '')) latest.set(day, row);
  }
  return latest;
}

function isNextDay(prev: string, cur: string): boolean {
  return Date.parse(`${cur}T00:00:00Z`) - Date.parse(`${prev}T00:00:00Z`) === 86_400_000;
}

/** Good days over a window of evening rows: how many days had a verdict, how many were good, and the
 *  longest run of consecutive calendar days that were all good. A day with no evening answer, or no
 *  verdict, is unknown and ends a run. */
export function summarizeGoodDays(rows: EveningRow[]): GoodDaySummary {
  const verdicts = new Map<string, boolean | null>();
  for (const [day, row] of latestEveningByDate(rows)) verdicts.set(day, provisionalGoodDay(row));
  const judgedDays = [...verdicts.entries()].filter(([, v]) => v !== null).map(([d]) => d).sort();
  const goodDays = judgedDays.filter((d) => verdicts.get(d) === true);
  let longest = 0;
  let run = 0;
  let prev: string | null = null;
  for (const d of goodDays) {
    run = prev !== null && isNextDay(prev, d) ? run + 1 : 1;
    longest = Math.max(longest, run);
    prev = d;
  }
  return { judged: judgedDays.length, good: goodDays.length, longest_run: longest };
}
