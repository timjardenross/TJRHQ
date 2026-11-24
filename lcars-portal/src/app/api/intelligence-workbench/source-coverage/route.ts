// Source coverage — is each registered source actually delivering intelligence?
// Same six-state rules as intelligence/source_effectiveness.py (ported in
// src/lib/sourceEffectiveness.ts, parity-tested). Read-only.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { classifyAll, coverageLimitations, limitationsLine, summarise } from '@/lib/sourceEffectiveness';
import { loadSourceRows } from '../_lib/sourceCoverage';

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const now = new Date();
    const rows = await loadSourceRows(sb, now);
    const sources = classifyAll(rows, undefined, now);
    const limits = coverageLimitations(rows, undefined, now);
    return NextResponse.json({
      generated_at: now.toISOString(),
      summary: summarise(sources),
      sources,
      limitations: limits,
      limitations_line: limitationsLine(limits),
    });
  } catch (err) {
    console.error('[intelligence-workbench/source-coverage] read failed:', err);
    return NextResponse.json(
      { error: 'source_coverage_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
