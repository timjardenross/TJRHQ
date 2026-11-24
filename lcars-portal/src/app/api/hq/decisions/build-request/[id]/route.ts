import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { logActionHistory } from '@/lib/actionHistoryServer';
import { isHqEnabled } from '@/lib/hq/flag';
import { normalizeLifecycle } from '@/lib/engineering-queue';

// Server-side decision guard for build requests (HQ Workbench).
//
// A build request is decided by flipping build_request_inbox.status. Until now
// that was an unconditional browser-side update, so two interfaces (or two
// tabs) could both "decide" the same item, the last write winning. Here the
// change is ONE conditional UPDATE ("set status where it is still the status
// the caller saw"), which the database applies atomically: of two concurrent
// requests exactly one changes the row and the other gets 409.
//
// Scope, deliberately narrow:
//  - approve only applies to a plain build request (action_type IS NULL).
//    An AI-proposed action must be approved through approve-action, which
//    executes it; flipping its status here would skip that execution.
//  - the expected status must be an awaiting-review status, so this route can
//    not be used to rewrite an arbitrary state.
//  - undo only reverses an approval back to an awaiting-review status.
// The existing /decisions page still writes directly from the browser and is
// not made stricter by this route (recorded as an existing gap; closing it
// needs a database-level guard).

type Action = 'approve' | 'decline' | 'undo';
const ACTIONS: Action[] = ['approve', 'decline', 'undo'];

interface Body { action?: string; expectedStatus?: string; restoreStatus?: string; question?: string }

const isAwaiting = (s: string | undefined): s is string => typeof s === 'string' && normalizeLifecycle(s) === 'awaiting_review';

export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  if (!isHqEnabled()) return NextResponse.json({ error: 'Not found' }, { status: 404 });

  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) return NextResponse.json({ error: 'id required' }, { status: 400 });

  let body: Body;
  try { body = (await request.json()) as Body; } catch { return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 }); }
  const action = body.action as Action;
  if (!ACTIONS.includes(action)) return NextResponse.json({ error: 'action must be approve, decline or undo' }, { status: 400 });

  // What the row must currently be, and what it becomes.
  let expected: string;
  let next: string;
  if (action === 'undo') {
    if (!isAwaiting(body.restoreStatus)) return NextResponse.json({ error: 'restoreStatus must be an awaiting-review status' }, { status: 400 });
    expected = 'approved';
    next = body.restoreStatus;
  } else {
    if (!isAwaiting(body.expectedStatus)) return NextResponse.json({ error: 'expectedStatus must be an awaiting-review status' }, { status: 400 });
    expected = body.expectedStatus;
    next = action === 'approve' ? 'approved' : 'rejected';
  }

  const supabase = await createSupabaseServerClient();
  let q = supabase.from('build_request_inbox').update({ status: next }).eq('id', id).eq('status', expected);
  if (action === 'approve') q = q.is('action_type', null);
  const { data, error } = await q.select('id');

  const audit = (outcome: 'success' | 'failed' | 'cancelled', details: Record<string, unknown>) =>
    logActionHistory({ action: `hq.build_request.${action}`, outcome, workbench: 'hq', recordId: id, details: { expected, next, ...details } });

  if (error) {
    await audit('failed', { reason: 'update_error' });
    return NextResponse.json({ error: 'Update failed', detail: error.message }, { status: 500 });
  }

  if (!data || data.length === 0) {
    // Nothing changed. Say why, from the row's current state, so the caller
    // can tell "already decided" from "not found" from "wrong kind of item".
    const { data: cur } = await supabase.from('build_request_inbox').select('status, action_type').eq('id', id).maybeSingle<{ status: string; action_type: string | null }>();
    if (!cur) { await audit('failed', { reason: 'not_found' }); return NextResponse.json({ error: 'Not found' }, { status: 404 }); }
    if (action === 'approve' && cur.action_type) {
      await audit('cancelled', { reason: 'ai_action_needs_approve_action' });
      return NextResponse.json({ error: 'wrong_kind', detail: 'This is an AI-proposed action. Approve it through the action route so it is executed.' }, { status: 409 });
    }
    await audit('cancelled', { reason: 'already_decided', currentStatus: cur.status });
    return NextResponse.json({ error: 'already_decided', currentStatus: cur.status }, { status: 409 });
  }

  await audit('success', {});

  // Same ledger the existing Decide page writes (its action column only allows
  // approve / hold / undo, so a decline is recorded in the audit trail alone).
  // Best-effort: a ledger failure never undoes a decision that was applied.
  if (action !== 'decline') {
    try {
      await supabase.from('decide_ledger').insert({
        question: (body.question ?? '').slice(0, 500) || `Build request ${id}`,
        source: 'engineering',
        item_ref: id,
        action,
        undo_available: action === 'approve',
        prior_status: action === 'approve' ? expected : undefined,
      });
    } catch { /* best-effort */ }
  }

  return NextResponse.json({ ok: true, id, status: next });
}
