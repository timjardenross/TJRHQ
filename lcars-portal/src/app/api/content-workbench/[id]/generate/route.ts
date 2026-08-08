// POST /api/content-workbench/[id]/generate — generate a draft for a
// Content Workbench opportunity that has completed research.
//
// This is a deliberate near-duplicate of /api/comms/generate/route.ts rather
// than a shared import or a modification of that route: comms-workbench's
// own "Generate Draft" button must keep working unchanged (an opportunity
// with no research brief is still valid there). The one behavioural
// difference is the research_completed_at gate below. System prompt, format
// lengths, and the LLM/scaffold-fallback behaviour are kept byte-identical
// on purpose — see the header comment there for why the fallback exists.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? 'https://ollama.com';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL_DEFAULT ?? 'glm-5.2';
const OLLAMA_API_KEY = process.env.OLLAMA_API_KEY ?? '';

const FORMAT_LENGTHS: Record<string, string> = {
  linkedin_post: '120–200 words, punchy, one idea, a hook and a closing question',
  executive_insight: '90–150 words, crisp, for senior leaders',
  lessons_learned: '150–220 words: situation, what happened, the durable lesson',
  case_study: '200–300 words: problem, approach, outcome, transferable lesson',
  industry_commentary: '150–220 words: the trend, your view, the implication',
  article_draft: '350–500 words, structured long-form with a clear thesis',
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

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const { format = 'linkedin_post' } = await req.json().catch(() => ({}));
    const id = params.id;

    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('id,title,pillar,notes,status,research_notes,research_angle,research_sources,research_completed_at')
      .eq('id', id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (row.status !== 'opportunity') {
      return NextResponse.json({ error: `Item is '${row.status}', not 'opportunity'` }, { status: 400 });
    }
    if (!row.research_completed_at) {
      return NextResponse.json(
        { error: 'Complete the research brief before generating a draft' },
        { status: 400 },
      );
    }

    const length = FORMAT_LENGTHS[format] ?? 'concise and professional';
    const system =
      'You are the Communications & Presence Officer for a senior professional. ' +
      'You write evidence-based, credible thought-leadership in a clear, grounded, ' +
      'first-person executive voice. Reputation over reach: no hype, no clickbait, ' +
      'no invented facts. The piece is an unpublished first draft the human will edit — ' +
      'never claim it is published.';
    const sources = Array.isArray(row.research_sources) && row.research_sources.length
      ? `\nSources:\n${row.research_sources.map((s: any) => `- ${s.label ?? s.url ?? s}`).join('\n')}\n`
      : '';
    const user =
      `Draft a ${format.replace(/_/g, ' ')} (${length}).\n\n` +
      `Topic: ${row.title}\n` +
      `Pillar: ${row.pillar ?? 'operational resilience'}\n` +
      (row.research_angle ? `Angle: ${row.research_angle}\n` : '') +
      (row.research_notes ? `Research brief: ${row.research_notes}\n` : '') +
      sources +
      '\nWrite the draft only — no preamble, no meta-commentary.';

    let generatedBody: string;
    let mode: 'llm' | 'scaffold';
    try {
      generatedBody = await callLLM(system, user);
      mode = 'llm';
    } catch (llmErr) {
      generatedBody =
        `[DRAFT SCAFFOLD — ${format.replace(/_/g, ' ').toUpperCase()}]\n\n` +
        `Topic: ${row.title}\n\n` +
        `Hook: [Open with a surprising fact or question about ${row.title}]\n\n` +
        `${row.research_angle ? `Angle: ${row.research_angle}\n\n` : ''}` +
        `${row.research_notes ? `Research brief: ${row.research_notes}\n\n` : ''}` +
        `Key insight: [The one thing readers should take away]\n\n` +
        `Evidence: [Ground it in the source — what actually happened or was published]\n\n` +
        `So what: [The implication for your audience — practitioners, leaders, or peers]\n\n` +
        `Close: [A question or provocation to drive comments]\n\n` +
        `[Scaffold generated — LLM unavailable: ${llmErr instanceof Error ? llmErr.message : 'unknown error'}]`;
      mode = 'scaffold';
    }

    const nowIso = new Date().toISOString();
    const { error: updateErr } = await sb
      .from('comms_content')
      .update({ body: generatedBody, draft_generated_at: nowIso, status: 'draft', updated_at: nowIso })
      .eq('id', id);
    if (updateErr) throw updateErr;

    // First revision row — the generated draft is revision 1, everything after
    // is a human edit tracked by /api/content-workbench/[id]/draft.
    await sb.from('comms_content_revisions').insert({ content_id: id, body: generatedBody, edited_by: mode === 'llm' ? 'ai_draft' : 'ai_scaffold' });

    return NextResponse.json({ success: true, mode, body: generatedBody });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
