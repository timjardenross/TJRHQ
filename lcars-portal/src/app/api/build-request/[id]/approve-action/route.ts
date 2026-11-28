import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import { createMission, createHandoff, logDecision, publishContent, supabaseAdmin, validateActionPayload, type ActionResult } from '@/lib/ai-actions';
import { fetchGovernedRow } from '@/lib/governedFetch';
import { errorDetail } from '@/lib/errorDetail';

interface BuildRequestRow {
  id: string;
  status: string;
  action_type: string | null;
  action_payload: unknown;
}

// MSN-0352: Conversational Governance Enforcement.
//
// This is the ONLY place a proposed AI action (create_mission /
// create_handoff / log_decision) actually mutates operational state.
// It is reachable only from Decide's own Approve action on this exact
// build_request_inbox item - never from the chat parser, never
// automatically. If this route is never called for a given proposal, the
// proposal sits in build_request_inbox as awaiting_review indefinitely,
// exactly like any other governed queue item.

// A claim older than this is treated as abandoned (the process died mid-execution).
const CLAIM_STALE_MS = 5 * 60_000;

export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'build_request_inbox id required' }, { status: 400 });
  }

  // Require a real Captain session - this route performs a governed,
  // human-authorised mutation, not a background job.
  const supabase = await createSupabaseServerClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const admin = supabaseAdmin();

  const fetched = await fetchGovernedRow<BuildRequestRow>(
    admin,
    'build_request_inbox',
    'id',
    id,
    'id, status, action_type, action_payload',
    {
      predicate: (r) => r.status === 'awaiting_review',
      ineligibleStatus: 409,
      ineligibleMessage: (r) => `Not eligible for approval (current status: ${r.status})`,
    },
  );
  if (!fetched.ok) {
    return NextResponse.json({ error: fetched.error }, { status: fetched.status });
  }
  const row = fetched.row;
  if (!row.action_type) {
    return NextResponse.json(
      { error: 'This item is a traditional build request, not a proposed action - approve it via the engineering queue, not this route.' },
      { status: 409 },
    );
  }

  const payload = (row.action_payload as Record<string, unknown>) ?? {};

  // Fail closed, again, right before execution - defense in depth. The
  // parser already validated this payload before ever queuing it, but a
  // row's action_type/action_payload could in principle have been written
  // by something else; never trust stored data as automatically safe to
  // execute just because it reached this table.
  const validation = validateActionPayload(row.action_type, payload);
  if (!validation.ok) {
    await recordExecutionResult(admin, id, { type: row.action_type, success: false, detail: validation.error });
    return NextResponse.json({ error: 'Execution refused', detail: validation.error }, { status: 400 });
  }

  // Claim the row BEFORE executing, as one conditional UPDATE the database
  // applies atomically. fetchGovernedRow above only READ the status, so two
  // simultaneous approvals (two tabs, HQ and /decisions) could both pass it and
  // both execute (two missions). Only the request that wins this claim runs.
  // The claim is stored in action_result (no schema change): it is open to a
  // retry after a recorded failure ({success:false}), and to recovery if a
  // previous attempt died mid-execution (marker older than CLAIM_STALE_MS).
  const staleIso = new Date(Date.now() - CLAIM_STALE_MS).toISOString();
  const { data: claimed, error: claimErr } = await admin
    .from('build_request_inbox')
    .update({ action_result: { state: 'executing', claimed_at: new Date().toISOString() } })
    .eq('id', id)
    .eq('status', 'awaiting_review')
    .or(`action_result.is.null,action_result->>success.eq.false,action_result->>claimed_at.lt.${staleIso}`)
    .select('id');
  if (claimErr) {
    return NextResponse.json({ error: 'Could not start the approval', detail: claimErr.message }, { status: 500 });
  }
  if (!claimed || claimed.length === 0) {
    return NextResponse.json(
      { error: 'Another approval of this item is already in progress or has completed. Nothing was run.' },
      { status: 409 },
    );
  }

  let execution: ActionResult;
  try {
    if (row.action_type === 'create_mission') execution = await createMission(payload);
    else if (row.action_type === 'log_decision') execution = await logDecision(payload);
    else if (row.action_type === 'create_handoff') execution = await createHandoff();
    else if (row.action_type === 'publish_content') execution = await publishContent(payload);
    else {
      // Unreachable given validateActionPayload above, but fail closed
      // explicitly rather than falling through to an implicit no-op.
      const detail = `Unsupported action_type: ${row.action_type}`;
      await recordExecutionResult(admin, id, { type: row.action_type, success: false, detail });
      return NextResponse.json({ error: detail }, { status: 400 });
    }
  } catch (err) {
    const detail = errorDetail(err);
    await recordExecutionResult(admin, id, { type: row.action_type, success: false, detail });
    return NextResponse.json({ error: 'Execution failed', detail }, { status: 500 });
  }

  if (!execution.success) {
    // The proposal stays awaiting_review - a failed execution is not an
    // approval; the Captain can retry or hold, never a silent no-op.
    await recordExecutionResult(admin, id, execution);
    return NextResponse.json({ error: 'Action execution failed', detail: execution.detail }, { status: 500 });
  }

  // Mark the proposal approved and record what it actually produced, so the
  // Decide ledger and this row both carry real evidence of the outcome.
  const { error: updateErr } = await admin
    .from('build_request_inbox')
    .update({
      status: 'approved',
      record_path: execution.id
        ? row.action_type === 'create_mission'
          ? `/missions/${execution.id}`
          : execution.id
        : null,
      action_result: { success: true, detail: execution.detail, executed_at: new Date().toISOString() },
    })
    .eq('id', id);

  if (updateErr) {
    // The real action already happened - do not report failure for a
    // bookkeeping error, but do surface it rather than hiding it.
    return NextResponse.json({
      ok: true,
      execution,
      warning: `Action executed but the queue row could not be marked approved: ${updateErr.message}`,
    });
  }

  return NextResponse.json({ ok: true, execution });
}

/** MSN-0352: every execution attempt - success or failure - leaves a
 * durable trace on the row itself, not just an HTTP response the Captain
 * may never see again. A failed attempt does NOT change status, so the
 * item correctly stays awaiting_review and can be retried or held. */
async function recordExecutionResult(
  admin: ReturnType<typeof supabaseAdmin>,
  id: string,
  execution: { type: string; success: boolean; detail: string },
): Promise<void> {
  try {
    await admin
      .from('build_request_inbox')
      .update({ action_result: { success: execution.success, detail: execution.detail, executed_at: new Date().toISOString() } })
      .eq('id', id);
  } catch {
    // Best-effort - do not let audit-trail bookkeeping mask the real
    // execution outcome already being returned to the caller.
  }
}
