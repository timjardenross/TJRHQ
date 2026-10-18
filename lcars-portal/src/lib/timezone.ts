/**
 * The platform's local time zone. Melbourne, daylight-saving aware (changed from
 * Brisbane, fixed UTC+10, on the owner's direction). Use these helpers instead of
 * hard-coding a zone name or a UTC offset such as "+10:00".
 */
export const LOCAL_TIMEZONE = 'Australia/Melbourne';

/** Calendar date (YYYY-MM-DD) in the local zone for the given instant. */
export function todayLocal(now: Date = new Date()): string {
  return now.toLocaleDateString('en-CA', { timeZone: LOCAL_TIMEZONE });
}

/** Offset of the local zone from UTC, in minutes, at the given instant (e.g. 660 in AEDT). */
function offsetMinutesAt(instant: Date): number {
  const part = new Intl.DateTimeFormat('en-US', {
    timeZone: LOCAL_TIMEZONE,
    timeZoneName: 'longOffset',
  })
    .formatToParts(instant)
    .find((p) => p.type === 'timeZoneName')?.value;
  const m = part?.match(/GMT([+-])(\d{2}):(\d{2})/);
  if (!m) return 0; // "GMT" alone means UTC+0
  const minutes = Number(m[2]) * 60 + Number(m[3]);
  return m[1] === '-' ? -minutes : minutes;
}

/**
 * The UTC instant at which the local clock reads `dateStr` (YYYY-MM-DD) at hh:mm:ss.
 * Correct across daylight-saving changes (the offset is taken at the local time,
 * not at the date's noon).
 */
export function localTimeToDate(dateStr: string, hh = 0, mm = 0, ss = 0): Date {
  const [y, mo, d] = dateStr.split('-').map(Number);
  const wallAsUtc = Date.UTC(y, mo - 1, d, hh, mm, ss);
  const first = offsetMinutesAt(new Date(wallAsUtc));
  let ts = wallAsUtc - first * 60_000;
  const second = offsetMinutesAt(new Date(ts));
  if (second !== first) ts = wallAsUtc - second * 60_000;
  return new Date(ts);
}

export function startOfLocalDay(dateStr: string): Date {
  return localTimeToDate(dateStr, 0, 0, 0);
}

export function endOfLocalDay(dateStr: string): Date {
  return localTimeToDate(dateStr, 23, 59, 59);
}
