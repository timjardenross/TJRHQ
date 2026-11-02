import { describe, it, expect } from 'vitest';
import { provisionalGoodDay, summarizeGoodDays, type EveningRow } from '../good-day';

// Same scenarios as telegram-bots/capacitybot/test_evening_checkin.py (the Python rule); if one changes,
// both should change.

describe('provisionalGoodDay', () => {
  it('judges only what was answered', () => {
    expect(provisionalGoodDay({ day_trajectory: 'same', day_compensation_load: 'moderate' })).toBe(true);
    expect(provisionalGoodDay({ day_trajectory: 'same' })).toBe(true); // missing compensation is not bad
    expect(provisionalGoodDay({ day_trajectory: 'declined' })).toBe(false);
    expect(provisionalGoodDay({ day_trajectory: 'same', day_compensation_load: 'extreme' })).toBe(false);
    expect(provisionalGoodDay({})).toBeNull();
    expect(provisionalGoodDay(null)).toBeNull();
  });

  it("the Captain's own answer wins, and 'kind of' falls through to the rule", () => {
    expect(provisionalGoodDay({ day_trajectory: 'declined', day_compensation_load: 'extreme', good_day: 'yes' })).toBe(true);
    expect(provisionalGoodDay({ day_trajectory: 'same', day_compensation_load: 'low', good_day: 'no' })).toBe(false);
    expect(provisionalGoodDay({ day_trajectory: 'same', day_compensation_load: 'low', good_day: 'kind_of' })).toBe(true);
  });

  it('ignores borrowed capacity entirely', () => {
    for (const debt of ['no', 'maybe', 'yes', null]) {
      const row = { day_trajectory: 'same', day_compensation_load: 'moderate', capacity_debt: debt } as Partial<EveningRow>;
      expect(provisionalGoodDay(row)).toBe(true);
    }
  });
});

const evening = (d: string, extra: Partial<EveningRow> = {}): EveningRow => ({
  log_date: d, captured_at: `${d}T20:00:00`, ...extra,
});
const GOOD = { day_trajectory: 'same', day_compensation_load: 'low' };
const BAD = { day_trajectory: 'declined' };

describe('summarizeGoodDays', () => {
  it('counts good days and the longest consecutive run', () => {
    const rows = [
      evening('2026-11-01', GOOD), evening('2026-11-02', GOOD), evening('2026-11-03', GOOD),
      evening('2026-11-04', BAD), evening('2026-11-05', GOOD),
    ];
    expect(summarizeGoodDays(rows)).toEqual({ judged: 5, good: 4, longest_run: 3 });
  });

  it('a day with no evening ends a run and is not counted', () => {
    expect(summarizeGoodDays([evening('2026-11-01', GOOD), evening('2026-11-03', GOOD)]))
      .toEqual({ judged: 2, good: 2, longest_run: 1 });
  });

  it('uses the latest evening of a day and ignores days with nothing answered', () => {
    const rows = [
      evening('2026-11-01', BAD),
      { ...evening('2026-11-01', GOOD), captured_at: '2026-11-01T22:00:00' },
      evening('2026-11-03'),
    ];
    expect(summarizeGoodDays(rows)).toEqual({ judged: 1, good: 1, longest_run: 1 });
    expect(summarizeGoodDays([])).toEqual({ judged: 0, good: 0, longest_run: 0 });
  });
});
