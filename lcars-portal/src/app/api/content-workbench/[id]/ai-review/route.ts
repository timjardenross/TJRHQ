// POST /api/content-workbench/[id]/ai-review — AI-assisted first pass over
// the Proofing QA checklist (accuracy / brand_voice / compliance /
// links_checked).
//
// This does NOT write to comms_content. It's advisory only: the LLM reads
// the draft and returns a suggested checklist + notes, which the Proofing
// UI pre-fills into the (still fully editable, still human-submitted)
// checklist form. Saving the checklist is still a separate, explicit
// PATCH /api/content-workbench/[id]/qa call the human makes — same as
// every other governed step in this pipeline, the AI proposes, a person
// disposes. Same callLLM/scaffold-fallback pattern as
// /api/content-workbench/[id]/generate, so a down LLM degrades to "run the
// checklist yourself" instead of blocking the page.

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

interface AiReview {
  accuracy: boolean | null;
  accuracy_note: string;
  brand_voice: boolean | null;
  brand_voice_note: string;
  compliance: boolean | null;
  compliance_note: string;
  links_checked: boolean | null;
  links_note: string;
  overall_notes: string;
}

const EMPTY_REVIEW: AiReview = {
  accuracy: null, accuracy_note: '',
  brand_voice: null, brand_voice_note: '',
  compliance: null, compliance_note: '',
  links_checked: null, links_note: '',
  overall_notes: 'AI review unavailable — work through the checklist manually.',
};

function parseReview(raw: string): AiReview {
  // Model may wrap JSON in a markdown fence despite instructions — strip it.
  const match = raw.match(/\{[\s\S]*\}/);
  if (!match) throw new Error('No JSON object in LLM response');
  const parsed = JSON.parse(match[0]);
  const asBool = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null);
  const asStr = (v: unknown): string => (typeof v === 'string' ? v.slice(0, 500) : '');
  return {
    accuracy: asBool(parsed.accuracy), accuracy_note: asStr(parsed.accuracy_note),
    brand_voice: asBool(parsed.brand_voice), brand_voice_note: asStr(parsed.brand_voice_note),
    compliance: asBool(parsed.compliance), compliance_note: asStr(parsed.compliance_note),
    links_checked: asBool(parsed.links_checked), links_note: asStr(parsed.links_note),
    overall_notes: asStr(parsed.overall_notes),
  };
}

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await requireSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const sb = serviceClient();
    const { data: row, error: fetchErr } = await sb
      .from('comms_content')
      .select('id, title, pillar, body, status, research_notes, research_sources')
      .eq('id', params.id)
      .single();
    if (fetchErr || !row) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    if (!['review', 'approved'].includes(row.status)) {
      return NextResponse.json({ error: `Item is '${row.status}' — AI review only applies during proofing` }, { status: 400 });
    }
    if (!row.body || !row.body.trim()) {
      return NextResponse.json({ error: 'No draft body to review' }, { status: 400 });
    }

    const system =
      'You are a meticulous editorial QA reviewer for a senior professional\'s LinkedIn / thought-leadership ' +
      'content. You check four things and ONLY these four: (1) accuracy — are claims plausible and not ' +
      'obviously fabricated or overstated given the stated sources/notes; (2) brand_voice — reputation over ' +
      'reach: grounded, first-person, no hype, no clickbait, no invented urgency; (3) compliance — no exposure ' +
      'of sensitive workplace detail, named clients, patients, or health information; (4) links_checked — ' +
      'flag if the draft references a link, source, or stat that is NOT backed by the provided research notes ' +
      '(you cannot browse, so treat unbacked specifics as a fail). Be skeptical, not generous — this is a ' +
      'first pass a human reviews and can overrule, not a final verdict. ' +
      'Respond with ONLY a JSON object, no markdown fences, no preamble: ' +
      '{"accuracy": true|false, "accuracy_note": "...", "brand_voice": true|false, "brand_voice_note": "...", ' +
      '"compliance": true|false, "compliance_note": "...", "links_checked": true|false, "links_note": "...", ' +
      '"overall_notes": "one or two sentence summary"}';

    const sources = Array.isArray(row.research_sources) && row.research_sources.length
      ? `\nSources on file:\n${row.research_sources.map((s: any) => `- ${s.label ?? s.url ?? s}`).join('\n')}\n`
      : '\nNo sources on file.\n';
    const user =
      `Title: ${row.title}\n` +
      `Pillar: ${row.pillar ?? 'unspecified'}\n` +
      (row.research_notes ? `Research brief: ${row.research_notes}\n` : '') +
      sources +
      `\nDraft:\n${row.body}`;

    let review: AiReview;
    let mode: 'llm' | 'scaffold';
    try {
      const raw = await callLLM(system, user);
      review = parseReview(raw);
      mode = 'llm';
    } catch (llmErr) {
      review = { ...EMPTY_REVIEW, overall_notes: `AI review unavailable (${llmErr instanceof Error ? llmErr.message : 'unknown error'}) — check manually.` };
      mode = 'scaffold';
    }

    return NextResponse.json({ success: true, mode, review });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: detail }, { status: 500 });
  }
}
