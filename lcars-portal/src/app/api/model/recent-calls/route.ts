import { NextRequest, NextResponse } from 'next/server';

const ROUTER_BASE = process.env.MODEL_ROUTER_URL ?? 'http://127.0.0.1:8891';

export async function GET(req: NextRequest) {
  const n = req.nextUrl.searchParams.get('n') ?? '20';
  try {
    const res = await fetch(`${ROUTER_BASE}/api/model/recent-calls?n=${n}`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(6000),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ calls: [], error: String(err) }, { status: 502 });
  }
}
