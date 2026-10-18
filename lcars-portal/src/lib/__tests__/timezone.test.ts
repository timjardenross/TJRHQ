import { describe, expect, it } from 'vitest';
import { LOCAL_TIMEZONE, endOfLocalDay, localTimeToDate, startOfLocalDay, todayLocal } from '../timezone';

describe('timezone helpers (Australia/Melbourne)', () => {
  it('uses Melbourne', () => {
    expect(LOCAL_TIMEZONE).toBe('Australia/Melbourne');
  });

  it('rolls the local date over at Melbourne midnight, not Brisbane midnight', () => {
    // 2026-10-17 13:30 UTC = 00:30 on 18 Oct in Melbourne (AEDT, UTC+11) but 23:30 on 17 Oct in Brisbane (UTC+10).
    expect(todayLocal(new Date('2026-10-17T13:30:00Z'))).toBe('2026-10-18');
  });

  it('start of day uses +11:00 in daylight saving', () => {
    expect(startOfLocalDay('2026-10-18').toISOString()).toBe('2026-10-17T13:00:00.000Z');
    expect(endOfLocalDay('2026-10-18').toISOString()).toBe('2026-10-18T12:59:59.000Z');
  });

  it('start of day uses +10:00 outside daylight saving', () => {
    expect(startOfLocalDay('2026-07-09').toISOString()).toBe('2026-07-08T14:00:00.000Z');
  });

  it('is correct on the day daylight saving starts (Sun 4 Oct 2026, 02:00 -> 03:00)', () => {
    // Midnight is still AEST (+10); the offset changes at 02:00.
    expect(startOfLocalDay('2026-10-04').toISOString()).toBe('2026-10-03T14:00:00.000Z');
    // 12:00 is AEDT (+11).
    expect(localTimeToDate('2026-10-04', 12).toISOString()).toBe('2026-10-04T01:00:00.000Z');
  });

  it('is correct on the day daylight saving ends (Sun 5 Apr 2026, 03:00 -> 02:00)', () => {
    expect(startOfLocalDay('2026-04-05').toISOString()).toBe('2026-04-04T13:00:00.000Z');
    expect(localTimeToDate('2026-04-05', 12).toISOString()).toBe('2026-04-05T02:00:00.000Z');
  });
});
