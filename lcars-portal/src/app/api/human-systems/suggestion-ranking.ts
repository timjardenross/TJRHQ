// TypeScript port of the capacity bot's suggestion ranking (telegram-bots/capacitybot/intervention_engine.py:
// _score and rank_interventions), so the portal's day plan can show the same top three suggestions as
// Telegram. Pure functions: the route reads the three tables and passes the rows in.
//
// Keep in step with the Python. ../../../../../core/health/shared_cases/capacity_cases.json holds example
// days read by both languages' tests; __tests__/shared-cases.test.ts runs them here.
//
// Suggestions only. A capacity reading never defers, limits or blocks anything (owner decision
// 2026-11-02), and the zone no longer changes how hard an option scores (2026-11-03).

export interface Intervention {
  intervention_id: string;
  title?: string | null;
  button_label?: string | null;
  management_lever?: string | null;
  target_states?: string[] | null;
  capacity_allowed?: string[] | null;
  stimulation_effect?: string | null;
  pain_compatible?: boolean | null;
  executive_effort?: string | null;
  estimated_minutes?: number | null;
}

export interface RankContext {
  help_state?: string | null;
  capacity_state?: string | null;
  stimulation_state?: string | null;
  pain_state?: string | null;
  executive_function?: string | null;
  max_minutes?: number | null;
}

export interface InterventionEvent {
  intervention_id: string;
  outcome: string | null;
  started_at?: string | null;
}

export type Preferences = Record<string, string>;

/** Below this many completed attempts, personal-outcome weighting is skipped. */
export const MIN_SAMPLE_FOR_WEIGHTING = 3;
const OUTCOME_WEIGHT: Record<string, number> = { better: 1, same: 0, worse: -1 };

/** Score for one candidate, or null when it must be excluded outright (pain-incompatible while pain is up). */
export function scoreIntervention(row: Intervention, ctx: RankContext, outcomes?: string[] | null): number | null {
  let score = 0;

  const targets = row.target_states ?? [];
  if (ctx.help_state) score += targets.includes(ctx.help_state) ? 10 : 0;
  else score += 5;

  const stim = row.stimulation_effect;
  const st = ctx.stimulation_state;
  if (st != null) {
    if ((st === 'low' && stim === 'increase') || (st === 'high' && stim === 'decrease')) score += 3;
    else if (stim === 'neutral') score += 1;
    else if ((st === 'low' && stim === 'decrease') || (st === 'high' && stim === 'increase')) score -= 3;
  }

  const painUp = ctx.pain_state === 'elevated' || ctx.pain_state === 'high';
  const painCompatible = row.pain_compatible === undefined ? true : row.pain_compatible; // null counts as not compatible, like the bot
  if (painUp && !painCompatible) return null;
  if (painUp && row.pain_compatible) score += 1;

  if (ctx.executive_function === 'very_difficult' && ['moderate', 'high'].includes(row.executive_effort ?? 'low')) {
    score -= 3;
  }

  if (outcomes && outcomes.length > 0) {
    const completed = outcomes.filter((o) => o in OUTCOME_WEIGHT);
    if (completed.length >= MIN_SAMPLE_FOR_WEIGHTING) {
      score += completed.reduce((sum, o) => sum + OUTCOME_WEIGHT[o], 0) * 2;
    }
    if (completed[0] === 'worse' && completed[1] === 'worse') score -= 4;
  }
  return score;
}

/** Up to `limit` suggestions, best first. `events` may be in any order; outcomes are taken most recent
 *  first. Mirrors the bot: the capacity-zone filter, max-minutes, do_not_suggest excluded before scoring,
 *  then 'preferred' moved ahead of everything else without changing the scores. */
export function rankInterventions(
  candidates: Intervention[],
  ctx: RankContext,
  events: InterventionEvent[],
  preferences: Preferences,
  limit = 3,
): Intervention[] {
  let pool = candidates;
  if (ctx.capacity_state) {
    pool = pool.filter((c) => (c.capacity_allowed ?? []).includes(ctx.capacity_state as string));
  }
  if (ctx.max_minutes != null) {
    const max = ctx.max_minutes;
    pool = pool.filter((c) => c.estimated_minutes == null || c.estimated_minutes <= max);
  }
  pool = pool.filter((c) => preferences[c.intervention_id] !== 'do_not_suggest');

  const byId = new Map<string, string[]>();
  [...events]
    .filter((e) => e.outcome)
    .sort((a, b) => String(b.started_at ?? '').localeCompare(String(a.started_at ?? '')))
    .forEach((e) => {
      byId.set(e.intervention_id, [...(byId.get(e.intervention_id) ?? []), e.outcome as string]);
    });

  const scored: { score: number; row: Intervention }[] = [];
  for (const row of pool) {
    const s = scoreIntervention(row, ctx, byId.get(row.intervention_id));
    if (s !== null) scored.push({ score: s, row });
  }
  scored.sort((a, b) => b.score - a.score); // stable
  scored.sort((a, b) => (preferences[a.row.intervention_id] === 'preferred' ? 0 : 1) - (preferences[b.row.intervention_id] === 'preferred' ? 0 : 1));
  return scored.slice(0, limit).map((s) => s.row);
}

const LEVER_LABEL: Record<string, string> = {
  reduce_load: 'Reduce', regulate: 'Regulate', recover: 'Recover', redesign: 'Redesign',
};

/** One line per suggestion, e.g. "Short walk (Regulate, 10 min)". Mirrors day_plan.py. */
export function suggestionLine(index: number, i: Intervention): string {
  const title = i.title || i.button_label || 'Suggestion';
  const lever = LEVER_LABEL[i.management_lever ?? ''];
  const tags = [lever, i.estimated_minutes ? `${i.estimated_minutes} min` : undefined].filter(Boolean);
  return `${index}. ${title}${tags.length ? ` (${tags.join(', ')})` : ''}`;
}
