/**
 * Intelligence governance bridge — Phase B write-path (D2 production transport).
 * Mounted at /api/v1/intel-governance  (distinct from /api/v1/governance, which
 * is the unrelated Starfleet-Records parser).
 *
 * POST /  { action, role, payload }
 *   -> spawns `python3 -m intelligence.workflow.cli --json {...}` on the VM
 *   -> returns { status, body } from dispatch(SupabaseRepository(), ...)
 *
 * The Vercel portal cannot spawn Python (no runtime / no repo FS), so its Next
 * action route proxies here with X-Api-Key. The role is injected server-side by
 * the portal BEFORE proxying — this bridge trusts and forwards it (both hops are
 * server-side + API-key authenticated); it never accepts a role from a browser.
 */

const express = require('express');
const path = require('path');
const { spawn } = require('child_process');

const router = express.Router();

const REPO_ROOT = path.resolve(__dirname, '../../../../');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const TIMEOUT_MS = 15000;

function runDispatch(req) {
  return new Promise((resolve) => {
    const child = spawn(
      PYTHON_BIN,
      ['-m', 'intelligence.workflow.cli', '--json', JSON.stringify(req)],
      { cwd: REPO_ROOT, env: process.env },
    );
    let out = '';
    let err = '';
    const timer = setTimeout(() => child.kill('SIGKILL'), TIMEOUT_MS);
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (err += d));
    child.on('error', (e) => resolve({ status: 500, body: { error: `spawn failed: ${e.message}` } }));
    child.on('close', () => {
      clearTimeout(timer);
      try {
        resolve(JSON.parse(out.trim()));
      } catch {
        resolve({ status: 500, body: { error: 'dispatch returned non-JSON', stderr: String(err).slice(0, 500) } });
      }
    });
  });
}

// POST /api/v1/intel-governance
router.post('/', async (req, res) => {
  const { action, role, payload } = req.body || {};
  if (!action || !role) {
    return res.status(400).json({ error: 'action and role are required (role is injected by the portal)' });
  }
  const { status, body } = await runDispatch({ action, role, payload: payload || {} });
  return res.status(status).json(body);
});

module.exports = router;
