import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { provisionalGoodDay } from '../good-day';
import { dayReasons } from '../day-plan';
import { rankInterventions } from '../suggestion-ranking';

// Drift guard: these example days are also read by telegram-bots/capacitybot/test_shared_cases.py. If a
// case fails here and passes there (or the reverse), the two implementations have drifted apart.
const FILE = resolve(__dirname, '../../../../../../core/health/shared_cases/capacity_cases.json');
type Case = Record<string, any>;
const CASES = JSON.parse(readFileSync(FILE, 'utf8')) as Record<string, Case[]>;

describe('shared cases (Python and TypeScript must agree)', () => {
  it.each(CASES.good_day as Case[])('good day: $name', (c: Case) => {
    expect(provisionalGoodDay(c.input)).toBe(c.expected);
  });
  it.each(CASES.day_reasons as Case[])('day reasons: $name', (c: Case) => {
    expect(dayReasons(c.input)).toEqual(c.expected);
  });
  it.each(CASES.ranking as Case[])('ranking: $name', (c: Case) => {
    const ranked = rankInterventions(c.candidates, c.context, c.events, c.preferences, c.limit);
    expect(ranked.map((r) => r.intervention_id)).toEqual(c.expected_ids);
  });
});
