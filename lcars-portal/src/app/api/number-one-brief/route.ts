// USS-TJR-MSN-0054 (Agent Orchestration Standardisation Discovery) — first
// live consumer bridge for core/coordination/number_one.py's NumberOne
// coordination engine.
//
// Discovery found NumberOne well-built and tested (core/coordination/
// test_number_one.py, 41 passing tests) but with zero live callers anywhere
// in the platform — the one HTTP endpoint that could have exposed it
// (context_service.py's /brief/number-one) instead hand-rolled a thinner
// reimplementation of the same brief logic from scratch. Fixed the endpoint
// itself first (2026-09-08), then added this route so a real workbench can
// actually surface it — same pattern as api/captain-brief and
// api/recommendations: this Next.js app may run on Vercel's Node.js
// serverless runtime, which has no python3 available, so this fetches the
// context_service.py HTTP bridge rather than shelling out to a local
// interpreter.

import { NextResponse } from 'next/server';
import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';
import { requireSession } from '@/lib/supabase-server';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  try {
    const resp = await fetch(`${contextServiceUrl()}/brief/number-one`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    const brief = await resp.json();
    if (!resp.ok || (brief && typeof brief === 'object' && 'error' in brief)) {
      return NextResponse.json(
        { error: 'Number One brief failed', detail: String(brief?.detail ?? brief?.error ?? resp.statusText) },
        { status: 502 },
      );
    }
    return NextResponse.json(brief);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to reach the Context Assembly service', detail: String(err) },
      { status: 502 },
    );
  }
}
