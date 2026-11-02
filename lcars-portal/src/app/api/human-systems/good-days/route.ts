// Human Systems — good days (last 14 days): the count, the longest run, a per-day timeline and the
// latest evening's whole-day answers. Read-only. Pure logic is in ../good-days-data.ts (a route file
// can only export handlers).

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { todayLocal } from '@/lib/timezone';
import { buildGoodDaysPayload, windowDates } from '../good-days-data';

const WINDOW_DAYS = 14;

export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const sb = await createSupabaseServerClient();
    const today = todayLocal();
    const since = windowDates(today, WINDOW_DAYS)[0];

    const [evening, capacity] = await Promise.all([
      sb.from('capacity_checkins')
        .select('log_date,captured_at,day_trajectory,day_compensation_load,good_day')
        .eq('checkin_type', 'evening')
        .gte('log_date', since)
        .lte('log_date', today)
        .order('captured_at', { ascending: true }),
      sb.from('capacity_checkins')
        .select('log_date,captured_at,capacity_state')
        .eq('checkin_type', 'capacity')
        .gte('log_date', since)
        .lte('log_date', today)
        .order('captured_at', { ascending: true }),
    ]);
    if (evening.error) throw evening.error;
    if (capacity.error) throw capacity.error;

    return NextResponse.json(
      buildGoodDaysPayload(evening.data ?? [], capacity.data ?? [], today, WINDOW_DAYS),
      { headers: { 'Cache-Control': 'no-store' } },
    );
  } catch (err) {
    console.error('[human-systems/good-days] read failed:', err);
    return NextResponse.json({ error: 'good_days_read_failed' }, { status: 500 });
  }
}
