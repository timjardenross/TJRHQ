import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

/**
 * Resolve a capacity check-in's nervous-system state — the same mapping as
 * the canonical `checkinNsState()` in lib/human-systems.ts, re-declared here
 * because that module pulls in supabase-browser.ts, a 'use client' file,
 * which this server Route Handler shouldn't depend on. Every consumer of
 * capacity_checkins data in this codebase must apply this same mapping or
 * they'll disagree on a given check-in's nervous-system reading.
 */
function checkinNsState(checkin: { regulation_state?: string | null }): string | null {
  const regulation = checkin.regulation_state ?? null;
  if (!regulation) return null;
  return ({
    settled: 'calm',
    manageable: 'calm',
    activated: 'activated',
    overloaded: 'dysregulated',
  } as Record<string, string>)[regulation] ?? null;
}

/**
 * Energy proxy derived from capacity_state, for backward-compat with the
 * `daily.energy` field this merges into (consumers of this route still
 * expect an `energy` reading). capacity_checkins has no direct energy
 * measure — green/orange/red is the closest analogue.
 */
function capacityEnergy(checkin: { capacity_state?: string | null }): string | null {
  const state = checkin.capacity_state ?? null;
  if (!state) return null;
  return ({ green: 'high', orange: 'moderate', red: 'low' } as Record<string, string>)[state] ?? null;
}

function getSupabase() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const supabase = getSupabase();
    const today = new Date().toISOString().slice(0, 10);

    const [insightsRes, dailyRes, checkinRes] = await Promise.all([
      supabase
        // health_insights has no insight_date column (WORKBENCH-REVIEW.md
        // H7, 2026-07-18) - this select 400'd every call, silently returning
        // null insights to the 2 real live callers (WellnessInsightPanel on
        // /medical and /recovery-brief). created_at is the real recency
        // column, confirmed against the live schema and against
        // api/human-systems/route.ts's own already-correct query.
        .from('health_insights')
        .select('created_at,llm_narrative,risk_flags,positive_flags,wins_this_week,cpap_compliance_rate,dow_pain_pattern')
        .order('created_at', { ascending: false })
        .limit(1),
      supabase
        .from('health_daily_logs')
        .select('log_date,sleep_hours,sleep_quality,cpap_compliant,nervous_system_state,sitting_tolerance_minutes,mood,energy')
        .order('log_date', { ascending: false })
        .limit(1),
      supabase
        .from('capacity_checkins')
        // capacity_state/regulation_state are the canonical Telegram-bot
        // "MY CAPACITY TODAY" fields (recovery_pulses is retired). Quick
        // check-in rows only — checkin_type also covers 'evening' rows,
        // which this route doesn't merge into the daily snapshot.
        .select('log_date,captured_at,capacity_state,regulation_state,pain_score,notes,trigger_note')
        .eq('checkin_type', 'capacity')
        .eq('log_date', today)
        .order('captured_at', { ascending: false })
        .limit(1),
    ]);

    const insights      = insightsRes.data?.[0] ?? null;
    const dailyLog      = dailyRes.data?.[0] ?? null;
    const latestCheckin = checkinRes.data?.[0] ?? null;

    // Merge: check-in wins on energy when present (more current than daily log)
    // If no daily log at all for today, synthesise one from the check-in.
    // nervous_system_state derives from the check-in's `regulation_state`
    // via checkinNsState() (the mapping canonical in lib/human-systems.ts,
    // re-declared locally above) — same rule ros-data.ts and
    // human-systems.ts already apply. No mood equivalent exists on
    // capacity_checkins, so mood is left untouched here.
    let daily = dailyLog;
    if (latestCheckin) {
      if (!daily || daily.log_date !== today) {
        // No log today — build a synthetic row from the check-in
        daily = {
          log_date: today,
          sleep_hours: null,
          sleep_quality: null,
          cpap_compliant: null,
          sitting_tolerance_minutes: null,
          energy: capacityEnergy(latestCheckin),
          mood: null,
          nervous_system_state: checkinNsState(latestCheckin),
        };
      } else {
        // Log exists but check-in has fresher readings — override energy/NS
        daily = {
          ...daily,
          energy: capacityEnergy(latestCheckin) ?? daily.energy,
          nervous_system_state: checkinNsState(latestCheckin) ?? daily.nervous_system_state,
        };
      }
    }

    // `checkin` now holds a capacity_checkins row (was `pulse`, a
    // recovery_pulses row, before the migration off that retired table).
    // No known consumer destructures the old `pulse` key (checked
    // recovery-brief/page.tsx and WellnessInsightPanel.tsx — both only read
    // `insights`/`daily`), so the rename is safe.
    return NextResponse.json({ insights, daily, checkin: latestCheckin });
  } catch (err) {
    return NextResponse.json({ insights: null, daily: null, error: String(err) }, { status: 500 });
  }
}
