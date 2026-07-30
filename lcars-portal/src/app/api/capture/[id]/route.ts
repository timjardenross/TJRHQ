/**
 * Capture action proxy — /api/capture/[id]/*
 *
 * Proxies routing and promotion actions to the Command Centre backend.
 * The browser cannot call the CC backend directly (CORS/auth), so this
 * Next.js route acts as a thin authenticated proxy.
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';

const CC_API = (process.env.COMMAND_CENTRE_API_URL ?? 'http://localhost:5050/api/v1').replace(/\/$/, '');
const CC_SECRET = process.env.COMMAND_CENTRE_API_SECRET ?? '';

function ccHeaders() {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (CC_SECRET) h['X-API-Key'] = CC_SECRET;
  return h;
}

// POST /api/capture/[id]/route  — re-classify and route capture
// POST /api/capture/[id]/promote-mission — promote to mission candidate
export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { id } = params;
  const url = req.nextUrl;
  const action = url.searchParams.get('action') ?? url.pathname.split('/').pop();

  let ccPath: string;
  if (action === 'promote-mission') {
    ccPath = `/capture/${id}/promote-mission`;
  } else if (action === 'enrich') {
    ccPath = `/capture/${id}/enrich`;
  } else {
    ccPath = `/capture/${id}/route`;
  }

  try {
    const body = await req.text();
    const upstream = await fetch(`${CC_API}${ccPath}`, {
      method: 'POST',
      headers: ccHeaders(),
      body: body || undefined,
      // A hung Command Centre backend previously hung this request (and the
      // UI) indefinitely - no timeout existed at all (WORKBENCH-REVIEW.md
      // Medium finding, 2026-07-18). 15s matches captain-brief/route.ts's
      // own convention for proxying to a live backend service.
      signal: AbortSignal.timeout(15_000),
    });
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    console.error('[capture proxy] POST failed:', err);
    return NextResponse.json(
      { ok: false, error: 'Command Centre unreachable' },
      { status: 502 },
    );
  }
}

// PATCH /api/capture/[id]  — update classification/importance/review_status
export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { id } = params;
  try {
    const body = await req.text();
    const upstream = await fetch(`${CC_API}/capture/${id}`, {
      method: 'PATCH',
      headers: ccHeaders(),
      body,
      signal: AbortSignal.timeout(15_000),
    });
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    console.error('[capture proxy] PATCH failed:', err);
    return NextResponse.json(
      { ok: false, error: 'Command Centre unreachable' },
      { status: 502 },
    );
  }
}
