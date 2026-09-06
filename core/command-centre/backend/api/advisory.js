/**
 * Advisory API — /api/v1/advisory
 *
 * Bridge between Vercel (or any remote caller) and the Python advisory CLI.
 * Accepts the same payload format as the portal's /api/advisory Next.js route so
 * that portal → Command Centre → Python CLI is a transparent proxy layer.
 *
 * POST body mirrors lcars-portal/src/app/api/advisory/route.ts:
 *   { action, question?, advisoryId?, outcome?, note? }
 *
 * Auth: BACKEND_API_KEY via X-Api-Key header (enforced by app.js middleware).
 */

const express = require('express');
const router = express.Router();
const path = require('path');
const { spawnSync } = require('child_process');
const fs = require('fs');
const { asyncHandler, ApiError } = require('../middleware/error-handling');

const REPO_ROOT  = path.resolve(__dirname, '../../../../');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const CLI_PY     = path.join(REPO_ROOT, 'core', 'advisory', 'cli.py');

const QUESTION_ACTIONS = new Set(['advice', 'challenge', 'lessons', 'evidence', 'temporal', 'episodic']);
const NULLARY_ACTIONS  = new Set([
  'metrics', 'calibration', 'advisory-health', 'patterns', 'signals', 'timeline', 'proactive',
  'operating-picture', 'wellness', 'strategic', 'forecast', 'daily-brief', 'data-quality',
  'awareness', 'resilience-watch', 'wellness-insights', 'strategic-outlook',
  'opportunity-review', 'captains-picture', 'products', 'loops',
]);

function runCli(args) {
  if (!fs.existsSync(CLI_PY)) {
    throw new ApiError(503, 'Advisory CLI not found on this host.');
  }
  const result = spawnSync(PYTHON_BIN, [CLI_PY, ...args], {
    cwd: REPO_ROOT,
    timeout: 30_000,
    encoding: 'utf8',
    env: { ...process.env, PYTHONPATH: REPO_ROOT },
  });
  if (result.status !== 0) {
    const msg = (result.stderr || '').trim() || 'Advisory CLI exited non-zero.';
    throw new ApiError(502, msg);
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    throw new ApiError(502, 'Advisory CLI returned non-JSON output.');
  }
}

router.post('/', asyncHandler(async (req, res) => {
  const { action = 'advice', question, advisoryId, outcome, note } = req.body || {};
  const act = String(action).toLowerCase();

  let args;
  if (QUESTION_ACTIONS.has(act)) {
    const q = (question || '').trim();
    if (!q) throw new ApiError(400, 'A question is required for this action.');
    args = ['--action', act, '--question', q, '--format', 'json'];
  } else if (NULLARY_ACTIONS.has(act)) {
    args = ['--action', act, '--format', 'json'];
  } else if (act === 'outcome') {
    const id = (advisoryId || '').trim();
    const out = (outcome || '').trim();
    if (!id || !['success', 'failure', 'partial', 'unknown'].includes(out)) {
      throw new ApiError(400, 'outcome requires advisoryId and outcome in {success,failure,partial,unknown}.');
    }
    args = ['--action', 'outcome', '--advisory-id', id, '--outcome', out];
    if (note) args.push('--note', note);
  } else {
    throw new ApiError(400, `Unknown action '${act}'.`);
  }

  const result = runCli(args);
  res.json({ action: act, result });
}));

module.exports = router;
