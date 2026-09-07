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
  let mode: 'first' | 'smaller' | 'another' = 'first';
  let previousAction: string | undefined;
  try {
    const body = await req.json();
    task = typeof body?.task === 'string' ? body.task.trim() : '';
    if (body?.mode === 'smaller' || body?.mode === 'another') mode = body.mode;
    if (typeof body?.previous_action === 'string') previousAction = body.previous_action;
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }
  if (!task) {
    return NextResponse.json({ error: 'task is required' }, { status: 400 });
  }

  const callRouter = () =>
    fetch(`${ROUTER_BASE}/api/model/adhd-decompose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task, mode, previous_action: previousAction }),
      // Model Router's own adhd-decompose timeout is 30s — it runs on
      // Gemini cloud, not local Ollama, since 2026-08-23 (app.py
      // TASK_POLICY). Give some headroom above that for network/JSON
      // overhead rather than racing the server's own timeout.
      signal: AbortSignal.timeout(35_000),
    });

  try {
    let res: Response;
    try {
      res = await callRouter();
    } catch (firstErr) {
      // Model Router is deployed via `systemctl restart` independently of
      // lcars-portal. Next's fetch (undici) pools keep-alive connections
      // to 127.0.0.1:8891; a router restart kills those sockets, and the
      // next reuse throws "TypeError: fetch failed" even though the
      // router is back up within seconds — indistinguishable from a real
      // outage. One retry on a fresh connection absorbs exactly that
      // stale-socket race (and any other one-shot connection blip)
      // instead of surfacing a false "write your own" fallback.
      console.warn('Model Router fetch failed, retrying once (ready-room/decompose):', firstErr);
      res = await callRouter();
    }
    const data = await res.json();
    if (!res.ok) {
      console.error('Model Router returned an error (ready-room/decompose):', data?.error);
    }
    return NextResponse.json({ action: data?.action ?? null }, { status: 200 });
  } catch (err) {
    // Model Router still unreachable after retry — degrade gracefully,
    // don't block the user. Log the real cause server-side but never
    // surface a raw fetch/undici error string (e.g. "TypeError: fetch
    // failed") in the UI.
    console.error('Model Router unreachable after retry (ready-room/decompose):', err);
    return NextResponse.json(
      { action: null, error: "Couldn't reach the suggestion service — write your own first step below." },
      { status: 200 },
    );
  }
}
