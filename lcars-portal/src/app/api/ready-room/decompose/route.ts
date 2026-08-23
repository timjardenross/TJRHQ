/**
 * Ready Room decomposition proxy — POST /api/ready-room/decompose
 *
 * Thin proxy to Model Router's /api/model/adhd-decompose (see
 * core/model-router/app.py), same shape as api/model/status/route.ts.
 * Returns a single editable micro-action, or null if all providers failed —
 * the client degrades gracefully (lets the user write their own step).
 */

import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';

const ROUTER_BASE = process.env.MODEL_ROUTER_URL ?? 'http://127.0.0.1:8891';

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let task = '';
  try {
    const body = await req.json();
    task = typeof body?.task === 'string' ? body.task.trim() : '';
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }
  if (!task) {
    return NextResponse.json({ error: 'task is required' }, { status: 400 });
  }

  try {
    const res = await fetch(`${ROUTER_BASE}/api/model/adhd-decompose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
      // Model Router's own adhd-decompose timeout is 60s (app.py TASK_POLICY)
      // and a cold gemma3:4b load can take ~50s — give it real room rather
      // than aborting into a false "couldn't generate a step" fallback.
      signal: AbortSignal.timeout(65_000),
    });
    const data = await res.json();
    return NextResponse.json({ action: data?.action ?? null }, { status: res.ok ? 200 : 200 });
  } catch (err) {
    // Model Router unreachable — degrade gracefully, don't block the user.
    return NextResponse.json({ action: null, error: String(err) }, { status: 200 });
  }
}
