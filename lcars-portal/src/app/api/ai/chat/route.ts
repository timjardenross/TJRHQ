import { NextRequest, NextResponse } from 'next/server';
import { getRoleById } from '@/lib/ai-roles';
import { buildShipContext } from '@/lib/ai-context';
import { parseAndProposeActions } from '@/lib/ai-actions';
import { createSupabaseServerClient } from '@/lib/supabase-server';

// Ollama Cloud base URL — configurable without code changes
const OLLAMA_BASE_URL =
  process.env.OLLAMA_BASE_URL ?? 'https://ollama.com';

const DEFAULT_MODEL =
  process.env.OLLAMA_MODEL_DEFAULT ?? 'glm-5.2';

const TIMEOUT_MS = 60_000;

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  model?: string;
  role?: string;
  stream?: boolean;
}

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const apiKey = process.env.OLLAMA_API_KEY;
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`;
  }
  return headers;
}

async function callOllamaCloud(
  messages: ChatMessage[],
  model: string,
  stream: boolean
): Promise<Response> {
  const body = JSON.stringify({
    model,
    messages,
    stream,
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${OLLAMA_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: buildHeaders(),
      body,
      signal: controller.signal,
    });
    clearTimeout(timer);
    return res;
  } catch (err) {
    clearTimeout(timer);
    throw err;
  }
}

// ── Streaming handler ─────────────────────────────────────────────────────────

function streamOllamaResponse(upstream: Response): Response {
  const encoder = new TextEncoder();

  const readable = new ReadableStream({
    async start(controller) {
      const reader = upstream.body?.getReader();
      if (!reader) {
        controller.close();
        return;
      }

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
                controller.enqueue(
                  encoder.encode(`data: ${JSON.stringify({ token })}\n\n`)
                );
              }
              if (chunk?.done) {
                // MSN-0352: queues any starfleet-action blocks as governed
                // proposals in Decide before closing - never executes them.
                const actionResults = await parseAndProposeActions(fullText).catch(() => []);
                if (actionResults.length > 0) {
                  controller.enqueue(
                    encoder.encode(`data: ${JSON.stringify({ actions: actionResults })}\n\n`)
                  );
                }
                controller.enqueue(encoder.encode('data: [DONE]\n\n'));
                controller.close();
                return;
              }
            } catch {
              // partial JSON line — skip
            }
          }
        }
      } catch (err) {
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ error: 'Stream interrupted' })}\n\n`
          )
        );
      } finally {
        controller.close();
        reader.releaseLock();
      }
    },
  });

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}

// ── Route handler ─────────────────────────────────────────────────────────────

export async function POST(request: NextRequest) {
  const supabase = await createSupabaseServerClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  if (!process.env.OLLAMA_CLOUD_ENABLED || process.env.OLLAMA_CLOUD_ENABLED !== 'true') {
    return NextResponse.json(
      { error: 'AI Console is not enabled. Set OLLAMA_CLOUD_ENABLED=true in environment.' },
      { status: 503 }
    );
  }

  let body: ChatRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const { messages = [], model, role, stream = false, systemPrompt } = body as ChatRequest & { systemPrompt?: string };

  if (!messages.length) {
    return NextResponse.json({ error: 'messages array is required' }, { status: 400 });
  }

  // Use client-provided system prompt if supplied (user edited), else role preset
  const resolvedRole = getRoleById(role ?? 'chief_engineer');
  const resolvedModel = model ?? DEFAULT_MODEL;
  const basePrompt = systemPrompt?.trim() || resolvedRole.systemPrompt;

  let contextText = '';
  try {
    const ctx = await buildShipContext();
    contextText = ctx.text;
  } catch {
    /* context is best-effort */
  }

  const resolvedSystemPrompt = contextText
    ? `${basePrompt}\n\n${contextText}`
    : basePrompt;

  const fullMessages: ChatMessage[] = [
    { role: 'system', content: resolvedSystemPrompt },
    ...messages.filter((m) => m.role !== 'system'),
  ];

  try {
    const upstream = await callOllamaCloud(fullMessages, resolvedModel, stream);

    if (!upstream.ok) {
      const errorText = await upstream.text().catch(() => 'Unknown error');
      return NextResponse.json(
        { error: `Ollama Cloud returned ${upstream.status}`, detail: errorText },
        { status: upstream.status }
      );
    }

    if (stream) {
      return streamOllamaResponse(upstream);
    }

    // Non-streaming response
    const data = await upstream.json();
    const content = data?.message?.content ?? '';

    return NextResponse.json({ content, model: resolvedModel, role: resolvedRole.id });
  } catch (err: unknown) {
    const isTimeout = err instanceof Error && err.name === 'AbortError';
    return NextResponse.json(
      {
        error: isTimeout
          ? 'Request timed out — GLM 5.2 did not respond within 60 seconds'
          : 'Failed to reach Ollama Cloud',
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: isTimeout ? 504 : 502 }
    );
  }
}
