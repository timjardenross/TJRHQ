import { describe, it, expect } from 'vitest';
import { computeSummaryStats, buildSummaryPrompt, type TrendDayRow } from '../route';

// Regression coverage for the 2026-09-06 LLM-summary improvement: the model
// used to be handed only raw per-day lines and asked to count/eyeball state
// changes and "drivers" itself. computeSummaryStats/buildSummaryPrompt now
// do that arithmetic in plain code so the prompt can tell the model to
// treat it as ground truth instead.

function row(overrides: Partial<TrendDayRow> & { log_date: string }): TrendDayRow {
  return {
    energy: null,
    nervous_system_state: null,
    capacity_state: null,
    stimulation_state: null,
    pain_state: null,
    pain_score: null,
    regulation_state: null,
    executive_function: null,
    compensation_load: null,
    emotional_state: null,
    social_state: null,
    ...overrides,
  };
}

describe('computeSummaryStats', () => {
  it('counts capacity states and day-to-day transitions correctly', () => {
    const trends = [
      row({ log_date: '2026-08-01', capacity_state: 'green' }),
      row({ log_date: '2026-08-02', capacity_state: 'green' }),
      row({ log_date: '2026-08-03', capacity_state: 'orange' }),
      row({ log_date: '2026-08-04', capacity_state: 'red' }),
      row({ log_date: '2026-08-05', capacity_state: 'orange' }),
    ];
    const stats = computeSummaryStats(trends);
    expect(stats.capacityCounts).toEqual({ green: 2, orange: 2, red: 1 });
    expect(stats.capacityRecorded).toBe(5);
    // green->green (no change), green->orange, orange->red, red->orange = 3 transitions
    expect(stats.capacityTransitions).toBe(3);
  });

  it('computes pain score average and max from only the recorded values', () => {
    const trends = [
      row({ log_date: '2026-08-01', pain_score: 2 }),
      row({ log_date: '2026-08-02' }),
      row({ log_date: '2026-08-03', pain_score: 8 }),
    ];
    const stats = computeSummaryStats(trends);
    expect(stats.painValues).toEqual([2, 8]);
  });

  it('excludes a field from candidate drivers when it is below the coverage threshold', () => {
    // social_state has only 2 recorded days (below MIN_DRIVER_COVERAGE=5)
    // even though both are concerning — it must not be surfaced as a driver.
    const trends = [
      row({ log_date: '2026-08-01', social_state: 'none' }),
      row({ log_date: '2026-08-02', social_state: 'none' }),
    ];
    const stats = computeSummaryStats(trends);
    expect(stats.drivers.find((d) => d.label === 'social resource')).toBeUndefined();
  });

  it('surfaces a field as a candidate driver once it has enough recorded days and any concerning values', () => {
    const trends = [
      row({ log_date: '2026-08-01', regulation_state: 'overloaded' }),
      row({ log_date: '2026-08-02', regulation_state: 'overloaded' }),
      row({ log_date: '2026-08-03', regulation_state: 'settled' }),
      row({ log_date: '2026-08-04', regulation_state: 'settled' }),
      row({ log_date: '2026-08-05', regulation_state: 'settled' }),
    ];
    const stats = computeSummaryStats(trends);
    const driver = stats.drivers.find((d) => d.label === 'regulation');
    expect(driver).toBeDefined();
    expect(driver).toMatchObject({ coverage: 5, concerningCount: 2 });
  });

  it('never lists a field with zero concerning days as a driver', () => {
    const trends = Array.from({ length: 6 }, (_, i) =>
      row({ log_date: `2026-08-0${i + 1}`, nervous_system_state: 'calm' })
    );
    const stats = computeSummaryStats(trends);
    expect(stats.drivers).toHaveLength(0);
  });
});

describe('buildSummaryPrompt', () => {
  it('includes a computed-statistics block ahead of the raw daily log', () => {
    const trends = [
      row({ log_date: '2026-08-01', capacity_state: 'green', pain_score: 3 }),
      row({ log_date: '2026-08-02', capacity_state: 'red', pain_score: 8 }),
    ];
    const prompt = buildSummaryPrompt(trends);
    const statsIndex = prompt.indexOf('Computed statistics');
    const rawIndex = prompt.indexOf('Raw daily log');
    expect(statsIndex).toBeGreaterThanOrEqual(0);
    expect(rawIndex).toBeGreaterThan(statsIndex);
    expect(prompt).toContain('green=1, orange=0, red=1');
    expect(prompt).toContain('max 8');
  });

  it('tells the model no field qualifies as a driver when none clears the coverage bar', () => {
    const trends = [row({ log_date: '2026-08-01', social_state: 'none' })];
    const prompt = buildSummaryPrompt(trends);
    expect(prompt).toContain('Candidate drivers: none');
  });
});
