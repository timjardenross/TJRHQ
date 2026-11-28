import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isHqEnabled } from '@/lib/hq/flag';
import { supabaseAdmin } from '@/lib/ai-actions';
import { DECISION_REQUEST_SOURCE, decisionTextFor, type DecisionRequestPayload } from '@/lib/hq/decisionRequests';
import { POST as approveAction } from '@/app/api/build-request/[id]/approve-action/route';

// Approve an intelligence decision request WITH the option the Captain chose.
// The choice is written into the request, then the existing approve-action route
// does the rest (its atomic claim means a double approval executes once, and it
// records the decision through the existing logDecision). Approving records the
// decision. It does not start any work.
export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  if (!isHqEnabled()) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) return NextResponse.json({ error: 'id required' }, { status: 400 });
  let body: { option?: string };
  try { body = (await request.json()) as { option?: string }; } catch { return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 }); }
  const option = String(body.option ?? '').trim();
  if (!option) return NextResponse.json({ error: 'option required' }, { status: 400 });

  const admin = supabaseAdmin();
  const { data: row, error } = await admin.from('build_request_inbox').select('id, status, source, action_type, action_payload').eq('id', id)
    .maybeSingle<{ id: string; status: string; source: string; action_type: string | null; action_payload: DecisionRequestPayload }>();
  if (error) return NextResponse.json({ error: 'Lookup failed', detail: error.message }, { status: 500 });
  if (!row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  if (row.source !== DECISION_REQUEST_SOURCE || row.action_type !== 'log_decision') {
    return NextResponse.json({ error: 'This is not an intelligence decision request.' }, { status: 409 });
  }
  if (!row.action_payload?.options?.includes(option)) return NextResponse.json({ error: 'That is not one of the options.' }, { status: 400 });

  // Record the choice only while the request is still awaiting review.
  const chosen = { ...row.action_payload, decision: decisionTextFor(row.action_payload, option), chosen_option: option, chosen_at: new Date().toISOString() };
  const { data: updated, error: upErr } = await admin.from('build_request_inbox').update({ action_payload: chosen }).eq('id', id).eq('status', 'awaiting_review')
    // Never change the choice once an approval is executing (approve-action's claim sets action_result);
    // a recorded failure leaves it open to a retry.
    .or('action_result.is.null,action_result->>success.eq.false')
    .select('id');
  if (upErr) return NextResponse.json({ error: 'Could not record the choice', detail: upErr.message }, { status: 500 });
  if (!updated || updated.length === 0) return NextResponse.json({ error: 'already_decided', currentStatus: row.status }, { status: 409 });

  return approveAction(request, { params: { id } });
}
