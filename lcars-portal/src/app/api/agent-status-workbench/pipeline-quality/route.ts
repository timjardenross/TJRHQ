// Pipeline Quality drill-down API (Agent & Job Status workbench, Phase 3).
//
// Reads the two Phase 26 observability views (migration 0187) directly —
// intelligence_ingestion_quality_daily and health_ingestion_quality_daily —
// built explicitly for this workbench ("not a new workbench page", per the
// mission's own comment on the migration). No scoring/classification logic
// is duplicated here; this route only shapes the view rows for display.
//
// mission_relevance/disposition/evidence_contribution columns are NULL
// (not zero) for rows collected before the 2026-09-05 Phase 4/6-9 rollout,
// so daily rows before that date will show 0 in those filtered counts —
// that's a real "not yet scored", not a pipeline outage. The UI must not
// read pre-rollout zeros as a stage failure.

import { NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

const DAYS = 14;

export async function GET() {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();

    const [{ data: technical, error: techErr }, { data: health, error: healthErr }] = await Promise.all([
      sb.from('intelligence_ingestion_quality_daily').select('*').order('day', { ascending: false }).limit(DAYS),
      sb.from('health_ingestion_quality_daily').select('*').order('day', { ascending: false }).limit(DAYS),
    ]);

    if (techErr) throw techErr;
    if (healthErr) throw healthErr;

    return NextResponse.json({
      fetchedAt: new Date().toISOString(),
      technical: technical ?? [],
      health: health ?? [],
      note: 'mission_relevance/disposition/evidence_contribution are populated only for rows scored after the 2026-09-05 rollout — earlier days show 0 in those columns because the fields were NULL then, not because the pipeline was down.',
    });
  } catch (err) {
    console.error('[agent-status-workbench/pipeline-quality] read failed:', err);
    return NextResponse.json(
      { error: 'pipeline_quality_read_failed', detail: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 },
    );
  }
}
