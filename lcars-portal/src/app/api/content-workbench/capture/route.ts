// POST /api/content-workbench/capture — scored capture entry point for the
// Content Workbench (COMMS-002).
//
// Closes the capture-bypass gap identified in the Communications Workbench
// review: the existing Capture Workbench's 'comms' capture type
// (lib/capture.ts -> /api/content/draft) inserts straight into comms_content
// with no classification/ranking. This route scores every capture with the
// TypeScript port in lib/contentScoring.ts before insert, so Content
// Workbench captures carry a real pillar and rank_score from the start —
// exactly like signal-sourced opportunities do.
//
// Deliberately does NOT modify lib/capture.ts or /api/content/draft — the
// original Capture Workbench is untouched and keeps its existing (unscored)
// behaviour.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';
import { scoreCapture } from '@/lib/contentScoring';

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

function deriveTitle(text: string): string {
  const firstLine = text.trim().split('\n')[0].trim();
  const clipped = firstLine.length > 90 ? `${firstLine.slice(0, 87)}…` : firstLine;
  return (clipped || 'Untitled capture').slice(0, 200);
}

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const body = await req.json();
    const text = String(body?.text ?? '').trim();
    if (!text) {
      return NextResponse.json({ error: 'text is required' }, { status: 400 });
    }

    const score = scoreCapture(text);
    const title = deriveTitle(text);

    const sb = serviceClient();
    const { data, error } = await sb
      .from('comms_content')
      .insert({
        title,
        pillar: score.pillarKey,
        source_kind: 'content_workbench_capture',
        classification: 'publishable',
        status: 'opportunity',
        notes: text.slice(0, 1000),
        rank_score: score.rankScore,
        capture_scored: true,
        captain_focus: score.captainFocus,
        // Pre-fill the research brief with the raw capture + suggested angle;
        // research_completed_at stays null until the human confirms it in the
        // Research stage — capture never auto-advances past 'capture'.
        research_angle: score.suggestedAngle,
      })
      .select('id')
      .single();

    if (error) throw error;

    return NextResponse.json({
      success: true,
      content_id: data.id,
      pillar_key: score.pillarKey,
      pillar_name: score.pillarName,
      rank_score: score.rankScore,
      captain_focus: score.captainFocus,
      suggested_angle: score.suggestedAngle,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Internal error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
