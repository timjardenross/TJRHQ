// TypeScript mirror of the wording in telegram-bots/capacitybot/day_plan.py (the day plan): the zone
// with plain reasons from the whole check-in, and one prompt per zone. Suggestions are NOT mirrored:
// the bot ranks them with the Captain's personal outcome history, which the portal doesn't replicate,
// so the portal points to Telegram for those. Keep the reasons and prompts in step with the Python
// file; __tests__/day-plan.test.ts pins the wording.
//
// Suggestions only: a capacity reading never defers, limits or blocks anything (owner decision
// 2026-11-02). No diagnosis, no shame, no "should".

export const ZONE_HEADLINE: Record<string, string> = {
  green: 'Sustainable',
  orange: 'Stretched',
  red: 'Depleted',
};

export const ZONE_PROMPT: Record<string, string> = {
  green: "You have room today. Spend some, bank some: capacity left over doesn't have to be used.",
  orange: 'What could you reduce, regulate or change before this becomes red?',
  red: 'Today can be the smallest workable day. Nothing else is held back; this is just the gentlest option.',
};

const PAIN: Record<string, string> = { elevated: 'pain is above your usual', high: 'pain is much higher than usual' };
const EF: Record<string, string> = {
  strained: 'thinking and deciding is taking more effort',
  difficult: 'thinking and deciding is difficult',
  very_difficult: 'thinking and deciding is very difficult',
};
const COMP: Record<string, string> = { high: "you're pushing or masking a lot", extreme: "you're forcing yourself through" };
const REG: Record<string, string> = { activated: 'your system feels activated', overloaded: 'your system feels overloaded' };
const STIM: Record<string, string> = { high: 'stimulation is too high', low: 'stimulation is too low' };

export interface DayPlanInput {
  capacity_state: string | null;
  pain_state?: string | null;
  executive_function?: string | null;
  compensation_load?: string | null;
  regulation_state?: string | null;
  stimulation_state?: string | null;
}

/** Plain-language reasons from the whole check-in. Only answered, notable things are listed; a missing
 *  answer is never treated as a problem. */
export function dayReasons(row: Omit<DayPlanInput, 'capacity_state'>): string[] {
  const pick = (table: Record<string, string>, v: string | null | undefined) => (v ? table[v] : undefined);
  return [
    pick(PAIN, row.pain_state),
    pick(EF, row.executive_function),
    pick(COMP, row.compensation_load),
    pick(REG, row.regulation_state),
    pick(STIM, row.stimulation_state),
  ].filter((r): r is string => !!r);
}

export interface DayPlan {
  zone: string;
  headline: string;
  reasons: string[];
  prompt: string;
}

/** The plan, or null when there's no capacity answer to build it on. */
export function buildDayPlan(row: DayPlanInput): DayPlan | null {
  const zone = row.capacity_state;
  if (!zone || !(zone in ZONE_HEADLINE)) return null;
  return { zone, headline: ZONE_HEADLINE[zone], reasons: dayReasons(row), prompt: ZONE_PROMPT[zone] };
}
