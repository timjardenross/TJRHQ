import { NextRequest, NextResponse } from 'next/server';
import { requireSession } from '@/lib/supabase-server';
import { supabaseAdmin } from '@/lib/ai-actions';
import { recordHeartbeatServerSide } from '@/lib/heartbeat';
import { logActionHistory } from '@/lib/actionHistoryServer';

// Advisory transcripts are Captain-only content - require a real session
// before reading or writing (WORKBENCH-REVIEW.md finding C3, 2026-07-18:
// this route previously used a bare anon-key client with no session check,
// and advisory_sessions' own RLS was role=public - together, fully open).

// POST /api/advisory-sessions — save a consult message or board result
export async function POST(req: NextRequest) {
  try {
    const session = await requireSession();
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = (await req.json()) as {
      mode: 'consult' | 'board';
      advisor_id?: string;
      question: string;
      response?: string;
      result?: Record<string, unknown>;
      metadata?: Record<string, unknown>;
    };

    const { mode, advisor_id, question, response, result, metadata } = body;

    if (!mode || !question) {
      await logActionHistory({ action: 'advisory.session_save', outcome: 'failed', workbench: 'advisory', details: { reason: 'mode_and_question_required' } });
      return NextResponse.json({ error: 'mode and question are required' }, { status: 400 });
    }
    if (mode === 'consult' && !response) {
      await logActionHistory({ action: 'advisory.session_save', outcome: 'failed', workbench: 'advisory', details: { reason: 'response_required', mode } });
      return NextResponse.json({ error: 'response is required for consult mode' }, { status: 400 });
    }
    if (mode === 'board' && !result) {
      await logActionHistory({ action: 'advisory.session_save', outcome: 'failed', workbench: 'advisory', details: { reason: 'result_required', mode } });
      return NextResponse.json({ error: 'result is required for board mode' }, { status: 400 });
    }

    const supabase = supabaseAdmin();
    const { data, error } = await supabase
      .from('advisory_sessions')
      .insert({ mode, advisor_id: advisor_id ?? null, question, response: response ?? null, result: result ?? null, metadata: metadata ?? null })
      .select('id, created_at')
      .single();

    if (error) {
      console.error('[advisory-sessions POST] insert failed:', error);
      await logActionHistory({ action: 'advisory.session_save', outcome: 'failed', workbench: 'advisory', details: { reason: 'write_error', mode } });
      return NextResponse.json({ error: 'internal error' }, { status: 500 });
    }

    // Heartbeat only after the real advisory_sessions row is confirmed
    // written — never before, never on the error path above.
    await recordHeartbeatServerSide({ domainKey: 'advisory_sessions', detail: `mode=${mode}` });
    await logActionHistory({ action: 'advisory.session_save', outcome: 'success', workbench: 'advisory', recordId: data.id, details: { mode, advisor_id: advisor_id ?? null } });

    return NextResponse.json({ ok: true, id: data.id, created_at: data.created_at });
  } catch (err) {
    console.error('[advisory-sessions POST] unhandled error:', err);
    await logActionHistory({ action: 'advisory.session_save', outcome: 'failed', workbench: 'advisory', details: { reason: 'exception' } });
    return NextResponse.json({ error: 'internal error' }, { status: 500 });
  }
}

// GET /api/advisory-sessions?mode=consult&advisor_id=xo&limit=50
export async function GET(req: NextRequest) {
  try {
    const session = await requireSession();
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = req.nextUrl;
    const mode      = searchParams.get('mode') as 'consult' | 'board' | null;
    const advisorId = searchParams.get('advisor_id');
    const limit     = Math.min(parseInt(searchParams.get('limit') ?? '100', 10), 200);

    const supabase = supabaseAdmin();
    let query = supabase
      .from('advisory_sessions')
      .select('id, created_at, mode, advisor_id, question, response, result')
      .order('created_at', { ascending: false })
      .limit(limit);

    if (mode)      query = query.eq('mode', mode);
    if (advisorId) query = query.eq('advisor_id', advisorId);

    const { data, error } = await query;
    if (error) {
      console.error('[advisory-sessions GET] query failed:', error);
      return NextResponse.json({ error: 'internal error' }, { status: 500 });
    }
    return NextResponse.json({ sessions: data ?? [] });
  } catch (err) {
    console.error('[advisory-sessions GET] unhandled error:', err);
    return NextResponse.json({ error: 'internal error' }, { status: 500 });
  }
}
