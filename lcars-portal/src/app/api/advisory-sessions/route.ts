import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

function getSupabase() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}

// POST /api/advisory-sessions — save a consult message or board result
export async function POST(req: NextRequest) {
  try {
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
      return NextResponse.json({ error: 'mode and question are required' }, { status: 400 });
    }
    if (mode === 'consult' && !response) {
      return NextResponse.json({ error: 'response is required for consult mode' }, { status: 400 });
    }
    if (mode === 'board' && !result) {
      return NextResponse.json({ error: 'result is required for board mode' }, { status: 400 });
    }

    const supabase = getSupabase();
    const { data, error } = await supabase
      .from('advisory_sessions')
      .insert({ mode, advisor_id: advisor_id ?? null, question, response: response ?? null, result: result ?? null, metadata: metadata ?? null })
      .select('id, created_at')
      .single();

    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ ok: true, id: data.id, created_at: data.created_at });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}

// GET /api/advisory-sessions?mode=consult&advisor_id=xo&limit=50
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = req.nextUrl;
    const mode      = searchParams.get('mode') as 'consult' | 'board' | null;
    const advisorId = searchParams.get('advisor_id');
    const limit     = Math.min(parseInt(searchParams.get('limit') ?? '100', 10), 200);

    const supabase = getSupabase();
    let query = supabase
      .from('advisory_sessions')
      .select('id, created_at, mode, advisor_id, question, response, result')
      .order('created_at', { ascending: false })
      .limit(limit);

    if (mode)      query = query.eq('mode', mode);
    if (advisorId) query = query.eq('advisor_id', advisorId);

    const { data, error } = await query;
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ sessions: data ?? [] });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
