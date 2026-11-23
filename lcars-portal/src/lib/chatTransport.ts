// #664 — the ONLY places the local-first chat path talks to a model.
//
//  * sendToCloud()  — the single enforced cloud-send choke point. It accepts only a validated intent + slot, builds the
//    request itself from fixed server instructions, re-validates the exact serialized body immediately before the
//    fetch, and fails closed (returns {ok:false}) on any doubt. Nothing else under CHAT_LOCAL_FIRST_V1 may call the
//    cloud.
//  * sendToLocal()  — loopback-only local Ollama with a local (non-cloud-tagged) model. A failure is reported as
//    {ok:false}; callers must NEVER fall back to the cloud on it.
import { localOllamaTarget } from './personalHealthGuard';
import {
  CLOUD_SYSTEM_PROMPT, cloudUserContent, intentSlotEligible, type CloudIntent,
} from './chatPrivacy';

const LOOPBACK = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);
const CLOUD_TIMEOUT_MS = 60_000;
const DEFAULT_LOCAL_TIMEOUT_MS = 30_000;

export type SendFailure =
  | 'validation_failed' | 'cloud_not_configured' | 'cloud_unreachable' | 'cloud_timeout' | 'cloud_error_status'
  | 'local_not_configured' | 'local_unreachable' | 'local_timeout' | 'local_error_status' | 'gate_error';

export type SendResult = { ok: true; response: Response } | { ok: false; reason: SendFailure; status?: number };

export interface CloudRequestInput { intent: CloudIntent; slot: string; model: string; stream: boolean }

/** Resolve the cloud endpoint: must be https and NOT loopback/private-by-name. */
function cloudBase(env: Record<string, string | undefined>): string | null {
  const base = (env.OLLAMA_BASE_URL || 'https://ollama.com').replace(/\/+$/, '');
  try {
    const u = new URL(base);
    if (u.protocol !== 'https:') return null;
    if (LOOPBACK.has(u.hostname)) return null;
    return base;
  } catch {
    return null;
  }
}

/** Build the exact body that would be sent. Exported so tests assert the serialized payload. */
export function buildCloudBody(input: CloudRequestInput): string {
  return JSON.stringify({
    model: input.model,
    messages: [
      { role: 'system', content: CLOUD_SYSTEM_PROMPT[input.intent] },
      { role: 'user', content: cloudUserContent(input.intent, input.slot) },
    ],
    stream: input.stream,
  });
}

/** Re-validate a serialized body: exact shape, fixed system text, and a user text rebuilt from a valid slot. */
export function serializedCloudBodyIsClean(serialized: string, intent: CloudIntent, slot: string): boolean {
  try {
    const parsed = JSON.parse(serialized) as { model?: unknown; messages?: unknown; stream?: unknown };
    if (Object.keys(parsed).sort().join(',') !== 'messages,model,stream') return false;
    if (typeof parsed.model !== 'string' || !/^[\w.:/-]{1,80}$/.test(parsed.model)) return false;
    if (typeof parsed.stream !== 'boolean') return false;
    const msgs = parsed.messages as { role?: unknown; content?: unknown }[];
    if (!Array.isArray(msgs) || msgs.length !== 2) return false;
    if (msgs.some((m) => Object.keys(m).sort().join(',') !== 'content,role')) return false;
    if (msgs[0].role !== 'system' || msgs[0].content !== CLOUD_SYSTEM_PROMPT[intent]) return false;
    if (msgs[1].role !== 'user' || msgs[1].content !== cloudUserContent(intent, slot)) return false;
    return intentSlotEligible(intent, slot);
  } catch {
    return false;
  }
}

export async function sendToCloud(
  input: CloudRequestInput,
  env: Record<string, string | undefined> = process.env,
  fetchImpl: typeof fetch = fetch,
): Promise<SendResult> {
  try {
    if (env.OLLAMA_CLOUD_ENABLED !== 'true') return { ok: false, reason: 'cloud_not_configured' };
    const base = cloudBase(env);
    if (!base) return { ok: false, reason: 'cloud_not_configured' };
    if (!intentSlotEligible(input.intent, input.slot)) return { ok: false, reason: 'validation_failed' };
    const body = buildCloudBody(input);
    if (!serializedCloudBodyIsClean(body, input.intent, input.slot)) return { ok: false, reason: 'validation_failed' };

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (env.OLLAMA_API_KEY) headers['Authorization'] = `Bearer ${env.OLLAMA_API_KEY}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CLOUD_TIMEOUT_MS);
    try {
      const res = await fetchImpl(`${base}/api/chat`, { method: 'POST', headers, body, signal: controller.signal, redirect: 'error' });
      if (!res.ok) return { ok: false, reason: 'cloud_error_status', status: res.status };
      return { ok: true, response: res };
    } catch (err) {
      return { ok: false, reason: err instanceof Error && err.name === 'AbortError' ? 'cloud_timeout' : 'cloud_unreachable' };
    } finally {
      clearTimeout(timer);
    }
  } catch {
    return { ok: false, reason: 'gate_error' };
  }
}

export interface LocalMessage { role: 'system' | 'user' | 'assistant'; content: string }

export async function sendToLocal(
  messages: LocalMessage[],
  stream: boolean,
  env: Record<string, string | undefined> = process.env,
  fetchImpl: typeof fetch = fetch,
): Promise<SendResult> {
  try {
    const target = localOllamaTarget(env); // loopback host + non-cloud-tagged model, else null
    if (!target) return { ok: false, reason: 'local_not_configured' };
    const timeoutMs = Number(env.CHAT_LOCAL_TIMEOUT_MS) > 0 ? Number(env.CHAT_LOCAL_TIMEOUT_MS) : DEFAULT_LOCAL_TIMEOUT_MS;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs); // bounds time to first response, not the stream
    try {
      const res = await fetchImpl(`${target.baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: target.model, messages, stream }),
        signal: controller.signal,
        redirect: 'error',
      });
      if (!res.ok) return { ok: false, reason: 'local_error_status', status: res.status };
      if (!stream) {
        // Non-streaming: keep the deadline active until the whole body is read (a stalled body must time out, not hang).
        const text = await res.text();
        return { ok: true, response: new Response(text, { status: res.status, headers: res.headers }) };
      }
      return { ok: true, response: res };
    } catch (err) {
      return { ok: false, reason: err instanceof Error && err.name === 'AbortError' ? 'local_timeout' : 'local_unreachable' };
    } finally {
      clearTimeout(timer);
    }
  } catch {
    return { ok: false, reason: 'gate_error' };
  }
}
