// Briefs/Captain's Brief consolidation Phase 2-3
// (BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md §4.1/§6) — proxy for the new
// shared cross-domain assembly endpoint (core/context-assembly/
// context_service.py's `/brief/domains`), mirroring api/captain-brief/
// route.ts's own reasoning verbatim: context_service.py runs as a real,
// persistent Flask process somewhere Python is actually available, so this
// route reaches it with a plain fetch() rather than shelling out to a local
// interpreter Vercel's Node.js serverless runtime doesn't have.

import { NextResponse } from 'next/server';
import { contextServiceUrl, contextServiceHeaders } from '@/lib/contextService';
import { requireSession } from '@/lib/supabase-server';
import { checkRateLimit } from '@/lib/rateLimit';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  // Same reasoning as api/captain-brief/route.ts: assembles a full
  // cross-domain document against context_service.py on every call — cap
  // accidental loop/retry hammering, not a security boundary.
  if (!checkRateLimit('briefs-domains', 6, 60_000)) {
    return NextResponse.json({ error: 'Too many requests — try again shortly' }, { status: 429 });
  }

  try {
    const resp = await fetch(`${contextServiceUrl()}/brief/domains?limit=200`, {
      headers: contextServiceHeaders(),
      signal: AbortSignal.timeout(15000),
    });
    const doc = await resp.json();
    if (!resp.ok || (doc && typeof doc === 'object' && 'error' in doc)) {
      return NextResponse.json(
        { error: 'Failed to assemble Domains document', detail: String(doc?.detail ?? doc?.error ?? resp.statusText) },
        { status: 502 },
      );
    }
    return NextResponse.json(doc);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to reach the Domains assembly service', detail: String(err) },
      { status: 502 },
    );
  }
}
