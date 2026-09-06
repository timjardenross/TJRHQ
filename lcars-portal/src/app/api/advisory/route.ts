import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { resolveAdvisoryRepoRoot, runAdvisoryCli, tryAdvisoryHttpBackend } from '@/lib/advisoryRuntime';

/**
 * Advisory Runtime endpoint — USS-TJR-MSN-0092 / MSN-0093 (Advisor Hub).
 * MSN-PORT-006: HTTP backend first, Python CLI fallback.
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

const QUESTION_ACTIONS = new Set(['advice', 'challenge', 'lessons', 'evidence', 'temporal', 'episodic']);
const NULLARY_ACTIONS = new Set([
  'metrics', 'calibration', 'advisory-health', 'patterns', 'signals', 'timeline', 'proactive',
  'operating-picture', 'wellness', 'strategic', 'forecast', 'daily-brief', 'data-quality',
  'awareness', 'resilience-watch', 'wellness-insights', 'strategic-outlook',
  'opportunity-review', 'captains-picture', 'products', 'loops',
]);

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

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

  // Build CLI args per action (also used to validate inputs before any attempt).
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

  // 1. Try HTTP backend first.
  try {
    const result = await tryAdvisoryHttpBackend(body);
    return NextResponse.json({ action, result });
  } catch (err) {
    console.debug('[advisory] HTTP backend unavailable, falling back to CLI:', err instanceof Error ? err.message : err);
  }

  // 2. Fall back to Python CLI subprocess.
  const root = resolveAdvisoryRepoRoot();
  if (!root) {
    return NextResponse.json(
      { error: 'Advisory backend unavailable. Start the Command Centre or set COMMAND_CENTRE_API_URL.' },
      { status: 503 },
    );
  }

  try {
    const result = await runAdvisoryCli(root, args);
    return NextResponse.json({ action, result });
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Advisory runtime failed.';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
