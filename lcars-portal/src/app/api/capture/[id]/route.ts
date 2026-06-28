/**
 * Capture action proxy — /api/capture/[id]/*
 *
 * Proxies routing and promotion actions to the Command Centre backend.
 * The browser cannot call the CC backend directly (CORS/auth), so this
 * Next.js route acts as a thin authenticated proxy.
 */

import { NextRequest, NextResponse } from 'next/server';

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
  const { id } = params;
  const url = req.nextUrl;
  const action = url.searchParams.get('action') ?? url.pathname.split('/').pop();

  let ccPath: string;
  if (action === 'promote-mission') {
    ccPath = `/capture/${id}/promote-mission`;
  } else {
    ccPath = `/capture/${id}/route`;
  }

  try {
    const body = await req.text();
    const upstream = await fetch(`${CC_API}${ccPath}`, {
      method: 'POST',
      headers: ccHeaders(),
      body: body || undefined,
    });
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: 'Command Centre unreachable', detail: String(err) },
      { status: 502 },
    );
  }
}

// PATCH /api/capture/[id]  — update classification/importance/review_status
export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const { id } = params;
  try {
    const body = await req.text();
    const upstream = await fetch(`${CC_API}/capture/${id}`, {
      method: 'PATCH',
      headers: ccHeaders(),
      body,
    });
    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: 'Command Centre unreachable', detail: String(err) },
      { status: 502 },
    );
  }
}
