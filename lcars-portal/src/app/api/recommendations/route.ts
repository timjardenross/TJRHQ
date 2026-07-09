// EOS Phase 2 Priority 1 — Recommendation Engine bridge (Capability Composition
// Audit §2 gap #2: "the engine exists and is good; it needs an API route ...
// exposing it to the portal. Connective work, not new reasoning logic.").
//
// core/coordination/recommendation_engine.py's generate_recommendation_package()
// is real, tested, deterministic, health-aware (check_health_constraints()) and
// evidence-cited (_explain_recommendation()) - none of that is re-derived here.
// core/context-assembly/context_service.py already has a `recommendations` CLI
// command (get_recommendations()) that wraps generate_recommendation_package()
// in output-ready JSON (RecommendationPackage.to_dict()) - this route reuses
// that CLI verbatim rather than adding a second wrapper.
//
// Same shell-out pattern as src/app/api/captain-brief/route.ts (the existing,
// working precedent for bridging a pure-Python object with no HTTP surface of
// its own): execFile a Python CLI, cwd at the repo root, parse its stdout JSON.
// context_service.py lives under a hyphenated directory (core/context-assembly)
// so it is invoked as a script path, not via `python3 -m` dotted-module import
// (which the hyphen would break) - the same invocation shape its own tests use
// (core/context-assembly/tests/test_captain_brief_integration.py references
// "python3 core/context-assembly/context_service.py serve").

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
      ['core/context-assembly/context_service.py', 'recommendations'],
      { cwd: repoRoot(), timeout: 15000, maxBuffer: 10 * 1024 * 1024 },
    );
    const pkg = JSON.parse(stdout);
    // context_service.py's own main() catches every exception internally and
    // still exits 0 in some paths with an {"error": ...} body (see get_recommendations
    // -> generate_recommendation_package) - so a parsed-but-error-shaped body
    // must be treated as a real failure, not silently returned as success.
    if (pkg && typeof pkg === 'object' && 'error' in pkg) {
      return NextResponse.json(
        { error: 'Recommendation engine reported a failure', detail: String(pkg.error) },
        { status: 502 },
      );
    }
    return NextResponse.json(pkg);
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to generate recommendations', detail: String(err) },
      { status: 502 },
    );
  }
}
