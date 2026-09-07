// Shared HTTP-backend-first / Python-CLI-fallback dispatch for the Advisory
// Runtime (core/advisory/cli.py). Extracted from api/advisory/route.ts so
// api/advisory/loops/route.ts can reuse the identical fallback chain instead
// of reading core/advisory's log directory directly off the local
// filesystem — that path only ever exists on the VM, never on Vercel, so a
// route doing its own readdir() silently returns an empty list in
// production instead of going through either real backend.

import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import https from 'node:https';
import path from 'node:path';

const PY = process.env.PYTHON_BIN ?? 'python3';
const TIMEOUT_MS = 30_000;
const COMMAND_CENTRE_API_URL = process.env.COMMAND_CENTRE_API_URL ?? 'http://localhost:5000/api/v1';
const COMMAND_CENTRE_API_KEY = process.env.COMMAND_CENTRE_API_KEY ?? '';

export function tryAdvisoryHttpBackend(body: object): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const target = new URL(`${COMMAND_CENTRE_API_URL}/advisory`);
    const payload = JSON.stringify(body);
    const isHttps = target.protocol === 'https:';
    const options: https.RequestOptions = {
      hostname: target.hostname,
      port: target.port || (isHttps ? 443 : 80),
      path: target.pathname + target.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
        ...(COMMAND_CENTRE_API_KEY ? { 'X-Api-Key': COMMAND_CENTRE_API_KEY } : {}),
      },
      // Allow self-signed certs on the VM's own bare-IP Caddy TLS only - if
      // COMMAND_CENTRE_API_URL is ever pointed at a real external HTTPS
      // endpoint, cert validation must stay on (WORKBENCH-REVIEW.md H6,
      // 2026-07-18: this used to disable verification for any HTTPS target).
      ...(isHttps && (target.hostname === 'localhost' || target.hostname === '127.0.0.1')
        ? { agent: new https.Agent({ rejectUnauthorized: false }) }
        : {}),
      timeout: 10_000,
    };
    const transport = isHttps ? https : require('node:http');
    const req = (transport.request as typeof https.request)(options, (res) => {
      if (res.statusCode && res.statusCode >= 400) {
        reject(new Error(`HTTP backend returned ${res.statusCode}`));
        return;
      }
      let raw = '';
      res.on('data', (chunk: Buffer) => { raw += chunk; });
      res.on('end', () => {
        try {
          const data = JSON.parse(raw) as Record<string, unknown>;
          resolve(data.result ?? data);
        } catch {
          reject(new Error('Advisory backend returned non-JSON.'));
        }
      });
    });
    req.on('timeout', () => { req.destroy(); reject(new Error('Advisory backend timeout.')); });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

export function resolveAdvisoryRepoRoot(): string | null {
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

export function runAdvisoryCli(root: string, args: string[]): Promise<unknown> {
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

/** Runs one advisory action through the HTTP backend first, falling back to
 * the local Python CLI. Throws only when both paths are unavailable/fail —
 * callers decide the right HTTP status for that case. */
export async function callAdvisoryAction(action: string, body: object, args: string[]): Promise<unknown> {
  try {
    return await tryAdvisoryHttpBackend(body);
  } catch (err) {
    console.debug(`[advisory:${action}] HTTP backend unavailable, falling back to CLI:`, err instanceof Error ? err.message : err);
  }

  const root = resolveAdvisoryRepoRoot();
  if (!root) {
    throw new Error('Advisory backend unavailable. Start the Command Centre or set COMMAND_CENTRE_API_URL.');
  }
  return runAdvisoryCli(root, args);
}
