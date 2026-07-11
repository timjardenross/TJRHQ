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

// Resolve the Supabase env the Python side needs (SUPABASE_URL +
// SUPABASE_SERVICE_ROLE_KEY — service-role so writes bypass RLS), tolerating the
// portal's NEXT_PUBLIC_* naming. Explicit so the bridge doesn't depend on the two
// codebases happening to share env-var names.
function pythonEnv(): NodeJS.ProcessEnv {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || '';
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
  return {
    ...process.env,
    SUPABASE_URL: url,
    SUPABASE_SERVICE_ROLE_KEY: key,
    LCARS_PORTAL_URL:
      process.env.LCARS_PORTAL_URL || process.env.NEXT_PUBLIC_SITE_URL || '',
  };
}

function credsReady(): boolean {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  return Boolean(url && process.env.SUPABASE_SERVICE_ROLE_KEY);
}

function runDispatch(req: object): Promise<{ status: number; body: unknown }> {
  const repoRoot = path.resolve(process.cwd(), '..'); // lcars-portal/ -> repo root
  const python = process.env.PYTHON_BIN || 'python3';
  return new Promise((resolve) => {
    const child = spawn(python, ['-m', 'intelligence.workflow.cli', '--json', JSON.stringify(req)], {
      cwd: repoRoot,
      env: pythonEnv(),
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

  if (!credsReady()) {
    return NextResponse.json(
      { error: 'governance bridge not configured: set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY on the server' },
      { status: 503 },
    );
  }

  const { status, body: result } = await runDispatch({
    action,
    role, // injected here — never from the client
    payload: body.payload ?? {},
  });
  return NextResponse.json(result, { status });
}
