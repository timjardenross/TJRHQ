// POST /api/comms/generate — generate an LLM draft for a comms_content opportunity.
// Body: { id: string, format?: string }
// Writes body + draft_generated_at to comms_content and advances status to 'draft'.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? 'https://ollama.com';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL_DEFAULT ?? 'glm-5.2';
const OLLAMA_API_KEY = process.env.OLLAMA_API_KEY ?? '';

const FORMAT_LENGTHS: Record<string, string> = {
  linkedin_post:       '120–200 words, punchy, one idea, a hook and a closing question',
  executive_insight:   '90–150 words, crisp, for senior leaders',
  lessons_learned:     '150–220 words: situation, what happened, the durable lesson',
  case_study:          '200–300 words: problem, approach, outcome, transferable lesson',
  industry_commentary: '150–220 words: the trend, your view, the implication',
  article_draft:       '350–500 words, structured long-form with a clear thesis',
};

function serviceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  );
}

async function callLLM(system: string, user: string): Promise<string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (OLLAMA_API_KEY) headers['Authorization'] = `Bearer ${OLLAMA_API_KEY}`;

  const res = await fetch(`${OLLAMA_BASE_URL}/api/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: OLLAMA_MODEL,
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user },
      ],
      stream: false,
    }),
    signal: AbortSignal.timeout(45_000),
  });
  if (!res.ok) throw new Error(`LLM error ${res.status}`);
  const data = await res.json();
  return data?.message?.content ?? data?.choices?.[0]?.message?.content ?? '';
}

export async function POST(req: NextRequest) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { id, format = 'linkedin_post' } = await req.json();
    if (!id) return NextResponse.json({ error: 'id required' }, { status: 400 });

    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('id,title,pillar,notes,status,signal_source_id')
      .eq('id', id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (row.status !== 'opportunity') {
      return NextResponse.json({ error: `Item is '${row.status}', not 'opportunity'` }, { status: 400 });
    }

    const length = FORMAT_LENGTHS[format] ?? 'concise and professional';
    const system =
      'You are the Communications & Presence Officer for a senior professional. ' +
      'You write evidence-based, credible thought-leadership in a clear, grounded, ' +
      'first-person executive voice. Reputation over reach: no hype, no clickbait, ' +
      'no invented facts. The piece is an unpublished first draft the human will edit — ' +
      'never claim it is published.';
    const user =
      `Draft a ${format.replace(/_/g, ' ')} (${length}).\n\n` +
      `Topic: ${row.title}\n` +
      `Pillar: ${row.pillar ?? 'operational resilience'}\n` +
      (row.notes ? `Context: ${row.notes}\n` : '') +
      '\nWrite the draft only — no preamble, no meta-commentary.';

    let body: string;
    let mode: 'llm' | 'scaffold';
    try {
      body = await callLLM(system, user);
      mode = 'llm';
    } catch (llmErr) {
      // Deterministic scaffold fallback
      body =
        `[DRAFT SCAFFOLD — ${format.replace(/_/g, ' ').toUpperCase()}]\n\n` +
        `Topic: ${row.title}\n\n` +
        `Hook: [Open with a surprising fact or question about ${row.title}]\n\n` +
        `${row.notes ? `Signal context: ${row.notes}\n\n` : ''}` +
        `Key insight: [The one thing readers should take away]\n\n` +
        `Evidence: [Ground it in the source — what actually happened or was published]\n\n` +
        `So what: [The implication for your audience — practitioners, leaders, or peers]\n\n` +
        `Close: [A question or provocation to drive comments]\n\n` +
        `[Scaffold generated — LLM unavailable: ${llmErr instanceof Error ? llmErr.message : 'unknown error'}]`;
      mode = 'scaffold';
    }

    const { error: updateErr } = await sb
      .from('comms_content')
      .update({
        body,
        draft_generated_at: new Date().toISOString(),
        status: 'draft',
        updated_at: new Date().toISOString(),
      })
      .eq('id', id);
    if (updateErr) throw updateErr;

    return NextResponse.json({ success: true, mode, body });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
