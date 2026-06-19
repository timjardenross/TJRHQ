import { NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

export async function GET() {
  try {
    const supabase = createSupabaseServerClient();

    const [insightsRes, dailyRes] = await Promise.all([
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
    ]);

    const insights = insightsRes.data?.[0] ?? null;
    const daily    = dailyRes.data?.[0] ?? null;

    return NextResponse.json({ insights, daily });
  } catch (err) {
    return NextResponse.json({ insights: null, daily: null, error: String(err) }, { status: 500 });
  }
}
