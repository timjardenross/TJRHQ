import { NextRequest, NextResponse } from 'next/server';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

/**
 * Advisory Runtime endpoint — USS-TJR-MSN-0092 / MSN-0093 (Advisor Hub).
 *
 * Reuse-first: invokes the shared Python advisory runtime (core/advisory/cli.py)
 * — the same engine used by Slack, Telegram and the XO/Number One adapters — and
 * returns its JSON. One brain, every surface.
 *
 * POST body:
 *   { action: "advice"|"challenge"|"lessons"|"evidence", question }
 *   { action: "metrics"|"calibration" }
 *   { action: "outcome", advisoryId, outcome: "success"|"failure"|"partial", note? }
 */

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PY = process.env.PYTHON_BIN ?? 'python3';
const TIMEOUT_MS = 90_000;
const QUESTION_ACTIONS = new Set(['advice', 'challenge', 'lessons', 'evidence', 'temporal', 'episodic']);
const NULLARY_ACTIONS = new Set([
  'metrics', 'calibration', 'advisory-health', 'patterns', 'signals', 'timeline', 'proactive',
]);

function resolveRepoRoot(): string | null {
  const candidates = [
    process.env.USSTJROS_ROOT,
    path.resolve(process.cwd(), '..'),
    process.cwd(),
    path.resolve(process.cwd(), '../..'),
  ].filter(Boolean) as string[];
  for (const root of candidates) {
    if (existsSync(path.join(root, 'core', 'advisory', 'cli.py'))) return root;
  }
  return null;
}

function runCli(root: string, args: string[]): Promise<unknown> {
  const cli = path.join(root, 'core', 'advisory', 'cli.py');
  return new Promise((resolve, reject) => {
    execFile(
      PY,
      [cli, ...args],
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
  let body: {
    action?: string;
    question?: string;
    advisoryId?: string;
    outcome?: string;
    note?: string;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  const action = (body.action ?? 'advice').toLowerCase();
  const root = resolveRepoRoot();
  if (!root) {
    return NextResponse.json(
      { error: 'Advisory runtime not found. Set USSTJROS_ROOT to the repository path.' },
      { status: 503 },
    );
  }

  // Build CLI args per action.
  let args: string[];
  if (QUESTION_ACTIONS.has(action)) {
    const question = (body.question ?? '').trim();
    if (!question) {
      return NextResponse.json({ error: 'A question is required.' }, { status: 400 });
    }
    args = ['--action', action, '--question', question, '--format', 'json'];
  } else if (NULLARY_ACTIONS.has(action)) {
    args = ['--action', action, '--format', 'json'];
  } else if (action === 'outcome') {
    const advisoryId = (body.advisoryId ?? '').trim();
    const outcome = (body.outcome ?? '').trim();
    if (!advisoryId || !['success', 'failure', 'partial', 'unknown'].includes(outcome)) {
      return NextResponse.json(
        { error: 'outcome requires advisoryId and outcome in {success,failure,partial}.' },
        { status: 400 },
      );
    }
    args = ['--action', 'outcome', '--advisory-id', advisoryId, '--outcome', outcome];
    if (body.note) args.push('--note', body.note);
  } else {
    return NextResponse.json({ error: `Unknown action '${action}'.` }, { status: 400 });
  }

  try {
    const result = await runCli(root, args);
    return NextResponse.json({ action, result });
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Advisory runtime failed.';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
