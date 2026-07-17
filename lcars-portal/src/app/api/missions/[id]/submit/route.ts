import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';
import { publishMissionEventServerSide } from '@/lib/core-events';

// MSN-0178: Statuses eligible for submission to Captain approval queue
const SUBMIT_ELIGIBLE = ['Tested', 'Validated', 'Implemented'];

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Mission ID required' }, { status: 400 });
  }

  // See approve/route.ts's own comment (WORKBENCH-REVIEW.md H2) - actor
  // must come from the real session, not a client-supplied body field.
  const session = await requireSession();
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const submitter = session.user.email;

  let body: Record<string, unknown> = {};
  try { body = await request.json(); } catch { /* empty body ok */ }

  const source = typeof body.source === 'string' ? body.source.trim() : 'API';

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

    if (mission.status === 'Awaiting Captain Approval') {
      return NextResponse.json(
        {
          error: 'Mission already awaiting Captain approval',
          current_status: mission.status,
          mission_id: mission.mission_id,
        },
        { status: 409 },
      );
    }

    if (!SUBMIT_ELIGIBLE.includes(mission.status)) {
      return NextResponse.json(
        {
          error: 'Mission not eligible for submission',
          current_status: mission.status,
          eligible_statuses: SUBMIT_ELIGIBLE,
        },
        { status: 409 },
      );
    }

    const prevStatus = mission.status;

    const { error: updateErr } = await supabase
      .from('missions')
      .update({ status: 'Awaiting Captain Approval' })
      .eq('mission_id', mission.mission_id);

    if (updateErr) throw updateErr;

    // Audit record — non-blocking. Service-role client: see approve/route.ts's
    // comment for the full 3-week-silent-failure finding (2026-07-18).
    void (async () => {
      try {
        const svc = createSupabaseServiceRoleClient();
        const { error } = await svc.from('mission_state_transitions').insert({
          mission_id: mission.mission_id,
          from_state: prevStatus,
          to_state:   'Awaiting Captain Approval',
          actor:      submitter,
          evidence:   JSON.stringify({ action: 'submit', source }),
        });
        if (error) console.error('[missions/submit] audit insert failed:', error.message);
      } catch (err) {
        console.error('[missions/submit] audit insert failed:', err);
      }
    })();

    // MSN-0328 Wave 2: canonical Captain Brief pipeline event — see lib/core-events.ts.
    // Service-role wrapper: core_events RLS denies the anon/SSR `supabase`
    // client above, so this must NOT reuse it (silent-failure bug, fixed).
    void publishMissionEventServerSide({
      eventType: 'mission.submitted', missionId: mission.mission_id,
      fromStatus: prevStatus, toStatus: 'Awaiting Captain Approval', source,
    });

    return NextResponse.json({
      mission_id:      mission.mission_id,
      title:           mission.title,
      previous_status: prevStatus,
      new_status:      'Awaiting Captain Approval',
      submitter,
      source,
      next_captain_action: `Use /captain_approve ${mission.mission_id.slice(-4)} or /captain_reject ${mission.mission_id.slice(-4)} <reason>`,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Submission failed', detail }, { status: 500 });
  }
}
