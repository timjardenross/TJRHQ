// HQ Ask. Connects to EXISTING capabilities only, in this order:
//   1. Retrieval over HQ data (lib/ask.ts answerQuery): zero cost, no model, shows what it is based on.
//   2. The existing AI Console chat (POST /api/ai/chat, streaming, role "general"): the same service
//      the Advisory Consult screen uses, with its own personal-health veto and its governed action
//      proposals (queued for approval in Decisions, never executed).
//   3. The existing Advisory service (POST /api/advisory, action "advice") for "should we..." questions.
// HQ adds no AI backend and no context store. It never sends a system prompt, a model override, a
// local-only role, or anything personal.
import { answerQuery, type AskSourceStat } from '@/lib/ask';

export type AskMode = 'answer' | 'advice';

export interface AskProposal { type: string; success: boolean; detail: string; id?: string }

export type AskResult =
  | { kind: 'answer'; via: 'retrieval' | 'model' | 'advice'; text: string; basedOn: AskSourceStat[]; proposals: AskProposal[]; notes: string[] }
  | { kind: 'unavailable'; reason: string }
  | { kind: 'refused'; reason: string }
  | { kind: 'error'; reason: string };

export interface SseEvent { token?: string; actions?: AskProposal[]; error?: string; done?: boolean }

/** Incremental parser for the chat service's SSE stream (`data: {...}` lines, `data: [DONE]`). */
export function createSseParser(onEvent: (e: SseEvent) => void) {
  let buf = '';
  const decoder = new TextDecoder();
  return {
    push(chunk: Uint8Array | string) {
      buf += typeof chunk === 'string' ? chunk : decoder.decode(chunk, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') { onEvent({ done: true }); continue; }
        try { onEvent(JSON.parse(payload) as SseEvent); } catch { /* skip a malformed line */ }
      }
    },
  };
}

export async function readSse(body: ReadableStream<Uint8Array>, onEvent: (e: SseEvent) => void): Promise<void> {
  const reader = body.getReader();
  const parser = createSseParser(onEvent);
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(value);
  }
}

/** Map a non-OK chat response onto what the person should be told. Never throws. */
export async function classifyChatFailure(res: Response): Promise<AskResult> {
  const body = (await res.json().catch(() => null)) as { error?: string; code?: string } | null;
  if (res.status === 401) return { kind: 'unavailable', reason: 'You are signed out. Sign in again to ask.' };
  if (res.status === 503) return { kind: 'unavailable', reason: 'Ask is not switched on for this environment (the AI Console is disabled).' };
  if (res.status === 422 && body?.code === 'personal_health_blocked') {
    return { kind: 'refused', reason: body.error ?? 'This looks like personal health information, which is never sent to the cloud model. HQ does not handle it.' };
  }
  if (res.status === 424) return { kind: 'unavailable', reason: body?.error ?? 'The local model is unavailable, so nothing was sent anywhere.' };
  if (res.status === 429) return { kind: 'unavailable', reason: 'Too many questions. Try again in a minute.' };
  if (res.status === 502 || res.status === 504) return { kind: 'unavailable', reason: 'The model did not answer in time. Try again.' };
  return { kind: 'error', reason: body?.error ?? `Ask failed (HTTP ${res.status}).` };
}

async function viaModel(question: string, onToken: (t: string) => void, signal?: AbortSignal): Promise<AskResult> {
  let res: Response;
  try {
    res = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // role "general" only. No systemPrompt, no model override, no history of other screens.
      body: JSON.stringify({ role: 'general', stream: true, messages: [{ role: 'user', content: question }] }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return { kind: 'error', reason: 'Cancelled.' };
    return { kind: 'unavailable', reason: 'Could not reach the answer service.' };
  }
  if (!res.ok) return classifyChatFailure(res);
  if (!res.body) return { kind: 'error', reason: 'The service returned no answer.' };
  let text = '';
  let proposals: AskProposal[] = [];
  let streamError: string | null = null;
  await readSse(res.body, (e) => {
    if (e.token) { text += e.token; onToken(text); }
    if (e.actions?.length) proposals = e.actions;
    if (e.error) streamError = e.error;
  });
  if (!text && streamError) return { kind: 'error', reason: streamError };
  const notes = [
    'Answered by the AI Console from missions, decisions, the build queue and knowledge titles. It does not read intelligence feeds directly.',
    ...(streamError ? ['The answer was interrupted and may be incomplete.'] : []),
  ];
  return { kind: 'answer', via: 'model', text: text || '(no response)', basedOn: [], proposals, notes };
}

interface AdviceResult {
  executive_summary?: string; recommendation?: string; risks_and_challenges?: string[]; sources?: unknown[]; degraded?: boolean; advisory_note?: string;
}

async function viaAdvice(question: string): Promise<AskResult> {
  let res: Response;
  try {
    res = await fetch('/api/advisory', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'advice', question }) });
  } catch {
    return { kind: 'unavailable', reason: 'Could not reach the advisory service.' };
  }
  if (res.status === 401) return { kind: 'unavailable', reason: 'You are signed out. Sign in again to ask.' };
  if (res.status === 503) return { kind: 'unavailable', reason: 'The advisory service is not reachable from this environment.' };
  if (!res.ok) return { kind: 'error', reason: `Advice failed (HTTP ${res.status}).` };
  const json = (await res.json().catch(() => null)) as { result?: AdviceResult } | null;
  const r = json?.result;
  if (!r) return { kind: 'error', reason: 'The advisory service returned nothing usable.' };
  const lines = [r.executive_summary, r.recommendation ? `Recommendation: ${r.recommendation}` : null, ...(r.risks_and_challenges?.length ? ['Risks: ' + r.risks_and_challenges.join('; ')] : [])].filter(Boolean);
  const notes = [
    ...(r.degraded ? ['Degraded: based on historical evidence only.' + (r.advisory_note ? ` ${r.advisory_note}` : '')] : []),
    'Advice is a recommendation only. Acting on it still goes through Decisions.',
  ];
  return { kind: 'answer', via: 'advice', text: lines.join('\n\n') || '(no advice returned)', basedOn: [], proposals: [], notes };
}

export async function askHq(
  question: string,
  opts: { mode?: AskMode; context?: string | null; onToken?: (text: string) => void; signal?: AbortSignal } = {},
): Promise<AskResult> {
  const q = question.trim();
  if (!q) return { kind: 'error', reason: 'Type a question first.' };
  if (opts.mode === 'advice') return viaAdvice(q);

  // 1. Retrieval first: free, no model, and it says what it is based on.
  try {
    const a = await answerQuery(q);
    if (a.matched) return { kind: 'answer', via: 'retrieval', text: a.prose, basedOn: a.basedOn, proposals: [], notes: [] };
  } catch { /* fall through to the model */ }

  // 2. Otherwise the existing AI Console. A viewing context (an item title) is added as plain text only.
  const asked = opts.context ? `${q}\n\n(Context: I am looking at “${opts.context}” in HQ.)` : q;
  return viaModel(asked, opts.onToken ?? (() => {}), opts.signal);
}
