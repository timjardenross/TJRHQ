// Human Systems Workbench — shared trend-row fetch/merge.
//
// Extracted out of route.ts (2026-09-07) so the Report route (14-day
// clinician-facing summary) can read the exact same merged rows the Trends
// page's own history reads, instead of a second hand-copied version of this
// merge that could silently drift from it. Behavior is unchanged from what
// route.ts's GET handler did inline — see that file's still-current
// docstring for which columns/tables this reads and why.

import type { SupabaseClient } from '@supabase/supabase-js';
import type { TrendDayRow } from './summary';

// analytics_health_daily.energy is COALESCE(captains_log_entries.energy,
// health_daily_logs.energy) (migration 0017) — both writers are already
// retired (Captain's Log 2026-08-10; health_daily_logs replaced by
// capacity_checkins the same day). Backfill from capacity_checkins.
// capacity_state — the live signal, same mapping the main /api/human-systems
// route's energyFromCapacityState() already uses.
export function energyFromCapacityState(state: string | null): string | null {
  return ({ green: 'High', orange: 'Moderate', red: 'Low' } as Record<string, string>)[state ?? ''] ?? null;
}

/** log_date rows from analytics_health_daily + capacity_checkins, merged
 *  and sorted ascending by log_date — same "last write per log_date wins"
 *  rule for the capacity_checkins side (rows arrive in ascending
 *  captured_at order). `since`/`until` are inclusive 'YYYY-MM-DD' bounds. */
export async function fetchTrendRows(
  sb: SupabaseClient,
  since: string,
  until: string
): Promise<TrendDayRow[]> {
  const [{ data: dailyRows, error: dailyErr }, { data: checkinRows, error: checkinErr }] = await Promise.all([
    sb.from('analytics_health_daily')
      .select('log_date,energy,nervous_system_state')
      .gte('log_date', since)
      .lte('log_date', until)
      .order('log_date', { ascending: true }),
    sb.from('capacity_checkins')
      .select('log_date,captured_at,capacity_state,stimulation_state,pain_state,pain_score,regulation_state,executive_function,compensation_load,emotional_state,social_state')
      .eq('checkin_type', 'capacity')
      .gte('log_date', since)
      .lte('log_date', until)
      .order('captured_at', { ascending: true }),
  ]);
  if (dailyErr) throw dailyErr;
  if (checkinErr) throw checkinErr;

  const byDate = new Map<string, TrendDayRow>();
  for (const r of (dailyRows ?? []) as any[]) {
    byDate.set(r.log_date, {
      log_date: r.log_date,
      energy: r.energy ?? null,
      nervous_system_state: r.nervous_system_state ?? null,
      capacity_state: null, stimulation_state: null, pain_state: null, pain_score: null,
      regulation_state: null, executive_function: null, compensation_load: null,
      emotional_state: null, social_state: null,
    });
  }
  for (const r of (checkinRows ?? []) as any[]) {
    const existing = byDate.get(r.log_date) ?? {
      log_date: r.log_date, energy: null, nervous_system_state: null,
      capacity_state: null, stimulation_state: null, pain_state: null, pain_score: null,
      regulation_state: null, executive_function: null, compensation_load: null,
      emotional_state: null, social_state: null,
    };
    byDate.set(r.log_date, {
      ...existing,
      energy: existing.energy ?? energyFromCapacityState(r.capacity_state),
      capacity_state: r.capacity_state ?? existing.capacity_state,
      stimulation_state: r.stimulation_state ?? existing.stimulation_state,
      pain_state: r.pain_state ?? existing.pain_state,
      pain_score: r.pain_score ?? existing.pain_score,
      regulation_state: r.regulation_state ?? existing.regulation_state,
      executive_function: r.executive_function ?? existing.executive_function,
      compensation_load: r.compensation_load ?? existing.compensation_load,
      emotional_state: r.emotional_state ?? existing.emotional_state,
      social_state: r.social_state ?? existing.social_state,
    });
  }

  return Array.from(byDate.values()).sort((a, b) => a.log_date.localeCompare(b.log_date));
}
