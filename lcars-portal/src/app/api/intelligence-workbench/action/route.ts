// Phase B — governance action bridge (write path, D2).
// POST { action, payload } -> inject role SERVER-SIDE (Captain assumes all roles,
// D3) -> spawn `python -m intelligence.workflow.cli` -> return {status, body}.
// The browser NEVER asserts its own role. Subprocess (VM/dev) transport, mirroring
// api/advisory/route.ts; the Node CC-backend bridge is the production-hardened
// alternative for Vercel (docs/PHASE-B-DESIGN-SIGN-OFF.md §5 / D2).

import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'node:child_process';
import path from 'node:path';

export const runtime = 'nodejs';

// action -> the role the server asserts for it (Captain holds every role in pilot).
const ACTION_ROLE: Record<string, string> = {
  'signal.score': 'analyst',
  'signal.verify': 'intelligence_lead',
  'signal.select': 'intelligence_lead',
  'brief.curate_watchlist': 'intelligence_lead',
  'brief.qa_gate': 'intelligence_lead',
  'brief.mark_qa_ready': 'intelligence_lead',
  'brief.record_lesson': 'intelligence_lead',
  'brief.escalate': 'intelligence_lead',
  'brief.notify_telegram': 'intelligence_lead',
  'brief.stand_down': 'intelligence_lead',
  'brief.publish': 'executive_approver',
};

function runDispatch(req: object): Promise<{ status: number; body: unknown }> {
  const repoRoot = path.resolve(process.cwd(), '..'); // lcars-portal/ -> repo root
  return new Promise((resolve) => {
    const child = spawn('python3', ['-m', 'intelligence.workflow.cli', '--json', JSON.stringify(req)], {
      cwd: repoRoot,
      env: process.env,
    });
    let out = '';
    let err = '';
    const timer = setTimeout(() => child.kill('SIGKILL'), 15_000);
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (err += d));
    child.on('error', (e) =>
      resolve({ status: 500, body: { error: `spawn failed: ${e.message}` } }),
    );
    child.on('close', () => {
      clearTimeout(timer);
      try {
        resolve(JSON.parse(out.trim()));
      } catch {
        resolve({ status: 500, body: { error: 'dispatch returned non-JSON', stderr: err.slice(0, 500) } });
      }
    });
  });
}

export async function POST(request: NextRequest) {
  let body: { action?: string; payload?: Record<string, unknown> };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'invalid JSON body' }, { status: 400 });
  }

  const action = body.action ?? '';
  const role = ACTION_ROLE[action];
  if (!role) {
    return NextResponse.json({ error: `unknown or unsupported action '${action}'` }, { status: 400 });
  }

  const { status, body: result } = await runDispatch({
    action,
    role, // injected here — never from the client
    payload: body.payload ?? {},
  });
  return NextResponse.json(result, { status });
}
