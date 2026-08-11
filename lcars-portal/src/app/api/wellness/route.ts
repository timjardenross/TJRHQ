import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

/**
 * Resolve a pulse's nervous-system state (MSN-0355 rule, mirrored here
 * rather than imported from lib/human-systems.ts because that module pulls
 * in supabase-browser.ts, a 'use client' file, which this server Route
 * Handler shouldn't depend on). Prefers the directly captured
 * `nervous_system` reading (the canonical Telegram-bot field) and only
 * falls back to deriving it from the legacy `stress` field when
 * `nervous_system` is null — every consumer of pulse data in this codebase
 * (ros-data.ts, lib/human-systems.ts, this route) must apply the same
 * priority order or they'll disagree on a given pulse's nervous-system
 * reading.
 */
function pulseNsState(pulse: { nervous_system?: string | null; stress?: string | null }): string | null {
  if (pulse.nervous_system) return pulse.nervous_system;
  const stress = pulse.stress ?? null;
  if (!stress) return null;
  return ({ low: 'calm', moderate: 'activated', high: 'dysregulated' } as Record<string, string>)[stress] ?? null;
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

    const [insightsRes, dailyRes, pulseRes] = await Promise.all([
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
        .from('recovery_pulses')
        // energy/nervous_system/body_signals are the canonical Telegram-bot
        // fields (Captain directive, 2026-08-10); mood/stress kept in the
        // select so historical rows (pre-canonical, manual-entry) still
        // surface via the raw `pulse` object below — no new writes to them,
        // read-only legacy context.
        .select('log_date,captured_at,energy,nervous_system,body_signals,mood,stress,readiness,pain_score,notes')
        .eq('log_date', today)
        .order('captured_at', { ascending: false })
        .limit(1),
    ]);

    const insights    = insightsRes.data?.[0] ?? null;
    const dailyLog    = dailyRes.data?.[0] ?? null;
    const latestPulse = pulseRes.data?.[0] ?? null;

    // Merge: pulse wins on energy/mood when present (more current than daily log)
    // If no daily log at all for today, synthesise one from the pulse.
    // nervous_system_state prefers the pulse's real captured `nervous_system`
    // reading and only falls back to deriving it from `stress` when that's
    // null (pulseNsState, MSN-0355) — same rule ros-data.ts and
    // human-systems.ts already apply, so this route stops disagreeing with
    // them now that the Telegram bot writes nervous_system directly instead
    // of stress.
    let daily = dailyLog;
    if (latestPulse) {
      if (!daily || daily.log_date !== today) {
        // No log today — build a synthetic row from the pulse
        daily = {
          log_date: today,
          sleep_hours: null,
          sleep_quality: null,
          cpap_compliant: null,
          sitting_tolerance_minutes: null,
          energy: latestPulse.energy,
          mood: latestPulse.mood,
          nervous_system_state: pulseNsState(latestPulse),
        };
      } else {
        // Log exists but pulse has fresher readings — override energy/mood/NS
        daily = {
          ...daily,
          energy: latestPulse.energy ?? daily.energy,
          mood: latestPulse.mood ?? daily.mood,
          nervous_system_state: pulseNsState(latestPulse) ?? daily.nervous_system_state,
        };
      }
    }

    return NextResponse.json({ insights, daily, pulse: latestPulse });
  } catch (err) {
    return NextResponse.json({ insights: null, daily: null, error: String(err) }, { status: 500 });
  }
}
