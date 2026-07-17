import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';
import { publishMissionEventServerSide } from '@/lib/core-events';

// MSN-0305: governed, audited status update — replaces the Mission Detail
// page's prior direct browser-side Supabase write. Preserves the existing
// free-form status editor UX exactly as-is (all STATUS_OPTIONS remain
// selectable); the fix is moving the write server-side with an audit
// record, not narrowing which transitions are allowed. The 3 narrow
// governed routes (approve/reject/submit) remain the canonical path for
// their specific eligibility-gated transitions; this route is the general
// audited path for everything else the status editor already permits.
export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Mission ID required' }, { status: 400 });
  }

  // See api/missions/[id]/approve/route.ts's own comment (WORKBENCH-REVIEW.md
  // H2) - actor must come from the real session, not a client-supplied
  // body field.
  const session = await requireSession();
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const owner = session.user.email;

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const status = typeof body.status === 'string' ? body.status.trim() : '';
  const notes  = typeof body.notes  === 'string' ? body.notes.trim()  : undefined;
  const source = typeof body.source === 'string' ? body.source.trim() : 'lcars-portal:mission-detail';

  if (!status) {
    return NextResponse.json({ error: 'status is required' }, { status: 400 });
  }

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

    const prevStatus = mission.status;

    const payload: Record<string, unknown> = { status };
    if (notes) payload.notes = notes;

    const { error: updateErr } = await supabase
      .from('missions')
      .update(payload)
      .eq('mission_id', mission.mission_id);

    if (updateErr) throw updateErr;

    // Audit record — same mission_state_transitions table the governed
    // approve/reject/submit routes already write to. Non-blocking, but the
    // mission write above is server-side (not a browser-direct table
    // write), which is the actual governance fix. Service-role client: see
    // approve/route.ts's comment for the full 3-week-silent-failure finding
    // (2026-07-18) - the SSR client is denied by mission_state_transitions'
    // own RLS (enabled, zero anon/authenticated policies).
    void (async () => {
      try {
        const svc = createSupabaseServiceRoleClient();
        const { error } = await svc.from('mission_state_transitions').insert({
          mission_id: mission.mission_id,
          from_state: prevStatus,
          to_state:   status,
          actor:      owner,
          evidence:   JSON.stringify({ action: 'status_update', notes: notes ?? null, source }),
        });
        if (error) console.error('[missions/[id] PATCH] audit insert failed:', error.message);
      } catch (err) {
        console.error('[missions/[id] PATCH] audit insert failed:', err);
      }
    })();

    // MSN-0328 Wave 2: canonical Captain Brief pipeline event — see lib/core-events.ts.
    // Service-role wrapper: core_events RLS denies the anon/SSR `supabase`
    // client above, so this must NOT reuse it (silent-failure bug, fixed).
    void publishMissionEventServerSide({
      eventType: 'mission.status_changed', missionId: mission.mission_id,
      fromStatus: prevStatus, toStatus: status, source,
    });

    return NextResponse.json({
      mission_id:      mission.mission_id,
      title:           mission.title,
      previous_status: prevStatus,
      new_status:      status,
      owner,
      source,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Mission update failed', detail }, { status: 500 });
  }
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Mission ID required' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();
    const { data, error } = await supabase
      .from('missions')
      .select('*')
      .ilike('mission_id', `%${id}%`)
      .limit(1)
      .maybeSingle();

    if (error) throw error;

    if (!data) {
      return NextResponse.json(
        { error: 'Mission not found', id },
        { status: 404 },
      );
    }

    return NextResponse.json({ mission: data });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: 'Failed to fetch mission', detail },
      { status: 500 },
    );
  }
}
