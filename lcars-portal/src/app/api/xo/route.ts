import { NextRequest, NextResponse } from 'next/server';
import { getRoleById } from '@/lib/ai-roles';
import { buildShipContext } from '@/lib/ai-context';
import { createSupabaseServerClient } from '@/lib/supabase-server';

/**
 * XO Chat endpoint (MSN-IOS-001 WP4).
 *
 * Reuse-first: same Ollama Cloud upstream and env flags as /api/ai/chat, and
 * the SAME existing ship-context builder (lib/ai-context.buildShipContext) the
 * AI Console uses — so XO already knows missions, decisions, health, knowledge
 * and command memory without the Captain pasting anything.
 *
 * XO is steered to translate intent into the NEXT useful action (not to merely
 * resurface information): it answers briefly, then ends with a single
 * "→ Next action:" line the mobile UI turns into a one-tap affordance.
 */

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL ?? 'https://ollama.com';
const DEFAULT_MODEL = process.env.OLLAMA_MODEL_DEFAULT ?? 'glm-5.2';
const TIMEOUT_MS = 60_000;

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

const XO_MOBILE_DOCTRINE = `
MOBILE XO MODE — Captain TJR is on a phone and likely time-poor or tired.
- Be brief. Lead with the answer. No preamble, no restating the question.
- Use the LIVE SHIP CONTEXT below; do not ask for information it already contains.
- Do not simply resurface data — translate intent into the next useful action.
- Where an approval or governance boundary applies, say so plainly and flag it for Captain decision (you are advisory; the Captain decides).
- ALWAYS end your reply with exactly one line beginning "→ Next action:" naming the single most useful next step (e.g. capture a mission, review the engineering queue, rest, log a check-in).
`.trim();

async function callOllama(messages: ChatMessage[], model: string): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.OLLAMA_API_KEY) headers['Authorization'] = `Bearer ${process.env.OLLAMA_API_KEY}`;
  try {
    return await fetch(`${OLLAMA_BASE_URL}/api/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ model, messages, stream: false }),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(request: NextRequest) {
  const supabase = await createSupabaseServerClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  if (process.env.OLLAMA_CLOUD_ENABLED !== 'true') {
    return NextResponse.json(
      {
        error: 'XO model is not enabled. Set OLLAMA_CLOUD_ENABLED=true. You can still route and capture from the XO screen.',
        code: 'model_disabled',
      },
      { status: 503 },
    );
  }

  let body: { messages?: ChatMessage[]; model?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const messages = body.messages ?? [];
  if (!messages.length) {
    return NextResponse.json({ error: 'messages array is required' }, { status: 400 });
  }

  // Live ship context (reused) + XO role + mobile doctrine.
  let contextText = '';
  let sources: string[] = [];
  try {
    const ctx = await buildShipContext();
    contextText = ctx.text;
    sources = ctx.sources;
  } catch {
    /* context is best-effort */
  }

  const xo = getRoleById('xo');
  const systemPrompt = [xo.systemPrompt, XO_MOBILE_DOCTRINE, contextText].filter(Boolean).join('\n\n');

  const fullMessages: ChatMessage[] = [
    { role: 'system', content: systemPrompt },
    ...messages.filter((m) => m.role !== 'system'),
  ];

  try {
    const upstream = await callOllama(fullMessages, body.model ?? DEFAULT_MODEL);
    if (!upstream.ok) {
      const detail = await upstream.text().catch(() => 'Unknown error');
      return NextResponse.json(
        { error: `XO model returned ${upstream.status}`, detail },
        { status: upstream.status },
      );
    }
    const data = await upstream.json();
    const content = data?.message?.content ?? '';
    return NextResponse.json({ content, sources });
  } catch (err: unknown) {
    const isTimeout = err instanceof Error && err.name === 'AbortError';
    return NextResponse.json(
      {
        error: isTimeout ? 'XO timed out (60s).' : 'Failed to reach the XO model.',
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: isTimeout ? 504 : 502 },
    );
  }
}
