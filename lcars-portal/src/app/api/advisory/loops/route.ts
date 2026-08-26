// GET  /api/advisory/loops  — returns open advisory records (outcome: null)
// Read directly from logs/advisory/ADV-*.json — no Python subprocess needed.

import { NextResponse } from 'next/server';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const REPO_ROOT = process.env.REPO_ROOT ?? '/opt/starship-endeavour';
const LOG_DIR = path.join(REPO_ROOT, 'logs', 'advisory');

interface AdvisoryRecord {
  advisory_id: string;
  recorded_at: string;
  question: string;
  recommendation: string;
  outcome: string | null;
  confidence_band?: string | null;
  decision_mode?: string;
}

export async function GET() {
  // Middleware enforces authentication for all non-public routes.
  try {
    let files: string[];
    try {
      files = await readdir(LOG_DIR);
    } catch {
      return NextResponse.json({ loops: [] });
    }

    const adv = files.filter((f) => f.startsWith('ADV-') && f.endsWith('.json'));
    const records: AdvisoryRecord[] = [];

    await Promise.all(
      adv.map(async (f) => {
        try {
          const raw = await readFile(path.join(LOG_DIR, f), 'utf-8');
          const r = JSON.parse(raw) as AdvisoryRecord;
          if (!r.outcome) records.push(r);
        } catch { /* skip corrupt files */ }
      })
    );

    records.sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
    console.log('[loops] returning', records.length, 'open records from', LOG_DIR);
    return NextResponse.json({ loops: records });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Failed to load loops', detail }, { status: 500 });
  }
}
