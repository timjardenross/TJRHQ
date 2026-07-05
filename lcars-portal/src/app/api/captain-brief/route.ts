// MSN-0315 Phase 1C — first live consumer bridge for CaptainBriefDocument
// (MSN-0313). CaptainBriefDocument is pure Python with no HTTP surface;
// this route shells out to core/platform/captain_brief_cli.py rather than
// standing up a persistent service for one read-only object. If load ever
// warrants it, this can be swapped for a real service without changing the
// page's contract.

import { NextResponse } from 'next/server';
import { execFile } from 'child_process';
import * as path from 'path';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

function repoRoot(): string {
  return process.env.REPO_ROOT ? path.resolve(process.env.REPO_ROOT) : path.resolve(process.cwd(), '..');
}

export async function GET() {
  try {
    const { stdout } = await execFileAsync(
      'python3',
      ['-m', 'core.platform.captain_brief_cli', '--limit', '200'],
      { cwd: repoRoot(), timeout: 15000, maxBuffer: 10 * 1024 * 1024 },
    );
    const doc = JSON.parse(stdout);
    return NextResponse.json(doc);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to assemble Captain Brief', detail: String(err) },
      { status: 502 },
    );
  }
}
