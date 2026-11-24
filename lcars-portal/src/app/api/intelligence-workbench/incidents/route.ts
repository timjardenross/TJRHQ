// Clustered / tiered incident view (flag INCIDENT_VIEW_V1, default OFF). Read-only from intelligence_incident_snapshots.
// ?scope=attention returns only alert-level incidents and material exceptions (what Home and Decisions show).

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';
import { fetchIncidentSnapshot, incidentViewEnabled } from '@/lib/incidents';

export async function GET(req: NextRequest) {
  const session = await requireSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!incidentViewEnabled()) return NextResponse.json({ enabled: false, available: false, incidents: [] });
  const sb = await createSupabaseServerClient();
  const attentionOnly = req.nextUrl.searchParams.get('scope') === 'attention';
  const snap = await fetchIncidentSnapshot(sb, { attentionOnly });
  return NextResponse.json({ enabled: true, ...snap });
}
