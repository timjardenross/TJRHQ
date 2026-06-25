import { NextRequest, NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

/**
 * Advisory Runtime endpoint — USS-TJR-MSN-0092 WP5.
 *
 * Reuse-first: this route does NOT re-implement any advisory logic. It invokes
 * the shared Python advisory runtime (core/advisory/cli.py) — the same engine
 * used by Slack and Telegram — and returns its JSON. One brain, every surface.
 *
 * POST body: { action: "advice" | "challenge" | "lessons", question: string }
 *
 * Deployment note: requires the Python repo to be reachable from the portal
 * process (co-located, or USSTJROS_ROOT pointed at it) with python3 available.
 */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PY = process.env.PYTHON_BIN ?? 'python3';
const TIMEOUT_MS = 90_000;
const VALID_ACTIONS = new Set(['advice', 'challenge', 'lessons']);

function resolveRepoRoot(): string | null {
  const candidates = [
    process.env.USSTJROS_ROOT,
    path.resolve(process.cwd(), '..'),       // portal run from lcars-portal/
    process.cwd(),                            // portal run from repo root
    path.resolve(process.cwd(), '../..'),
  ].filter(Boolean) as string[];
  for (const root of candidates) {
    if (existsSync(path.join(root, 'core', 'advisory', 'cli.py'))) return root;
  }
  return null;
}

function runAdvisory(root: string, action: string, question: string): Promise<unknown> {
  const cli = path.join(root, 'core', 'advisory', 'cli.py');
  return new Promise((resolve, reject) => {
    execFile(
      PY,
      [cli, '--action', action, '--question', question, '--format', 'json'],
      { cwd: root, timeout: TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) {
          reject(new Error(stderr?.trim() || err.message));
          return;
        }
        try {
          resolve(JSON.parse(stdout));
        } catch {
          reject(new Error('Advisory runtime returned non-JSON output.'));
        }
      },
    );
  });
}

export async function POST(req: NextRequest) {
  let body: { action?: string; question?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  const action = (body.action ?? 'advice').toLowerCase();
  const question = (body.question ?? '').trim();

  if (!VALID_ACTIONS.has(action)) {
    return NextResponse.json({ error: `Unknown action '${action}'.` }, { status: 400 });
  }
  if (!question) {
    return NextResponse.json({ error: 'A question is required.' }, { status: 400 });
  }

  const root = resolveRepoRoot();
  if (!root) {
    return NextResponse.json(
      { error: 'Advisory runtime not found. Set USSTJROS_ROOT to the repository path.' },
      { status: 503 },
    );
  }

  try {
    const result = await runAdvisory(root, action, question);
    return NextResponse.json({ action, result });
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Advisory runtime failed.';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
