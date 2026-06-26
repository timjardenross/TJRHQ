/**
 * Server-side canonical ID minting for the LCARS portal.
 *
 * MSN-0147: delegates to tools/mint_id.py (Python) so id_registry.py remains the
 * single writer of .id-counters.json. Eliminates the cross-language lock-contention
 * risk present in the earlier TypeScript-mirror implementation.
 *
 * REPO_ROOT env var (MSN-0144 deployment hardening): overrides the default
 * path.resolve(process.cwd(), '..') assumption so the portal can be run from any
 * working directory.
 *
 * NOTE: Server-side only. Never import from client components.
 */

import { execFile } from 'child_process';
import { promisify } from 'util';
import * as fs from 'fs';
import * as path from 'path';

const execFileAsync = promisify(execFile);

// REPO_ROOT: explicit env var wins; default assumes Next.js runs from lcars-portal/.
const REPO_ROOT = process.env.REPO_ROOT
  ? path.resolve(process.env.REPO_ROOT)
  : path.resolve(process.cwd(), '..');

const MINT_SCRIPT = path.join(REPO_ROOT, 'tools', 'mint_id.py');
const REGISTRY_FILE = path.join(
  REPO_ROOT, 'core', 'mission-control', 'registry', 'mission-index.txt',
);

/**
 * Mint the next canonical ID for the given prefix.
 * Delegates to tools/mint_id.py → id_registry.next_id() so Python is the
 * single counter writer. For MSN returns USS-TJR-MSN-NNNN; other prefixes return PREFIX-NNNN.
 * Falls back to a timestamp-based canonical ID on any subprocess failure.
 */
export async function nextId(prefix: string): Promise<string> {
  try {
    const { stdout } = await execFileAsync(
      'python3', [MINT_SCRIPT, prefix.toUpperCase()],
      { timeout: 5000 },
    );
    return stdout.trim();
  } catch {
    // Non-blocking fallback — keeps canonical prefix even under failure
    return `USS-TJR-${prefix.toUpperCase()}-${Date.now()}`;
  }
}

/**
 * Append a runtime mission entry to the authoritative registry (MSN-0145).
 * Same dash-list format as slack-bot/mission_registry.py::append_canonical_registry().
 * Non-fatal: any filesystem failure is silently swallowed.
 */
export function appendToRegistry(
  missionId: string,
  title: string,
  domain: string,
  status: string,
): void {
  try {
    if (!fs.existsSync(REGISTRY_FILE)) return;
    const ts = new Date().toISOString().slice(0, 16).replace('T', ' ');
    const entry = `\n- ${missionId} | ${ts} | ${domain} | ${status} | ${title}\n`;
    fs.appendFileSync(REGISTRY_FILE, entry, 'utf8');
  } catch {
    // Non-blocking — Supabase is the source of truth for LCARS missions
  }
}
