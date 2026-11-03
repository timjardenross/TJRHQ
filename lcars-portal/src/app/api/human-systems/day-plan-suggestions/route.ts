// Human Systems — the day plan's ranked suggestions (top three), computed with the same scoring as the
// capacity bot (../suggestion-ranking.ts). Read-only. The capacity answers come from the latest check-in
// today; with none, there are no suggestions.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { todayLocal } from '@/lib/timezone';
import { rankInterventions, type Intervention, type InterventionEvent, type Preferences } from '../suggestion-ranking';

const LIMIT = 3;

export async function GET() {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  try {
    const sb = await createSupabaseServerClient();
    const today = todayLocal();

    const { data: checkin, error: ce } = await sb
      .from('capacity_checkins')
      .select('capacity_state,stimulation_state,pain_state,executive_function')
      .eq('checkin_type', 'capacity')
      .eq('log_date', today)
      .order('captured_at', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (ce) throw ce;
    if (!checkin?.capacity_state) {
      return NextResponse.json({ suggestions: [] }, { headers: { 'Cache-Control': 'no-store' } });
    }

    const [cands, evts, prefs] = await Promise.all([
      sb.from('capacity_interventions').select('*').eq('enabled', true),
      sb.from('capacity_intervention_events').select('intervention_id,outcome,started_at')
        .not('outcome', 'is', null).order('started_at', { ascending: false }).limit(500),
      sb.from('capacity_preferences').select('item_code,preference_state').eq('domain', 'capacity').not('item_code', 'is', null),
    ]);
    if (cands.error) throw cands.error;
    // Outcomes and preferences are optional: a failed read ranks without them, like the bot.
    const events = (evts.error ? [] : evts.data ?? []) as InterventionEvent[];
    const preferences: Preferences = {};
    for (const r of (prefs.error ? [] : prefs.data ?? []) as { item_code: string; preference_state: string }[]) {
      if (r.item_code && r.preference_state) preferences[r.item_code] = r.preference_state;
    }

    const ranked = rankInterventions((cands.data ?? []) as Intervention[], checkin, events, preferences, LIMIT);
    return NextResponse.json(
      {
        suggestions: ranked.map((i) => ({
          intervention_id: i.intervention_id,
          title: i.title ?? i.button_label ?? 'Suggestion',
          management_lever: i.management_lever ?? null,
          estimated_minutes: i.estimated_minutes ?? null,
        })),
      },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  } catch (err) {
    console.error('[human-systems/day-plan-suggestions] read failed:', err);
    return NextResponse.json({ error: 'day_plan_suggestions_read_failed' }, { status: 500 });
  }
}
