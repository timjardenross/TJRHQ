// Phase B — governance action bridge (write path, D2).
// POST { action, payload } -> inject role SERVER-SIDE (Captain assumes all roles,
// D3) -> run the Python dispatcher and return {status, body}. The browser NEVER
// asserts its own role.
//
// Transport (robust across environments):
//   1. PROXY to the Node Command-Centre backend (VM) /api/v1/intel-governance,
//      which spawns the Python dispatcher. Works on Vercel (no Python there) and
//      on the VM. This is the production path (D2).
//   2. FALLBACK (off-Vercel only): spawn `python3 -m intelligence.workflow.cli`
//      locally — for VM/dev runs where the CC backend isn't up but Python is.

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
  'brief.qa_pass': 'intelligence_lead',
  'brief.record_lesson': 'intelligence_lead',
  'brief.escalate': 'intelligence_lead',
  'brief.notify_telegram': 'intelligence_lead',
  'brief.stand_down': 'intelligence_lead',
  'brief.publish': 'executive_approver',
};

const CC_API = (process.env.COMMAND_CENTRE_API_URL ?? 'http://localhost:5050/api/v1').replace(/\/$/, '');
const CC_SECRET = process.env.COMMAND_CENTRE_API_SECRET ?? '';
const ON_VERCEL = process.env.VERCEL === '1';

type Result = { status: number; body: unknown };

// --- transport 1: proxy to the VM Command-Centre backend ---
async function viaProxy(req: object): Promise<Result> {
  const res = await fetch(`${CC_API}/intel-governance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(CC_SECRET ? { 'X-API-Key': CC_SECRET } : {}) },
    body: JSON.stringify(req),
  });
  const body = await res.json().catch(() => ({ error: 'bad upstream response' }));
  return { status: res.status, body };
}

// --- transport 2: local subprocess (off-Vercel fallback) ---
// `selfUrl` is the portal's own absolute origin, used as the last-resort value
// for LCARS_PORTAL_URL. The dispatcher (intelligence/workflow/service.py
// _deep_link) builds absolute Telegram escalation deep-links from it, so an
// empty value would yield a relative, broken link. Falling back to the request
// origin keeps deep-links valid even when neither env var is set.
function pythonEnv(selfUrl: string): NodeJS.ProcessEnv {
  return {
    ...process.env,
    SUPABASE_URL: process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || '',
    SUPABASE_SERVICE_ROLE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY || '',
    LCARS_PORTAL_URL: process.env.LCARS_PORTAL_URL || process.env.NEXT_PUBLIC_SITE_URL || selfUrl,
  };
}

function localCredsReady(): boolean {
  const url = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  return Boolean(url && process.env.SUPABASE_SERVICE_ROLE_KEY);
}

function viaLocal(req: object, selfUrl: string): Promise<Result> {
  const repoRoot = path.resolve(process.cwd(), '..');
  const python = process.env.PYTHON_BIN || 'python3';
  return new Promise((resolve) => {
    const child = spawn(python, ['-m', 'intelligence.workflow.cli', '--json', JSON.stringify(req)], {
      cwd: repoRoot,
      env: pythonEnv(selfUrl),
    });
    let out = '';
    let err = '';
    const timer = setTimeout(() => child.kill('SIGKILL'), 15_000);
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (err += d));
    child.on('error', (e) => resolve({ status: 500, body: { error: `spawn failed: ${e.message}` } }));
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

  // role injected here — never from the client
  const req = { action, role, payload: body.payload ?? {} };

  // Prefer the VM bridge; fall back to a local subprocess only when off Vercel.
  try {
    const { status, body: result } = await viaProxy(req);
    return NextResponse.json(result, { status });
  } catch (proxyErr) {
    if (ON_VERCEL) {
      return NextResponse.json(
        { error: 'governance bridge unreachable: set COMMAND_CENTRE_API_URL to the VM Command-Centre backend', detail: String(proxyErr) },
        { status: 502 },
      );
    }
    if (!localCredsReady()) {
      return NextResponse.json(
        { error: 'no governance transport: start the Command-Centre backend or set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY' },
        { status: 503 },
      );
    }
    const { status, body: result } = await viaLocal(req, request.nextUrl.origin);
    return NextResponse.json(result, { status });
  }
}
