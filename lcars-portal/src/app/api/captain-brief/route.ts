// MSN-0315 Phase 1C — first live consumer bridge for CaptainBriefDocument
// (MSN-0313). CaptainBriefDocument is pure Python with no HTTP surface.
//
// 2026-07-10: this route used to execFile a local python3 CLI
// (core.platform.captain_brief_cli) directly - "if load ever warrants it,
// this can be swapped for a real service" (this file's own prior comment).
// Load wasn't the reason it needed swapping: this pattern is confirmed
// broken once deployed to Vercel's Node.js serverless runtime, which has
// no python3 available at all. A real Captain walkthrough found /captains-
// brief permanently showing "No new signals since the last brief" - tested
// the underlying assembly directly against real production data instead of
// trusting that empty state, and it returns a genuinely rich, evidence-
// cited document (real confidence scores, real weighted priority
// explanations, real domain aggregation). The bridge was silently
// swallowing everything, not the engine being empty.
//
// Fixed to call core/context-assembly/context_service.py's new /brief/full
// HTTP endpoint (added this same session, reuses assemble_captain_brief_
// document()/poll_events() verbatim - the exact same functions
// captain_brief_cli.py called) instead of shelling out to a local
// interpreter that may not exist wherever this Next.js app actually runs.
// CONTEXT_SERVICE_URL must point at a real, persistently-running instance
// of `python3 context_service.py serve` - this route depends on that
// infrastructure existing somewhere reachable, not something it can stand
// up itself.

import { NextResponse } from 'next/server';
import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';

export async function GET() {
  try {
    const resp = await fetch(`${contextServiceUrl()}/brief/full?limit=200`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    const doc = await resp.json();
    if (!resp.ok || (doc && typeof doc === 'object' && 'error' in doc)) {
      return NextResponse.json(
        { error: 'Failed to assemble Captain Brief', detail: String(doc?.detail ?? doc?.error ?? resp.statusText) },
        { status: 502 },
      );
    }
    return NextResponse.json(doc);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to reach the Captain Brief service', detail: String(err) },
      { status: 502 },
    );
  }
}
