// GET /api/content-workbench — list comms_content items for the Content
// Workbench board (COMMS-002): Capture -> Research -> Content Prep -> Proofing.
//
// Scope: opportunity/draft/review/approved/ready_to_publish are returned —
// i.e. everything up to (not including) 'published'. Submitting for publish
// approval happens in this workbench too now (Proofing stage, ready_to_publish
// sub-state), via the same governed publish_content proposal in
// /api/comms/[id]/advance — the Captain still makes the final call in Decide,
// this workbench just no longer requires a detour through the Communications
// Workbench to get there. 'published'/'archived' stay excluded: published
// items live in comms-workbench's Portfolio tab, not this active board.

import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient, requireSession } from '@/lib/supabase-server';

export type Stage = 'capture' | 'research' | 'content_prep' | 'proofing';

// 'ready_to_publish' stays inside the Proofing stage (same column) rather than
// becoming a 5th stage — it's still pre-publish, just awaiting the Captain's
// sign-off in Decide via the same governed publish_content proposal every
// other publish action already goes through. See ContentBoard.tsx's
// ProofingStageBody for the ready_to_publish-specific UI within that column.
function stageOf(item: { status: string; research_completed_at: string | null }): Stage {
  if (item.status === 'opportunity') return item.research_completed_at ? 'research' : 'capture';
  if (item.status === 'draft') return 'content_prep';
  return 'proofing'; // review | approved | ready_to_publish
}

// Inlined as a literal (not built from an array via .join()) — supabase-js's
// .select() overload resolution needs a literal string to infer a real row
// type; a widened `string` variable falls back to its GenericStringError
// branch, which is why this isn't SELECT_FIELDS.join(', ') like it reads
// everywhere else in this file's comments.
const SELECT =
  'id, title, pillar, status, source_kind, source_ref, signal_source_id, ' +
  'notes, body, draft_generated_at, sensitive, ' +
  'research_notes, research_sources, research_angle, research_completed_at, ' +
  'qa_checklist, qa_status, reviewed_by, reviewed_at, ' +
  'rank_score, capture_scored, captain_focus, ' +
  'created_at, updated_at';

interface Row {
  id: string; title: string; pillar: string | null; status: string;
  source_kind: string | null; source_ref: string | null; signal_source_id: string | null;
  notes: string | null; body: string | null; draft_generated_at: string | null; sensitive: boolean;
  research_notes: string | null; research_sources: unknown; research_angle: string | null;
  research_completed_at: string | null;
  qa_checklist: unknown; qa_status: string | null; reviewed_by: string | null; reviewed_at: string | null;
  rank_score: number | null; capture_scored: boolean; captain_focus: boolean;
  created_at: string; updated_at: string;
}

export async function GET(_req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = await createSupabaseServerClient();
    const { data, error } = await sb
      .from('comms_content')
      .select(SELECT)
      .in('status', ['opportunity', 'draft', 'review', 'approved', 'ready_to_publish'])
      .order('created_at', { ascending: false })
      .returns<Row[]>();
    if (error) throw error;

    const items = (data ?? []).map((item) => ({ ...item, stage: stageOf(item) }));

    const counts: Record<Stage, number> = { capture: 0, research: 0, content_prep: 0, proofing: 0 };
    for (const item of items) counts[item.stage]++;

    return NextResponse.json({ items, counts });
  } catch (err) {
    console.error('[content-workbench]', err);
    return NextResponse.json({ error: 'Content workbench query failed' }, { status: 500 });
  }
}
