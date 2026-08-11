import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';
import { publishMissionEventServerSide } from '@/lib/core-events';
import { recordHeartbeatServerSide } from '@/lib/heartbeat';

// MSN-0175: Statuses eligible for captain approval
const APPROVAL_ELIGIBLE = [
  'Awaiting Captain Approval',
  'Awaiting XO Approval',
  'Validated',
  'Tested',
];

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Mission ID required' }, { status: 400 });
  }

  // The audit actor must be who actually authorised this, not whatever the
  // request body claims (WORKBENCH-REVIEW.md H2, 2026-07-18: a caller could
  // set owner: 'Captain' regardless of who they really are). RLS on
  // missions.UPDATE already requires `authenticated`, so this session check
  // doesn't newly restrict who can approve - it makes the audit trail
  // actually trustworthy about who did.
  const session = await requireSession();
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const owner = session.user.email;

  let body: Record<string, unknown> = {};
  try { body = await request.json(); } catch { /* empty body ok — defaults used */ }

  const source = typeof body.source === 'string' ? body.source.trim() : 'API';

  try {
    const supabase = await createSupabaseServerClient();

    const { data: mission, error: fetchErr } = await supabase
      .from('missions')
      .select('mission_id, title, status')
      // Exact match, not substring (WORKBENCH-REVIEW.md H3, 2026-07-18):
      // .ilike('%'+id+'%') meant `MSN-1` matched `MSN-10`/`MSN-100` too,
      // with .limit(1) silently picking whichever sorted first. Every real
      // caller already passes the full canonical mission_id.
      .eq('mission_id', id)
      .maybeSingle();

    if (fetchErr) throw fetchErr;

    if (!mission) {
      return NextResponse.json({ error: 'Mission not found', id }, { status: 404 });
    }

    if (!APPROVAL_ELIGIBLE.includes(mission.status)) {
      return NextResponse.json(
        {
          error: 'Mission not eligible for approval',
          current_status: mission.status,
          eligible_statuses: APPROVAL_ELIGIBLE,
        },
        { status: 409 },
      );
    }

    const prevStatus = mission.status;

    const { error: updateErr } = await supabase
      .from('missions')
      .update({ status: 'Approved' })
      .eq('mission_id', mission.mission_id);

    if (updateErr) throw updateErr;

    // Audit record — non-blocking; mission update already succeeded.
    // mission_state_transitions has RLS enabled with ZERO anon/authenticated
    // policies (confirmed live, 2026-07-18) - the SSR `supabase` client above
    // was silently denied on every call (the swallowed catch hid it; the
    // real table sat at 18 rows, none newer than 2026-06-27, for 3+ weeks of
    // real approvals/rejections). Same class of bug core-events.ts's own
    // docstring already names for Physical Readiness/mission-lifecycle/
    // knowledge-library - this call site just hadn't been migrated yet.
    void (async () => {
      try {
        const svc = createSupabaseServiceRoleClient();
        const { error } = await svc.from('mission_state_transitions').insert({
          mission_id: mission.mission_id,
          from_state: prevStatus,
          to_state:   'Approved',
          actor:      owner,
          evidence:   JSON.stringify({ decision: 'approve', source }),
        });
        if (error) console.error('[missions/approve] audit insert failed:', error.message);
      } catch (err) {
        console.error('[missions/approve] audit insert failed:', err);
      }
    })();

    // MSN-0328 Wave 2: canonical Captain Brief pipeline event — see lib/core-events.ts.
    // Service-role wrapper: core_events RLS denies the anon/SSR `supabase`
    // client above, so this must NOT reuse it (silent-failure bug, fixed).
    void publishMissionEventServerSide({
      eventType: 'mission.approved', missionId: mission.mission_id,
      fromStatus: prevStatus, toStatus: 'Approved', source,
    });

    // Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/
    // final-4-domains.md): confirmed-live via tg-xo.service's
    // /captain_approve and CaptainApprovalQueue.tsx. See that doc for the
    // full multi-writer disposition of the `missions` domain.
    void recordHeartbeatServerSide({
      domainKey: 'missions',
      status: 'ok',
      detail: `approve mission_id=${mission.mission_id}`,
    });

    return NextResponse.json({
      mission_id:      mission.mission_id,
      title:           mission.title,
      previous_status: prevStatus,
      new_status:      'Approved',
      decision:        'approve',
      owner,
      source,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Approval failed', detail }, { status: 500 });
  }
}
