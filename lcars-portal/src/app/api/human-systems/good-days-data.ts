// Builds the /api/human-systems/good-days payload from raw capacity_checkins rows. Pure, so it can be
// tested without a database (route.ts can only export handlers).

import { latestEveningByDate, provisionalGoodDay, summarizeGoodDays, type EveningRow, type GoodDaySummary } from './good-day';

export interface CapacityRow {
  log_date: string;
  captured_at?: string | null;
  capacity_state?: string | null;
}

export interface GoodDaysDay {
  date: string;
  /** 'green' | 'orange' | 'red' from the last quick check-in of the day, or null */
  zone: string | null;
  /** true good, false not good, null unknown (no evening answer, or nothing to judge) */
  verdict: boolean | null;
}

export interface GoodDaysPayload {
  window_days: number;
  summary: GoodDaySummary;
  days: GoodDaysDay[];
  /** the most recent evening in the window, for showing the whole-day answers */
  latest_evening: {
    log_date: string;
    day_trajectory: string | null;
    day_compensation_load: string | null;
    good_day: string | null;
  } | null;
}

/** The `windowDays` calendar dates ending on `today` (YYYY-MM-DD), oldest first. */
export function windowDates(today: string, windowDays: number): string[] {
  const end = Date.parse(`${today}T00:00:00Z`);
  return Array.from({ length: windowDays }, (_, i) =>
    new Date(end - (windowDays - 1 - i) * 86_400_000).toISOString().slice(0, 10),
  );
}

export function buildGoodDaysPayload(
  eveningRows: EveningRow[],
  capacityRows: CapacityRow[],
  today: string,
  windowDays = 14,
): GoodDaysPayload {
  const dates = windowDates(today, windowDays);
  const inWindow = new Set(dates);
  const evenings = eveningRows.filter((r) => inWindow.has(String(r.log_date).slice(0, 10)));
  const byDate = latestEveningByDate(evenings);

  const zoneByDate = new Map<string, { at: string; zone: string }>();
  for (const r of capacityRows) {
    const day = String(r.log_date ?? '').slice(0, 10);
    if (!inWindow.has(day) || !r.capacity_state) continue;
    const at = String(r.captured_at ?? '');
    const prev = zoneByDate.get(day);
    if (!prev || at >= prev.at) zoneByDate.set(day, { at, zone: r.capacity_state });
  }

  const days: GoodDaysDay[] = dates.map((date) => ({
    date,
    zone: zoneByDate.get(date)?.zone ?? null,
    verdict: byDate.has(date) ? provisionalGoodDay(byDate.get(date)) : null,
  }));

  const lastDate = [...byDate.keys()].sort().pop();
  const last = lastDate ? byDate.get(lastDate)! : null;
  return {
    window_days: windowDays,
    summary: summarizeGoodDays(evenings),
    days,
    latest_evening: last
      ? {
          log_date: String(last.log_date).slice(0, 10),
          day_trajectory: last.day_trajectory ?? null,
          day_compensation_load: last.day_compensation_load ?? null,
          good_day: last.good_day ?? null,
        }
      : null,
  };
}
