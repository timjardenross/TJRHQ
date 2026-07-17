// MSN-0329 Phase 5 — triggers a real run of the full Understanding/
// Insight/Reasoning pipeline (assemble_evolved_captain_brief(), via
// captain_brief_cli.py --evolved). Deliberately a separate, explicit
// POST action, not something that runs on every page load: real
// synthesis takes 50-260s per insight on this platform's hardware
// (MSN-0329 Phase 3's own measured latency) — running it automatically
// on every Captain's Chair view would make the page unusably slow and
// burn a real LLM call for no reason. The Captain triggers this when
// they actually want a fresh read.
//
// Every insight this produces is already persisted to insight_outcomes
// by assemble_evolved_captain_brief() itself (MSN-0329 Phase 5 fix) —
// this route does not need its own persistence step, only to run the
// pipeline and return what it found.

import { NextResponse } from 'next/server';
import { execFile } from 'child_process';
import * as path from 'path';
import { promisify } from 'util';
import { requireSession } from '@/lib/supabase-server';

const execFileAsync = promisify(execFile);

function repoRoot(): string {
  return process.env.REPO_ROOT ? path.resolve(process.env.REPO_ROOT) : path.resolve(process.cwd(), '..');
}

export async function POST() {
  // Unauthenticated access here isn't just a read leak - it's a free trigger
  // for a real 50-260s LLM pipeline run (WORKBENCH-REVIEW.md H1, 2026-07-18).
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    // 290s client-side ceiling, just under the model router's own 300s
    // server-side TASK_POLICY timeout for these task types. NOTE: if
    // this route is deployed behind a reverse proxy or serverless
    // platform with its own shorter request timeout, that limit wins
    // regardless of this value — not addressed here, since this
    // platform's actual deployment target wasn't re-verified this pass.
    const { stdout } = await execFileAsync(
      'python3',
      ['-m', 'core.platform.captain_brief_cli', '--evolved', '--limit', '200'],
      { cwd: repoRoot(), timeout: 290000, maxBuffer: 10 * 1024 * 1024 },
    );
    const doc = JSON.parse(stdout);
    return NextResponse.json({ insights: doc.insights ?? [], recommendations: doc.recommendations ?? [] });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: 'Failed to generate Captain Intelligence insights', detail },
      { status: 502 },
    );
  }
}
