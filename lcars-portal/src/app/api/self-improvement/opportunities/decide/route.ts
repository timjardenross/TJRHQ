import { NextRequest, NextResponse } from 'next/server';
import { selfImprovementApiUrl, selfImprovementHeaders } from '@/lib/selfImprovementApi';
import { requireSession } from '@/lib/supabase-server';
import { logActionHistory } from '@/lib/actionHistoryServer';

// Engineering Handoffs' own canonical page (/engineering-handoffs) is
// deliberately read-only (2026-09-06 Chief Engineer decision — no
// in-platform approve/merge). This route is the real governed mutation for
// that domain's underlying data — a Captain deciding an HQ Evolution
// opportunity (approve/reject/create_mission/more_evidence etc.) — so it's
// instrumented here instead.
export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  let payload: Record<string, unknown> = {};
  try {
    payload = await req.json();
    const res = await fetch(`${selfImprovementApiUrl()}/api/opportunity/decide`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...selfImprovementHeaders() },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
    const recordId = typeof payload.opportunity_id === 'string' ? payload.opportunity_id : null;
    const decisionType = typeof payload.decision_type === 'string' ? payload.decision_type : null;
    if (res.ok) {
      await logActionHistory({ action: 'self_improvement.opportunity_decide', outcome: 'success', workbench: 'engineering-handoffs', recordId, details: { decision_type: decisionType, mission_id: payload.mission_id ?? null } });
    } else if (res.status === 409) {
      // Controlled rejection — the opportunity had already been decided.
      // Distinct from a fresh decide so a retry doesn't masquerade as a
      // new successful decision.
      await logActionHistory({ action: 'self_improvement.opportunity_decide', outcome: 'cancelled', workbench: 'engineering-handoffs', recordId, details: { decision_type: decisionType, reason: 'already_decided' } });
    } else {
      await logActionHistory({ action: 'self_improvement.opportunity_decide', outcome: 'failed', workbench: 'engineering-handoffs', recordId, details: { decision_type: decisionType, reason: 'upstream_error', status: res.status } });
    }
    return NextResponse.json(body, { status: res.status });
  } catch (err: any) {
    const recordId = typeof payload.opportunity_id === 'string' ? payload.opportunity_id : null;
    await logActionHistory({ action: 'self_improvement.opportunity_decide', outcome: 'failed', workbench: 'engineering-handoffs', recordId, details: { reason: 'unreachable' } });
    return NextResponse.json({ error: 'self_improvement_unreachable', detail: String(err) }, { status: 502 });
  }
}
