import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { isHqEnabled } from '@/lib/hq/flag';
import { proposeAction, supabaseAdmin } from '@/lib/ai-actions';
import { logActionHistory } from '@/lib/actionHistoryServer';
import { DECISION_REQUEST_SOURCE, requestIdFor, validateDecisionRequest } from '@/lib/hq/decisionRequests';

// Turn ONE intelligence item into a governed decision request, on explicit request.
// One request per item (deterministic request_id + the table's UNIQUE request_id);
// repeating the call returns the existing request instead of creating another.
export async function POST(request: NextRequest) {
  if (!isHqEnabled()) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  let body: unknown;
  try { body = await request.json(); } catch { return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 }); }
  const v = validateDecisionRequest(body as Record<string, unknown>);
  if (!v.ok) return NextResponse.json({ error: v.error }, { status: 400 });
  const payload = v.value;
  const requestId = requestIdFor(payload.dedupe_key);

  const existing = async () => {
    const { data } = await supabaseAdmin().from('build_request_inbox').select('id, status').eq('request_id', requestId).maybeSingle<{ id: string; status: string }>();
    return data;
  };

  const already = await existing();
  if (already) return NextResponse.json({ ok: true, existing: true, id: already.id, status: already.status });

  const res = await proposeAction('log_decision', payload as unknown as Record<string, unknown>, { requestId, source: DECISION_REQUEST_SOURCE });
  if (!res.success) {
    if (res.duplicate) {
      const row = await existing();
      return NextResponse.json({ ok: true, existing: true, id: row?.id ?? null, status: row?.status ?? null });
    }
    await logActionHistory({ action: 'hq.decision_request.create', outcome: 'failed', workbench: 'hq', recordId: payload.dedupe_key, details: { reason: 'insert_failed' } });
    return NextResponse.json({ error: 'Could not create the request', detail: res.detail }, { status: 500 });
  }
  await logActionHistory({ action: 'hq.decision_request.create', outcome: 'success', workbench: 'hq', recordId: payload.dedupe_key, details: { requestId, options: payload.options.length } });
  return NextResponse.json({ ok: true, existing: false, id: res.id ?? null, status: 'awaiting_review' }, { status: 201 });
}
