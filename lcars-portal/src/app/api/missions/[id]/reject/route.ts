import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import { publishMissionEvent } from '@/lib/core-events';

// MSN-0175: Statuses eligible for captain rejection
const REJECTION_ELIGIBLE = [
  'Awaiting Captain Approval',
  'Awaiting XO Approval',
  'Validated',
  'Tested',
  'Implemented',
  'Designed',
];

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Mission ID required' }, { status: 400 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const reason = typeof body.reason === 'string' ? body.reason.trim() : '';
  if (!reason) {
    return NextResponse.json(
      { error: 'reason is required for rejection' },
      { status: 400 },
    );
  }

  const source = typeof body.source === 'string' ? body.source.trim() : 'API';
  const owner  = typeof body.owner  === 'string' ? body.owner.trim()  : 'Captain';

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

    if (!REJECTION_ELIGIBLE.includes(mission.status)) {
      return NextResponse.json(
        {
          error: 'Mission not eligible for rejection',
          current_status: mission.status,
          eligible_statuses: REJECTION_ELIGIBLE,
        },
        { status: 409 },
      );
    }

    const prevStatus = mission.status;

    const { error: updateErr } = await supabase
      .from('missions')
      .update({ status: 'Requires Rework' })
      .eq('mission_id', mission.mission_id);

    if (updateErr) throw updateErr;

    // Audit record — non-blocking
    void (async () => { try { await supabase.from('mission_state_transitions').insert({
      mission_id: mission.mission_id,
      from_state: prevStatus,
      to_state:   'Requires Rework',
      actor:      owner,
      evidence:   JSON.stringify({ decision: 'reject', reason, source }),
    }); } catch { /* non-fatal */ } })();

    // MSN-0328 Wave 2: canonical Captain Brief pipeline event — see lib/core-events.ts
    void publishMissionEvent(supabase, {
      eventType: 'mission.rejected', missionId: mission.mission_id,
      fromStatus: prevStatus, toStatus: 'Requires Rework', source,
    });

    return NextResponse.json({
      mission_id:      mission.mission_id,
      title:           mission.title,
      previous_status: prevStatus,
      new_status:      'Requires Rework',
      decision:        'reject',
      reason,
      owner,
      source,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Rejection failed', detail }, { status: 500 });
  }
}
