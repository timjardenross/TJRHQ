// #664 — shared CHAT_LOCAL_FIRST_V1 handler for /api/ai/chat and /api/xo. Only called when the flag is ON.
//
// Flow: validate the request shape (malformed → 400, never sent anywhere) → decide a route (local by default;
// cloud only for a validated intent) → cloud via the single choke point sendToCloud() (any cloud failure falls back to
// LOCAL, which is safe) or local via sendToLocal() (any local failure → 424; NEVER a cloud fallback).
// HEALTH_LLM_EXTERNAL_ALLOWED is not consulted anywhere on this path.
import { NextResponse } from 'next/server';
import { decideRoute, recordChatPrivacyEvent } from './chatPrivacy';
import { sendToCloud, sendToLocal, type LocalMessage } from './chatTransport';

export const LOCAL_UNAVAILABLE = 'local_model_unavailable';
export const LOCAL_UNAVAILABLE_MESSAGE =
  'The local model is unavailable, so this request was not sent anywhere. Number One\'s built-in commands still work; ' +
  'try again once the local model is back.';

export interface ChatMsg { role: 'user' | 'assistant' | 'system'; content: string; id?: string }

const MAX_MESSAGES = 100;
const MAX_TOTAL_CHARS = 200_000;

/** Strict request-shape validation. Returns null if malformed. */
export function validateMessages(raw: unknown): ChatMsg[] | null {
  if (!Array.isArray(raw) || raw.length === 0 || raw.length > MAX_MESSAGES) return null;
  let total = 0;
  const out: ChatMsg[] = [];
  for (const m of raw) {
    if (!m || typeof m !== 'object') return null;
    const { role, content, id } = m as Record<string, unknown>;
    if (role !== 'user' && role !== 'assistant' && role !== 'system') return null;
    if (typeof content !== 'string') return null;
    total += content.length;
    if (total > MAX_TOTAL_CHARS) return null;
    out.push({ role, content, ...(typeof id === 'string' ? { id } : {}) });
  }
  return out;
}

export interface LocalFirstOptions {
  messages: unknown;
  role: unknown;
  systemPrompt?: unknown;
  explicit?: { intent?: unknown; slot?: unknown } | null;
  stream: boolean;
  cloudModel: string;
  /** Builds the LOCAL system prompt (may include ship context — it never leaves this machine). */
  buildLocalSystem: () => Promise<string>;
  streamResponse: (upstream: Response) => Response;
  roleId: string;
}

export async function handleLocalFirstChat(opts: LocalFirstOptions, env: Record<string, string | undefined> = process.env): Promise<Response> {
  const messages = validateMessages(opts.messages);
  if (!messages) {
    recordChatPrivacyEvent('malformed');
    return NextResponse.json({ error: 'messages must be a non-empty array of {role, content}', code: 'invalid_messages' }, { status: 400 });
  }
  const lastUser = [...messages].reverse().find((m) => m.role === 'user');

  const decision = decideRoute(
    { role: opts.role, systemPrompt: opts.systemPrompt, lastUserContent: messages[messages.length - 1]?.role === 'user' ? lastUser?.content : null, explicit: opts.explicit },
    env,
  );
  recordChatPrivacyEvent(`decision_${decision.route}_${decision.reason}`);

  if (decision.route === 'cloud' && decision.candidate) {
    const sent = await sendToCloud({ intent: decision.candidate.intent, slot: decision.candidate.slot, model: opts.cloudModel, stream: opts.stream }, env);
    if (sent.ok) {
      recordChatPrivacyEvent('cloud_sent');
      return respond(sent.response, opts);
    }
    recordChatPrivacyEvent(`cloud_failed_${sent.reason}`); // falling back to LOCAL is always safe
  }

  let system: string;
  try {
    system = await opts.buildLocalSystem();
  } catch {
    system = '';
  }
  const localMessages: LocalMessage[] = [
    ...(system ? [{ role: 'system' as const, content: system }] : []),
    ...messages.filter((m) => m.role !== 'system').map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })),
  ];
  const local = await sendToLocal(localMessages, opts.stream, env);
  if (!local.ok) {
    recordChatPrivacyEvent(`local_failed_${local.reason}`);
    return NextResponse.json({ error: LOCAL_UNAVAILABLE_MESSAGE, code: LOCAL_UNAVAILABLE }, { status: 424 });
  }
  recordChatPrivacyEvent('local_sent');
  return respond(local.response, opts);
}

async function respond(upstream: Response, opts: LocalFirstOptions): Promise<Response> {
  if (opts.stream) return opts.streamResponse(upstream);
  try {
    const data = await upstream.json();
    return NextResponse.json({ content: data?.message?.content ?? '', model: 'local-first', role: opts.roleId });
  } catch {
    return NextResponse.json({ error: 'Model returned an unreadable response', code: 'bad_upstream' }, { status: 502 });
  }
}
