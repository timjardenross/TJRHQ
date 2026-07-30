import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseServerClient } from '@/lib/supabase-server';
import { nextId, appendToRegistry } from '@/lib/id-registry';

// MSN-0334: Captain's Notebook's "Approve Route" previously only updated
// the note's own status/routed_to_type columns via a direct client-side
// Supabase call -- it never created the artefact the UI's own "Artefact
// Created" block implies (missions/lib/notebook/notebook_route_executor.py
// has the real creation logic, but nothing in lcars-portal ever called
// it). A Captain approving a route saw a success state for something that
// silently did nothing.
//
// This route actually creates the artefact for MISSION (the most common
// route, per notebook_route_executor.py's own ROUTE_MAP: captain/xo ->
// MISSION), reusing the same canonical mission-creation path as
// POST /api/missions -- not a second, divergent mission-ID scheme like
// the Python executor's own M-YYYYMMDD-HHMMSS-NB format, which would add
// a third inconsistent ID format to the platform.
//
// Every other route type (IMPROVEMENT, KNOWLEDGE_ARTICLE, BUILD_REQUEST,
// STRATEGIC_INITIATIVE, RESEARCH_REQUEST, COMMUNICATION_OPPORTUNITY) is
// honestly reported as not yet wired here, rather than faking success --
// research_memory's own insert shape was separately found broken in a
// prior audit (MSN-0330), so porting it as-is would just move the bug,
// not fix it.

const ROUTE_TYPE_MAP: Record<string, string> = {
  captain:    'MISSION',
  xo:         'MISSION',
  number_one: 'IMPROVEMENT',
  officer:    'KNOWLEDGE_ARTICLE',
  knowledge:  'KNOWLEDGE_ARTICLE',
};

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
) {
  const id = decodeURIComponent(params.id ?? '').trim();
  if (!id) {
    return NextResponse.json({ error: 'Note ID required' }, { status: 400 });
  }

  try {
    const supabase = await createSupabaseServerClient();

    const { data: note, error: fetchErr } = await supabase
      .from('intelligence_notes')
      .select('id, title, raw_content, triage_summary, recommended_route, routed_to_id, status')
      .eq('id', id)
      .maybeSingle();
    if (fetchErr) throw fetchErr;
    if (!note) {
      return NextResponse.json({ error: 'Note not found', id }, { status: 404 });
    }
    if (note.routed_to_id) {
      return NextResponse.json(
        { error: 'Already routed', routed_to_id: note.routed_to_id },
        { status: 409 },
      );
    }

    const routeType = ROUTE_TYPE_MAP[note.recommended_route ?? ''] ?? null;

    if (routeType === 'MISSION') {
      const mission_id = await nextId('MSN');
      const title = note.title || (note.raw_content ?? 'Notebook capture').slice(0, 80);
      const description = [note.triage_summary, note.raw_content].filter(Boolean).join('\n\n').slice(0, 2000);

      const { error: missionErr } = await supabase
        .from('missions')
        .insert({
          mission_id,
          title,
          status: 'Idea',
          created_by: 'notebook',
          description,
        });
      if (missionErr) throw missionErr;
      appendToRegistry(mission_id, title, 'Captain\'s Notebook', 'Idea');

      const { error: updateErr } = await supabase
        .from('intelligence_notes')
        .update({
          status: 'ROUTED',
          routed_to_type: 'mission',
          routed_to_id: mission_id,
          routed_entity_type: 'MISSION',
          routed_at: new Date().toISOString(),
          routed_by: 'Captain',
        })
        .eq('id', id);
      if (updateErr) throw updateErr;

      return NextResponse.json({ artefact_created: true, entity_type: 'MISSION', artefact_id: mission_id });
    }

    // Honest non-implementation: mark routed (the Captain's triage
    // decision is still real and recorded) but don't claim an artefact
    // was created when it wasn't.
    const { error: updateErr } = await supabase
      .from('intelligence_notes')
      .update({
        status: 'ROUTED',
        routed_to_type: routeType ? routeType.toLowerCase() : 'decision',
      })
      .eq('id', id);
    if (updateErr) throw updateErr;

    return NextResponse.json({
      artefact_created: false,
      entity_type: routeType,
      note: routeType
        ? `Routing decision recorded. Automatic ${routeType.toLowerCase()} creation isn't wired up yet for this route type -- create it manually if needed.`
        : 'Routing decision recorded. No automatic artefact creation exists for this route.',
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: 'Approve route failed', detail }, { status: 500 });
  }
}
