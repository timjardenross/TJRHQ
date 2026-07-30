import { NextRequest, NextResponse } from 'next/server';
import { getRoleById } from '@/lib/ai-roles';
import { buildShipContext } from '@/lib/ai-context';
import { parseAndProposeActions } from '@/lib/ai-actions';
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
- Where a governance boundary applies (GitHub writes, deployments, closing missions), flag it plainly for Captain decision.
- When the Captain approves an action you CAN perform (log a mission, create a handoff, log a decision), emit the starfleet-action block immediately — the system executes it.
- ALWAYS end your reply with exactly one line beginning "→ Next action:" naming the single most useful next step (e.g. capture a mission, review the engineering queue, rest, log a check-in).
`.trim();

async function callOllama(messages: ChatMessage[], model: string, stream: boolean): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.OLLAMA_API_KEY) headers['Authorization'] = `Bearer ${process.env.OLLAMA_API_KEY}`;
  try {
    return await fetch(`${OLLAMA_BASE_URL}/api/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ model, messages, stream }),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

function streamXOResponse(upstream: Response): Response {
  const encoder = new TextEncoder();
  const readable = new ReadableStream({
    async start(controller) {
      const reader = upstream.body?.getReader();
      if (!reader) { controller.close(); return; }
      const decoder = new TextDecoder();
      let lineBuffer = '';
      let fullText = '';
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          lineBuffer += decoder.decode(value, { stream: true });
          const lines = lineBuffer.split('\n');
          lineBuffer = lines.pop() ?? '';
          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const chunk = JSON.parse(line);
              const token = chunk?.message?.content ?? '';
              if (token) {
                fullText += token;
                controller.enqueue(encoder.encode(`data: ${JSON.stringify({ token })}\n\n`));
              }
              if (chunk?.done) {
                // MSN-0352: queues any starfleet-action blocks as governed
                // proposals in Decide before closing - never executes them.
                const actionResults = await parseAndProposeActions(fullText).catch(() => []);
                if (actionResults.length > 0) {
                  controller.enqueue(encoder.encode(`data: ${JSON.stringify({ actions: actionResults })}\n\n`));
                }
                controller.enqueue(encoder.encode('data: [DONE]\n\n'));
                controller.close();
                return;
              }
            } catch { /* partial JSON line */ }
          }
        }
      } catch {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ error: 'Stream interrupted' })}\n\n`));
      } finally {
        controller.close();
        reader.releaseLock();
      }
    },
  });
  return new Response(readable, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' },
  });
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
    const upstream = await callOllama(fullMessages, body.model ?? DEFAULT_MODEL, true);
    if (!upstream.ok) {
      const detail = await upstream.text().catch(() => 'Unknown error');
      return NextResponse.json(
        { error: `XO model returned ${upstream.status}`, detail },
        { status: upstream.status },
      );
    }
    return streamXOResponse(upstream);
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
