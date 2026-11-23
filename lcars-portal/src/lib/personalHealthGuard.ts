// Personal-health guard for the LCARS portal server routes (follow-up to #661).
//
// Rule: the Captain's capacity / pain / recovery data is processed on this machine only. Routes that carry it
// call generatePersonalHealthText(): it tries the LOCAL Ollama model (loopback only) and otherwise returns null,
// so the caller falls back to its deterministic text. The external Gemini -> Mistral chain runs only on an
// explicit opt-in (HEALTH_LLM_EXTERNAL_ALLOWED=1), exactly like the Python policy in
// core/security/personal_data_policy.py. Fail closed: a non-loopback URL, a cloud-hosted model tag or any error
// yields null, never a cloud call.
//
// personal_health_patterns.json is a verbatim copy of core/security/personal_health_patterns.json (the portal's
// build root is lcars-portal/, so it cannot import from the parent). A test asserts the two stay identical.
import patterns from './personal_health_patterns.json';

const TRUE_VALUES = ['1', 'true', 'yes', 'on'];
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);
const LOCAL_TIMEOUT_MS = 20_000;

export function externalHealthAiAllowed(env: Record<string, string | undefined> = process.env): boolean {
  return TRUE_VALUES.includes((env.HEALTH_LLM_EXTERNAL_ALLOWED ?? '').trim().toLowerCase());
}

const STRUCTURED = patterns.structured.map((p) => ({ name: p.name, rx: new RegExp(p.regex, 'i') }));
const FREE_TEXT = patterns.conservative_free_text.map((r) => new RegExp(r, 'i'));

/** Conservative content check for free text (used where a route cannot know the content is personal). */
export function assessPersonalHealthText(...texts: string[]): { personal: boolean; reasons: string[] } {
  try {
    const hay = texts.filter(Boolean).join('\n');
    const reasons = STRUCTURED.filter((p) => p.rx.test(hay)).map((p) => p.name);
    if (FREE_TEXT.some((rx) => rx.test(hay))) reasons.push('free_text_health_term');
    return { personal: reasons.length > 0, reasons };
  } catch {
    return { personal: true, reasons: ['detector_unavailable'] };
  }
}

/** Structured-forms-only check (no broad lexicon): for free chat where ordinary words like "recovery" or "capacity" are common. */
export function containsStructuredPersonalHealth(...texts: string[]): string[] {
  try {
    const hay = texts.filter(Boolean).join('\n');
    return STRUCTURED.filter((p) => p.rx.test(hay)).map((p) => p.name);
  } catch {
    return ['detector_unavailable'];
  }
}

/** Drop any line that matches a structured personal-health form (defence in depth for assembled prompt context). */
export function scrubPersonalHealthLines(text: string): string {
  return text.split('\n').filter((line) => containsStructuredPersonalHealth(line).length === 0).join('\n');
}

/**
 * Cloud chat routes: user-supplied text that carries structured personal health content is refused before any
 * upstream call unless the Captain has opted in. Returns the reasons (empty = fine).
 */
export function personalHealthBlockedReasons(
  texts: string[],
  env: Record<string, string | undefined> = process.env,
): string[] {
  if (externalHealthAiAllowed(env)) return [];
  return containsStructuredPersonalHealth(...texts);
}

export const PERSONAL_HEALTH_CLOUD_REFUSAL =
  'This message looks like personal health information, which is never sent to the cloud model. ' +
  'Use the local tools (Human Systems, Pain Recovery Studio) for health questions.';

export function localOllamaTarget(
  env: Record<string, string | undefined> = process.env,
): { baseUrl: string; model: string } | null {
  const baseUrl = (env.OLLAMA_LOCAL_BASE_URL || 'http://127.0.0.1:11434').replace(/\/+$/, '');
  const model = (env.OLLAMA_LOCAL_MODEL || 'qwen3:8b').trim();
  try {
    const u = new URL(baseUrl);
    if (!LOOPBACK_HOSTS.has(u.hostname)) return null;           // the model must run on this machine
  } catch {
    return null;
  }
  if (/(:cloud|-cloud)$/i.test(model)) return null;             // cloud-hosted tags are proxied off this machine
  return { baseUrl, model };
}

export async function generateLocalOnly(
  system: string,
  prompt: string,
  opts: { json?: boolean; maxTokens?: number; timeoutMs?: number } = {},
  env: Record<string, string | undefined> = process.env,
): Promise<string | null> {
  const target = localOllamaTarget(env);
  if (!target) return null;
  try {
    const res = await fetch(`${target.baseUrl}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: target.model,
        stream: false,
        ...(opts.json ? { format: 'json' } : {}),
        messages: [{ role: 'system', content: system }, { role: 'user', content: prompt }],
        options: { temperature: 0.3, num_predict: opts.maxTokens ?? 512 },
      }),
      signal: AbortSignal.timeout(opts.timeoutMs ?? LOCAL_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return (data?.message?.content as string | undefined)?.trim() || null;
  } catch {
    return null;
  }
}

/**
 * Local model first. The external chain is invoked only when the Captain has explicitly opted in. Returns null
 * when nothing may or can answer: the caller must then use its deterministic fallback.
 */
export async function generatePersonalHealthText(
  system: string,
  prompt: string,
  opts: { json?: boolean; maxTokens?: number } = {},
  externalChain?: () => Promise<string | null>,
  env: Record<string, string | undefined> = process.env,
): Promise<string | null> {
  const local = await generateLocalOnly(system, prompt, opts, env);
  if (local) return local;
  if (externalHealthAiAllowed(env) && externalChain) return externalChain();
  return null;
}
