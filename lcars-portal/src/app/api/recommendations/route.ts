// EOS Phase 2 Priority 1 — Recommendation Engine bridge (Capability Composition
// Audit §2 gap #2: "the engine exists and is good; it needs an API route ...
// exposing it to the portal. Connective work, not new reasoning logic.").
//
// core/coordination/recommendation_engine.py's generate_recommendation_package()
// is real, tested, deterministic, health-aware (check_health_constraints()) and
// evidence-cited (_explain_recommendation()) - none of that is re-derived here.
//
// 2026-07-10: this route used to execFile a local python3 CLI
// (core/context-assembly/context_service.py) directly from this API route -
// a pattern confirmed broken once deployed to Vercel's Node.js serverless
// runtime, which has no python3 available at all. Real Captain walkthrough
// found this: /recommended showed nothing, but the underlying engine (tested
// directly against real production data) returns genuinely good, evidence-
// cited output - the bridge was the entire problem, not the engine.
//
// Fixed to call context_service.py's new /recommendations/full HTTP endpoint
// (added this same session) instead - the exact same get_recommendations()
// function, now reachable over a plain fetch() from wherever this Next.js
// app actually runs, rather than shelling out to a local interpreter that
// may not exist in that environment. CONTEXT_SERVICE_URL must point at a
// real, persistently-running instance of `python3 context_service.py serve`
// (see core/context-assembly/context_service.py's own serve command) -
// this is infrastructure this route depends on now existing somewhere
// reachable, not something this route can stand up itself.

import { NextResponse } from 'next/server';
import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';
import { requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const resp = await fetch(`${contextServiceUrl()}/recommendations/full`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    const pkg = await resp.json();
    // The Flask route returns a 500 with an {"error": ...} body on any
    // internal failure (context_service.py's own try/except pattern,
    // unchanged by this bridge swap) - a parsed-but-error-shaped body must
    // be treated as a real failure, not silently returned as success.
    if (!resp.ok || (pkg && typeof pkg === 'object' && 'error' in pkg)) {
      return NextResponse.json(
        { error: 'Recommendation engine reported a failure', detail: String(pkg?.detail ?? pkg?.error ?? resp.statusText) },
        { status: 502 },
      );
    }
    return NextResponse.json(pkg);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to reach the Recommendation Engine service', detail: String(err) },
      { status: 502 },
    );
  }
}
