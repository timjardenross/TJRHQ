import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

function getSupabase() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}

export async function GET() {
  try {
    const supabase = getSupabase();
    const today = new Date().toISOString().slice(0, 10);

    const [insightsRes, dailyRes, pulseRes] = await Promise.all([
      supabase
        .from('health_insights')
        .select('insight_date,llm_narrative,risk_flags,positive_flags,wins_this_week,cpap_compliance_rate,dow_pain_pattern')
        .order('insight_date', { ascending: false })
        .limit(1),
      supabase
        .from('health_daily_logs')
        .select('log_date,sleep_hours,sleep_quality,cpap_compliant,nervous_system_state,sitting_tolerance_minutes,mood,energy')
        .order('log_date', { ascending: false })
        .limit(1),
      supabase
        .from('recovery_pulses')
        .select('log_date,captured_at,energy,mood,stress,readiness,pain_score,notes')
        .eq('log_date', today)
        .order('captured_at', { ascending: false })
        .limit(1),
    ]);

    const insights    = insightsRes.data?.[0] ?? null;
    const dailyLog    = dailyRes.data?.[0] ?? null;
    const latestPulse = pulseRes.data?.[0] ?? null;

    // Merge: pulse wins on energy/mood when present (more current than daily log)
    // If no daily log at all for today, synthesise one from the pulse
    let daily = dailyLog;
    if (latestPulse) {
      const stressToNs = (s: string | null) =>
        ({ low: 'calm', moderate: 'activated', high: 'dysregulated' } as Record<string, string>)[s ?? ''] ?? null;

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
          nervous_system_state: stressToNs(latestPulse.stress),
        };
      } else {
        // Log exists but pulse has fresher readings — override energy/mood/NS
        daily = {
          ...daily,
          energy: latestPulse.energy ?? daily.energy,
          mood: latestPulse.mood ?? daily.mood,
          nervous_system_state: stressToNs(latestPulse.stress) ?? daily.nervous_system_state,
        };
      }
    }

    return NextResponse.json({ insights, daily, pulse: latestPulse });
  } catch (err) {
    return NextResponse.json({ insights: null, daily: null, error: String(err) }, { status: 500 });
  }
}
