// MSN-0329 Phase 5 — triggers a real run of the full Understanding/
// Insight/Reasoning pipeline (assemble_evolved_captain_brief(), via
// captain_brief_cli.py --evolved). Deliberately a separate, explicit
// POST action, not something that runs on every page load: real
// synthesis takes 50-260s per insight on this platform's hardware
// (MSN-0329 Phase 3's own measured latency) — running it automatically
// on every Captain's Chair view would make the page unusably slow and
// burn a real LLM call for no reason. The Captain triggers this when
// they actually want a fresh read.
//
// Every insight this produces is already persisted to insight_outcomes
// by assemble_evolved_captain_brief() itself (MSN-0329 Phase 5 fix) —
// this route does not need its own persistence step, only to run the
// pipeline and return what it found.
//
// 2026-08-09: this route used to execFile a local python3 CLI
// (core.platform.captain_brief_cli --evolved) directly - the exact
// pattern api/captain-brief/route.ts's own header comment documents as
// "confirmed broken once deployed to Vercel's Node.js serverless
// runtime, which has no python3 available at all" (fixed there
// 2026-07-10). This route carried the same anti-pattern for three more
// weeks after that fix and lesson were already committed to this repo -
// clicking "Generate New Insights" in production almost certainly
// failed every time. Fixed the same way: core/context-assembly/
// context_service.py's Flask service already exposes /brief/full for
// the non-evolved document; added a POST /brief/evolved endpoint there
// that calls assemble_evolved_captain_brief() verbatim (same function
// captain_brief_cli.py --evolved called), and this route now fetch()es
// it instead of shelling out. CONTEXT_SERVICE_URL must point at a real,
// persistently-running instance of `python3 context_service.py serve`
// (see contextService.ts) - this route depends on that infrastructure
// existing somewhere reachable, not something it can stand up itself.

import { NextResponse } from 'next/server';
import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';
import { requireSession } from '@/lib/supabase-server';

export async function POST() {
  // Unauthenticated access here isn't just a read leak - it's a free trigger
  // for a real 50-260s LLM pipeline run (WORKBENCH-REVIEW.md H1, 2026-07-18).
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // 290s client-side ceiling, just under the model router's own 300s
    // server-side TASK_POLICY timeout for these task types. NOTE: if
    // this route is deployed behind a reverse proxy or serverless
    // platform with its own shorter request timeout, that limit wins
    // regardless of this value — not addressed here, since this
    // platform's actual deployment target wasn't re-verified this pass.
    const resp = await fetch(`${contextServiceUrl()}/brief/evolved?limit=200`, {
      method: 'POST',
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(290000),
    });
    const doc = await resp.json();
    if (!resp.ok || (doc && typeof doc === 'object' && 'error' in doc)) {
      return NextResponse.json(
        {
          error: 'Failed to generate Captain Intelligence insights',
          detail: String(doc?.detail ?? doc?.error ?? resp.statusText),
        },
        { status: 502 },
      );
    }
    return NextResponse.json({ insights: doc.insights ?? [], recommendations: doc.recommendations ?? [] });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: 'Failed to reach the Captain Brief service', detail },
      { status: 502 },
    );
  }
}
