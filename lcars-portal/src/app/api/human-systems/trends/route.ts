// Human Systems Workbench — Trends API.
//
// Separate from the main /api/human-systems route deliberately (Captain
// direction, 2026-08-27): the main route feeds "what's happening today"
// views; this one feeds the dedicated /human-systems-workbench/trends
// page — a longer, cross-field look-back, same split the Readiness domain
// already established (readiness/history/page.tsx alongside its own
// today-focused tab).
//
// Sources every field from real, live-checked columns only:
//   - capacity_checkins (checkin_type='capacity'): capacity_state,
//     stimulation_state, pain_state, pain_score, regulation_state,
//     executive_function, compensation_load, emotional_state, social_state
//     — confirmed live 2026-08-27 all reasonably populated (7-13 of the
//     last 16 check-ins) except emotional_state/social_state (7/16,
//     included anyway — still real, just sparser).
//   - analytics_health_daily: energy, nervous_system_state — the same two
//     fields the old Medical-tab sparklines used, moved here rather than
//     duplicated (see MedicalView.tsx's removed Trends section).
//
// sleep_quality, body_signal_clarity, and predictability are deliberately
// NOT included — checked live: 0 of 16 recent rows have any of the three
// populated (sleep_quality's writers are retired; the other two have never
// been written by anything). A sparkline for a field with zero real data
// would misrepresent it as "tracked" rather than "not currently captured."

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const MAX_WINDOW_DAYS = 90;

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export interface TrendDayRow {
  log_date: string;
  energy: string | null;
  nervous_system_state: string | null;
  capacity_state: string | null;
  stimulation_state: string | null;
  pain_state: string | null;
  pain_score: number | null;
  regulation_state: string | null;
  executive_function: string | null;
  compensation_load: string | null;
  emotional_state: string | null;
  social_state: string | null;
}

export async function GET(request: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const since = daysAgo(MAX_WINDOW_DAYS - 1);

    const [{ data: dailyRows, error: dailyErr }, { data: checkinRows, error: checkinErr }] = await Promise.all([
      sb.from('analytics_health_daily')
        .select('log_date,energy,nervous_system_state')
        .gte('log_date', since)
        .order('log_date', { ascending: true }),
      sb.from('capacity_checkins')
        .select('log_date,captured_at,capacity_state,stimulation_state,pain_state,pain_score,regulation_state,executive_function,compensation_load,emotional_state,social_state')
        .eq('checkin_type', 'capacity')
        .gte('log_date', since)
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
    // Last write per log_date wins (ascending captured_at order), same
    // priority rule the main route's own backfill already uses.
    for (const r of (checkinRows ?? []) as any[]) {
      const existing = byDate.get(r.log_date) ?? {
        log_date: r.log_date, energy: null, nervous_system_state: null,
        capacity_state: null, stimulation_state: null, pain_state: null, pain_score: null,
        regulation_state: null, executive_function: null, compensation_load: null,
        emotional_state: null, social_state: null,
      };
      byDate.set(r.log_date, {
        ...existing,
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

    const trends = Array.from(byDate.values()).sort((a, b) => a.log_date.localeCompare(b.log_date));
    return NextResponse.json({ trends, window_days: MAX_WINDOW_DAYS });
  } catch (err) {
    console.error('[human-systems/trends] read failed:', err);
    return NextResponse.json({ error: 'trends_read_failed' }, { status: 500 });
  }
}
