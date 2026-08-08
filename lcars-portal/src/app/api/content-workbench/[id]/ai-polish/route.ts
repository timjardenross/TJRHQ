// POST /api/content-workbench/[id]/ai-polish — AI-proposed revision of the
// draft body, addressing whatever QA concerns are on file.
//
// Companion to ai-review/route.ts: that route only *flags* issues against
// the checklist, it never touches the draft. This route is the next step a
// human can reach for — "don't just tell me it's wrong, propose a fix" —
// but it still stops short of writing anything. It returns a suggested_body
// string; the Proofing UI shows it for review and only calls the existing
// PATCH /api/content-workbench/[id]/draft (unchanged, already revision-
// tracked) if the human clicks Apply. No new write path, no auto-apply —
// same "AI proposes, a person disposes" posture as ai-review and every
// governed status transition in this pipeline.

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireSession } from '@/lib/supabase-server';

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? 'https://ollama.com';
const OLLAMA_MODEL = process.env.OLLAMA_MODEL_DEFAULT ?? 'glm-5.2';
const OLLAMA_API_KEY = process.env.OLLAMA_API_KEY ?? '';

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
    // Optional free-text steer from the human ("tighten the close", "cut the
    // stat in paragraph 2") on top of whatever QA notes are on file.
    const { instructions } = await req.json().catch(() => ({ instructions: undefined }));

    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('id, title, body, status, qa_checklist, research_notes, research_sources')
      .eq('id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (!['review', 'approved'].includes(row.status)) {
      return NextResponse.json({ error: `Item is '${row.status}' — AI revision only applies during proofing` }, { status: 400 });
    }
    if (!row.body || !row.body.trim()) {
      return NextResponse.json({ error: 'No draft body to revise' }, { status: 400 });
    }

    const checklist = (row.qa_checklist ?? {}) as Record<string, unknown>;
    const concerns: string[] = [];
    for (const [key, noteKey] of [
      ['accuracy', 'accuracy_note'], ['brand_voice', 'brand_voice_note'],
      ['compliance', 'compliance_note'], ['links_checked', 'links_note'],
    ] as const) {
      if (checklist[key] === false && typeof checklist[noteKey] === 'string' && checklist[noteKey]) {
        concerns.push(`${key.replace(/_/g, ' ')}: ${checklist[noteKey]}`);
      }
    }
    if (typeof checklist.notes === 'string' && checklist.notes) concerns.push(`Reviewer note: ${checklist.notes}`);

    const sources = Array.isArray(row.research_sources) && row.research_sources.length
      ? `\nSources on file:\n${row.research_sources.map((s: any) => `- ${s.label ?? s.url ?? s}`).join('\n')}\n`
      : '';

    const system =
      'You revise thought-leadership drafts for a senior professional\'s LinkedIn / executive voice. ' +
      'Preserve the author\'s first-person voice, structure, and roughly the same length — this is a ' +
      'targeted revision, not a rewrite from scratch. Reputation over reach: no hype, no invented urgency. ' +
      'If a claim or statistic is not backed by the sources provided, either cut it, hedge it honestly ' +
      '("in my experience", "I\'d expect"), or attribute it to informed opinion rather than fact. ' +
      'Return ONLY the revised draft text — no preamble, no meta-commentary, no markdown fences, no diff markup.';
    const user =
      `Title: ${row.title}\n` +
      sources +
      (concerns.length ? `\nQA concerns to address:\n${concerns.map((c) => `- ${c}`).join('\n')}\n` : '') +
      (instructions ? `\nAdditional instruction from the reviewer: ${instructions}\n` : '') +
      (!concerns.length && !instructions ? '\nNo specific concerns on file — do a general tightening pass for accuracy hedging and brand voice.\n' : '') +
      `\nCurrent draft:\n${row.body}`;

    let suggestedBody: string;
    let mode: 'llm' | 'unavailable';
    try {
      suggestedBody = (await callLLM(system, user)).trim();
      if (!suggestedBody) throw new Error('Empty response');
      mode = 'llm';
    } catch (llmErr) {
      return NextResponse.json(
        { error: `AI revision unavailable: ${llmErr instanceof Error ? llmErr.message : 'unknown error'}` },
        { status: 502 },
      );
    }

    return NextResponse.json({ success: true, mode, suggested_body: suggestedBody, concerns });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
