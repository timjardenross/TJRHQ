import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// MSN-0180: Statuses eligible for engineering handoff
// Decision: use 'Approved for Engineering' as the target status (new, added in MSN-0180 migration).
// Reasoning: 'Designed' already means design-complete; a distinct handoff status makes
// the lifecycle explicit and prevents confusion between "designed" and "approved to build".
const HANDOFF_ELIGIBLE = ['Idea', 'Designed', 'Approved', 'Requires Rework'];

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Mission ID required' }, { status: 400 });
  }

  let body: Record<string, unknown> = {};
  try { body = await request.json(); } catch { /* empty body ok */ }

  const source  = typeof body.source  === 'string' ? body.source.trim()  : 'API';
  const officer = typeof body.officer === 'string' ? body.officer.trim() : 'Captain';

  try {
    const supabase = await createSupabaseServerClient();

    const { data: mission, error: fetchErr } = await supabase
      .from('missions')
      .select('mission_id, title, status')
      .ilike('mission_id', `%${id}%`)
      .limit(1)
      .maybeSingle();

    if (fetchErr) throw fetchErr;

    if (!mission) {
      return NextResponse.json({ error: 'Mission not found', id }, { status: 404 });
    }

    if (mission.status === 'Approved for Engineering') {
      return NextResponse.json(
        {
          error: 'Mission already in engineering queue',
          current_status: mission.status,
          mission_id: mission.mission_id,
        },
        { status: 409 },
      );
    }

    if (!HANDOFF_ELIGIBLE.includes(mission.status)) {
      return NextResponse.json(
        {
          error: 'Mission not eligible for engineering handoff',
          current_status: mission.status,
          eligible_statuses: HANDOFF_ELIGIBLE,
        },
        { status: 409 },
      );
    }

    const prevStatus = mission.status;

    const { error: updateErr } = await supabase
      .from('missions')
      .update({ status: 'Approved for Engineering' })
      .eq('mission_id', mission.mission_id);

    if (updateErr) throw updateErr;

    // Audit record — non-blocking
    supabase.from('mission_state_transitions').insert({
      mission_id: mission.mission_id,
      from_state: prevStatus,
      to_state:   'Approved for Engineering',
      actor:      officer,
      evidence:   JSON.stringify({ action: 'handoff', source }),
    }).then(() => {/* fire-and-forget */}).catch(() => {/* non-fatal */});

    return NextResponse.json({
      mission_id:      mission.mission_id,
      title:           mission.title,
      previous_status: prevStatus,
      new_status:      'Approved for Engineering',
      officer,
      source,
      next_engineering_action: 'Engineering implementation and test evidence required before /mission_submit',
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Handoff failed', detail }, { status: 500 });
  }
}
