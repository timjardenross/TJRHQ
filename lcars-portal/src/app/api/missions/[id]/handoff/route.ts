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

  const source = typeof body.source === 'string' ? body.source.trim() : 'API';

  // SUOC Wave 2 (MSN-0210F, Item D): audit-integrity fix only — `officer` was
  // previously an arbitrary string from the request body with no validation,
  // flowing straight into mission_state_transitions.actor. This does NOT gate
  // the handoff itself (eligibility is decided by HANDOFF_ELIGIBLE above); it
  // only stops the audit label from being spoofed to an arbitrary value.
  // Historical actor values include both officer titles ("Captain") and
  // automated process identifiers ("edo-pilot", "edo-execute") — a strict
  // enum would reject legitimate automation labels, so this validates shape
  // (identifier-like, bounded length) rather than matching a fixed list.
  const OFFICER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$/;
  const officerRaw = typeof body.officer === 'string' ? body.officer.trim() : 'Captain';
  const officer = OFFICER_PATTERN.test(officerRaw) ? officerRaw : 'Captain';

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
    void (async () => { try { await supabase.from('mission_state_transitions').insert({
      mission_id: mission.mission_id,
      from_state: prevStatus,
      to_state:   'Approved for Engineering',
      actor:      officer,
      evidence:   JSON.stringify({ action: 'handoff', source }),
    }); } catch { /* non-fatal */ } })();

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
