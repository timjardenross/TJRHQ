import { describe, it, expect } from 'vitest';
import { buildGoodDaysPayload, windowDates } from '../good-days-data';

describe('windowDates', () => {
  it('gives consecutive dates ending today, oldest first, across a month end', () => {
    expect(windowDates('2026-11-02', 4)).toEqual(['2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02']);
  });
});

describe('buildGoodDaysPayload', () => {
  const today = '2026-11-05';
  const evening = (d: string, extra = {}) => ({ log_date: d, captured_at: `${d}T20:00:00`, ...extra });

  it('builds one entry per day with the zone and the verdict, unknown where no evening', () => {
    const payload = buildGoodDaysPayload(
      [evening('2026-11-03', { day_trajectory: 'same', day_compensation_load: 'low' }), evening('2026-11-04', { day_trajectory: 'declined' })],
      [
        { log_date: '2026-11-03', captured_at: '2026-11-03T08:00:00', capacity_state: 'green' },
        { log_date: '2026-11-03', captured_at: '2026-11-03T13:00:00', capacity_state: 'orange' },
        { log_date: '2026-11-05', captured_at: '2026-11-05T08:00:00', capacity_state: 'red' },
      ],
      today,
      5,
    );
    expect(payload.days.map((d) => d.date)).toEqual(['2026-11-01', '2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05']);
    const by = Object.fromEntries(payload.days.map((d) => [d.date, d]));
    expect(by['2026-11-03']).toMatchObject({ zone: 'orange', verdict: true }); // last zone of the day wins
    expect(by['2026-11-04']).toMatchObject({ zone: null, verdict: false });
    expect(by['2026-11-05']).toMatchObject({ zone: 'red', verdict: null }); // no evening yet: unknown
    expect(by['2026-11-02']).toMatchObject({ zone: null, verdict: null });
    expect(payload.summary).toEqual({ judged: 2, good: 1, longest_run: 1 });
  });

  it('ignores rows outside the window and reports the latest evening', () => {
    const payload = buildGoodDaysPayload(
      [evening('2026-10-01', { day_trajectory: 'same' }), evening('2026-11-04', { day_trajectory: 'same', good_day: 'kind_of', day_compensation_load: 'moderate' })],
      [],
      today,
      5,
    );
    expect(payload.summary.judged).toBe(1);
    expect(payload.latest_evening).toEqual({
      log_date: '2026-11-04', day_trajectory: 'same', day_compensation_load: 'moderate', good_day: 'kind_of',
    });
  });

  it('is empty and calm with no data', () => {
    const payload = buildGoodDaysPayload([], [], today, 3);
    expect(payload.summary).toEqual({ judged: 0, good: 0, longest_run: 0 });
    expect(payload.latest_evening).toBeNull();
    expect(payload.days.every((d) => d.verdict === null && d.zone === null)).toBe(true);
  });
});
