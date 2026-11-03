import { describe, it, expect } from 'vitest';
import { buildDayPlan, dayReasons, ZONE_PROMPT } from '../day-plan';

// Wording mirrors telegram-bots/capacitybot/day_plan.py (tests in test_day_plan.py).

describe('dayReasons', () => {
  it('draws on the whole check-in, not just the zone', () => {
    const reasons = dayReasons({
      pain_state: 'elevated', executive_function: 'strained', compensation_load: 'high',
      regulation_state: 'activated', stimulation_state: 'high',
    });
    expect(reasons).toHaveLength(5);
    expect(reasons).toContain('pain is above your usual');
  });

  it('never lists a missing or fine answer as a problem', () => {
    expect(dayReasons({ pain_state: 'baseline', executive_function: 'good' })).toEqual([]);
    expect(dayReasons({})).toEqual([]);
  });
});

describe('buildDayPlan', () => {
  it('has a prompt per zone, including the orange early-intervention question', () => {
    for (const zone of ['green', 'orange', 'red']) {
      expect(buildDayPlan({ capacity_state: zone })?.prompt).toBe(ZONE_PROMPT[zone]);
    }
    expect(ZONE_PROMPT.orange).toContain('reduce, regulate or change before this becomes red');
    expect(ZONE_PROMPT.green).toContain('Spend some, bank some');
    expect(ZONE_PROMPT.red).toContain('smallest workable day');
  });

  it('is null without a capacity answer', () => {
    expect(buildDayPlan({ capacity_state: null })).toBeNull();
    expect(buildDayPlan({ capacity_state: 'purple' })).toBeNull();
  });

  it('never uses gate or pressure wording', () => {
    for (const zone of ['green', 'orange', 'red']) {
      const plan = buildDayPlan({ capacity_state: zone, pain_state: 'high', executive_function: 'very_difficult' })!;
      const text = [plan.headline, plan.prompt, ...plan.reasons].join(' ').toLowerCase();
      for (const word of ['should', 'must', 'deferred', 'blocked', 'limit', 'not allowed', 'you need to']) {
        expect(text).not.toContain(word);
      }
    }
  });
});
