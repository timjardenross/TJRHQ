/**
 * Server-side canonical ID registry — TypeScript mirror of the Python id_registry.py.
 *
 * Shares the same `.id-counters.json` counter file so all runtime paths (Slack bot,
 * LCARS portal) increment the same atomic sequence and can never collide.
 *
 * MSN-0144: replaces the MSN-AI-${Date.now()} fallback in ai-actions.ts.
 *
 * NOTE: This module uses Node.js `fs` and is server-side only. Never import it
 * from client components.
 */

import * as fs from 'fs';
import * as path from 'path';

// process.cwd() in Next.js server context is the lcars-portal/ directory.
// The repo root is one level up.
const REPO_ROOT = path.resolve(process.cwd(), '..');
const COUNTER_FILE = path.join(REPO_ROOT, '.id-counters.json');
const LOCK_FILE = path.join(REPO_ROOT, '.id-counters.lock');
const REGISTRY_FILE = path.join(REPO_ROOT, 'core', 'mission-control', 'registry', 'mission-index.txt');

const CANONICAL_PREFIX: Record<string, string> = {
  MSN: 'USS-TJR-MSN',
};

const SEEDS: Record<string, number> = {
  MSN: 143,
  BREQ: 10,
  DEC: 0,
};

async function acquireLock(retries = 20, delayMs = 50): Promise<void> {
  for (let i = 0; i < retries; i++) {
    try {
      const fd = fs.openSync(LOCK_FILE, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY);
      fs.closeSync(fd);
      return;
    } catch {
      await new Promise<void>(r => setTimeout(r, delayMs));
    }
  }
  throw new Error(`Could not acquire ${LOCK_FILE} after ${retries} retries`);
}

function releaseLock(): void {
  try { fs.unlinkSync(LOCK_FILE); } catch { /* ignore */ }
}

function loadCounters(): Record<string, number> {
  try {
    return JSON.parse(fs.readFileSync(COUNTER_FILE, 'utf8')) as Record<string, number>;
  } catch {
    return {};
  }
}

function saveCounters(data: Record<string, number>): void {
  fs.writeFileSync(COUNTER_FILE, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

/**
 * Mint the next canonical ID for the given prefix.
 * For MSN returns USS-TJR-MSN-NNNN; other prefixes return PREFIX-NNNN.
 * Atomically increments the shared .id-counters.json counter.
 */
export async function nextId(prefix: string): Promise<string> {
  const p = prefix.toUpperCase();
  const canonical = CANONICAL_PREFIX[p] ?? p;
  await acquireLock();
  try {
    const data = loadCounters();
    const n = (data[p] ?? SEEDS[p] ?? 0) + 1;
    data[p] = n;
    saveCounters(data);
    return `${canonical}-${String(n).padStart(4, '0')}`;
  } finally {
    releaseLock();
  }
}

/**
 * Append a runtime mission entry to the authoritative registry (MSN-0145).
 * Uses the same dash-list format as slack-bot/mission_registry.py::append_canonical_registry().
 * Non-fatal: filesystem write failures are silently swallowed — the Supabase record is the primary.
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
    // Non-blocking — Supabase record is the source of truth for LCARS missions
  }
}
