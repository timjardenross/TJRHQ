// #664 — local-first privacy boundary for the cloud chat callers (V11d, intent based).
//
// Rule: nothing is sent to the cloud model unless it is one of three narrow, explicitly validated INTENTS
// (explain_concept, explain_error, summarise_log). The cloud request is built ONLY from a fixed server-side
// instruction plus the validated slot. Conversation history, client system prompts, ship context and draft prose
// are never part of it. Everything else — free chat, mixed, ambiguous, malformed, unknown — stays local.
//
// Eligibility is a closed allowlist, not a health-content classifier: a slot is cloud-eligible only if every line
// matches a log/stack-trace grammar and every word is in a closed technical vocabulary (chatPrivacy.vocab.json,
// generated from the offline-evaluated V11d gate). A vocabulary gap therefore makes a payload ineligible (local),
// it cannot let an unknown word through. The existing personal-health patterns and a health-stem deny list are
// applied on top as a veto.
//
// Gated by CHAT_LOCAL_FIRST_V1 (default OFF). Nothing here runs when the flag is off.
import vocab from './chatPrivacy.vocab.json';
import { assessPersonalHealthText } from './personalHealthGuard';

const TRUE_VALUES = ['1', 'true', 'yes', 'on'];

export function chatLocalFirstEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return TRUE_VALUES.includes((env.CHAT_LOCAL_FIRST_V1 ?? '').trim().toLowerCase());
}

export type CloudIntent = 'explain_concept' | 'explain_error' | 'summarise_log';

const CONCEPTS = new Set<string>(vocab.concepts);
const TECH = new Set<string>(vocab.tech);
const FUNC = new Set<string>(vocab.func);
const VERBS = new Set<string>(vocab.verbs);
const ORGS = new Set<string>(vocab.orgs);
const LOGVOCAB = new Set<string>(vocab.logvocab);
const SHORT_OK = new Set<string>(vocab.shortOk);
const TECHKEYS = new Set<string>(vocab.techKeys);
const DENY = new RegExp(vocab.deny, 'i');

const MAX_SLOT_CHARS = 8000;
const MAX_SLOT_LINES = 60;

function stems(word: string): string[] {
  const w = word.toLowerCase();
  const out = new Set<string>([w]);
  for (const suf of ['ing', 'ed', 'es', 's', 'ly']) {
    if (w.endsWith(suf) && w.length - suf.length >= 3) {
      out.add(w.slice(0, -suf.length));
      out.add(w.slice(0, -suf.length) + 'e');
    }
  }
  return [...out];
}

function subwords(tok: string): string[] {
  const cleaned = tok.replace(/[_\-./]/g, ' ');
  return (cleaned.match(/[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+/g) ?? []).map((w) => w.toLowerCase());
}

function subOk(w: string): boolean {
  if (DENY.test(w)) return false;
  if (TECH.has(w) || FUNC.has(w) || VERBS.has(w) || ORGS.has(w) || LOGVOCAB.has(w) || SHORT_OK.has(w)) return true;
  if (/^\d+$/.test(w)) return true;
  return stems(w).some((x) => TECH.has(x) || FUNC.has(x) || LOGVOCAB.has(x));
}

function hasTech(msg: string): boolean {
  if (/\d/.test(msg)) return true;
  const toks = msg.match(/[A-Za-z_][A-Za-z0-9_.\-/]*/g) ?? [];
  return toks.some((t) =>
    subwords(t).some(
      (w) => w.length > 2 && !FUNC.has(w) && !SHORT_OK.has(w) && stems(w).some((x) => TECH.has(x) || LOGVOCAB.has(x)),
    ),
  );
}

function kvValueOk(v: string): boolean {
  if (/^\d+(?:\.\d+)*(?:ms|s|sec|min|kb|mb|gb|%|x)?$/i.test(v)) return true;
  if (!/^[\w.\-/:]+$/.test(v)) return false;
  return subwords(v).every(subOk);
}

function msgOk(rawMsg: string): boolean {
  // quoted multi-word text is free text
  if (/['"][^'"]*\s[^'"]*['"]/.test(rawMsg)) return false;
  let kvBad = false;
  let kvOk = false;
  const msg = rawMsg.replace(/\b([A-Za-z_]+)=(\S+)/g, (_m, k: string, v: string) => {
    if (TECHKEYS.has(k.toLowerCase()) && kvValueOk(v)) {
      kvOk = true;
      return ' KVOK ';
    }
    kvBad = true;
    return ' KVBAD ';
  });
  if (kvBad) return false;
  if (!hasTech(msg) && !kvOk) return false;
  const toks = msg.match(/[A-Za-z_][A-Za-z0-9_.\-/]*/g) ?? [];
  for (const tok of toks) {
    if (tok === 'KVOK') continue;
    if (!subwords(tok).every(subOk)) return false;
  }
  return true;
}

const LEVEL = '(?:INFO|WARN|WARNING|ERROR|DEBUG|CRITICAL)';
const LINE_GRAMMARS: { rx: RegExp; groups: string[] }[] = [
  { rx: new RegExp(`^\\d{4}-\\d\\d-\\d\\d[T ][\\d:.]+Z?\\s+${LEVEL}\\s+[\\w.-]+:\\s+(.*)$`), groups: ['msg'] },
  { rx: /^\s*at\s+([\w.$<>[\]/-]+)\s*\(([^)]*)\)\s*$/, groups: ['fn', 'msg'] },
  { rx: /^Traceback \(most recent call last\):\s*$/, groups: [] },
  { rx: /^\s*File "[^"]+", line \d+, in (\w+)\s*$/, groups: ['msg'] },
  { rx: /^([A-Za-z]+(?:Error|Exception)): (.*)$/, groups: ['msg', 'm2'] },
];

function sensitiveVeto(text: string): boolean {
  try {
    return assessPersonalHealthText(text).personal || DENY.test(text);
  } catch {
    return true; // fail closed
  }
}

/** True only if the whole text is a log / stack-trace artifact built from closed grammar and vocabulary. */
export function artifactEligible(text: unknown): boolean {
  try {
    if (typeof text !== 'string' || text.length === 0 || text.length > MAX_SLOT_CHARS) return false;
    if (!/^[\x20-\x7E\n\t]*$/.test(text)) return false; // printable ASCII only: no homoglyph / hidden-character tricks
    const lines = text.split('\n').filter((l) => l.trim());
    if (lines.length === 0 || lines.length > MAX_SLOT_LINES) return false;
    for (const line of lines) {
      if (sensitiveVeto(line)) return false;
      let matched = false;
      for (const g of LINE_GRAMMARS) {
        const m = g.rx.exec(line);
        if (!m) continue;
        matched = true;
        for (let i = 0; i < g.groups.length; i++) {
          const v = m[i + 1];
          if (v && !msgOk(v)) return false;
        }
        break;
      }
      if (!matched) return false;
    }
    return !sensitiveVeto(text);
  } catch {
    return false;
  }
}

export function conceptEligible(slot: unknown): boolean {
  return typeof slot === 'string' && CONCEPTS.has(slot.trim().toLowerCase());
}

/** Validate one (intent, slot). Unknown intent or any exception → false. */
export function intentSlotEligible(intent: unknown, slot: unknown): boolean {
  try {
    if (intent === 'explain_concept') return conceptEligible(slot);
    if (intent === 'explain_error' || intent === 'summarise_log') return artifactEligible(slot);
    return false;
  } catch {
    return false;
  }
}

const CONCEPT_ASK = /^\s*(?:what\s+is|what's|explain|define)\s+(?:an?\s+|the\s+)?(.+?)\s*\??\s*$/i;

export interface CloudIntentCandidate { intent: CloudIntent; slot: string }

/**
 * Derive a cloud intent from the LAST user message only, and only when the whole message is an explicit concept
 * question or a bare artifact. Anything else (prose, mixed, instructions around an artifact) → null (local).
 */
export function deriveIntent(lastUserContent: unknown): CloudIntentCandidate | null {
  try {
    if (typeof lastUserContent !== 'string') return null;
    const text = lastUserContent.trim();
    if (!text) return null;
    const ask = CONCEPT_ASK.exec(text);
    if (ask && conceptEligible(ask[1])) return { intent: 'explain_concept', slot: ask[1].trim().toLowerCase() };
    if (artifactEligible(text)) {
      const isLog = text.split('\n').some((l) => /^\d{4}-\d\d-\d\d[T ]/.test(l));
      return { intent: isLog ? 'summarise_log' : 'explain_error', slot: text };
    }
    return null;
  } catch {
    return null;
  }
}

// Fixed, server-controlled instructions. The slot is the only variable part of a cloud request.
export const CLOUD_SYSTEM_PROMPT: Record<CloudIntent, string> = {
  explain_concept:
    'You are a concise technical explainer. Explain the named software engineering concept in under 200 words, with one short example. Do not ask follow-up questions.',
  explain_error:
    'You are a concise software debugging assistant. Explain what the following error or stack trace means and the most likely fixes, in under 200 words.',
  summarise_log:
    'You are a concise operations assistant. Summarise the following log lines: what happened, anything abnormal, and a likely next step, in under 200 words.',
};

export function cloudUserContent(intent: CloudIntent, slot: string): string {
  if (intent === 'explain_concept') return `Concept: ${slot.trim().toLowerCase()}`;
  return `Input:\n${slot}`;
}

/** Roles whose subject matter is the Captain's health or wellbeing: local only, always. */
export const LOCAL_ONLY_ROLES = new Set([
  'recovery_officer', 'medical_officer', 'wellness_advisor', 'recovery_coach', 'performance_coach', 'human_systems_advisor',
  'crisis_advisor', 'bc_advisor', 'executive_risk_advisor', 'number_one',
]);

/** Cloud allowed only for these roles (positive list); any other or unknown role is local. */
export const CLOUD_CAPABLE_ROLES = new Set([
  'chief_engineer', 'xo', 'research_officer', 'general', 'or_advisor', 'strategist', 'challenger', 'operator', 'external_lens', 'commercial_realist',
]);

export type RouteReason =
  | 'intent_ok' | 'default_local' | 'health_role' | 'role_not_listed' | 'client_prompt' | 'no_intent' | 'gate_error' | 'cloud_disabled';

export interface RouteDecision { route: 'cloud' | 'local'; reason: RouteReason; candidate?: CloudIntentCandidate }

export interface RouteInput {
  role: unknown;
  systemPrompt: unknown;
  lastUserContent: unknown;
  /** optional explicit intent from the client; validated exactly like a derived one */
  explicit?: { intent?: unknown; slot?: unknown } | null;
}

export function decideRoute(input: RouteInput, env: Record<string, string | undefined> = process.env): RouteDecision {
  try {
    if (input.role !== undefined && input.role !== null && typeof input.role !== 'string') return { route: 'local', reason: 'role_not_listed' };
    const role = input.role ?? 'chief_engineer';
    if (LOCAL_ONLY_ROLES.has(role)) return { route: 'local', reason: 'health_role' };
    if (!CLOUD_CAPABLE_ROLES.has(role)) return { route: 'local', reason: 'role_not_listed' };
    if (typeof input.systemPrompt === 'string' && input.systemPrompt.trim()) return { route: 'local', reason: 'client_prompt' };
    if (env.OLLAMA_CLOUD_ENABLED !== 'true') return { route: 'local', reason: 'cloud_disabled' };
    let candidate: CloudIntentCandidate | null = null;
    if (input.explicit && typeof input.explicit === 'object' && input.explicit.intent !== undefined) {
      const { intent, slot } = input.explicit;
      if (intentSlotEligible(intent, slot)) candidate = { intent: intent as CloudIntent, slot: slot as string };
      else return { route: 'local', reason: 'no_intent' };
    } else {
      candidate = deriveIntent(input.lastUserContent);
    }
    if (!candidate) return { route: 'local', reason: 'no_intent' };
    return { route: 'cloud', reason: 'intent_ok', candidate };
  } catch {
    return { route: 'local', reason: 'gate_error' };
  }
}

// ── Counts-only telemetry (no content, no identifiers) ───────────────────────────────────────────────────────────
const counts: Record<string, number> = {};
export function recordChatPrivacyEvent(name: string): void {
  counts[name] = (counts[name] ?? 0) + 1;
  try {
    console.info('[chat-privacy]', JSON.stringify({ event: name, total: counts[name] }));
  } catch {
    /* never throw from telemetry */
  }
}
export function chatPrivacyCounts(): Record<string, number> { return { ...counts }; }
export function resetChatPrivacyCounts(): void { for (const k of Object.keys(counts)) delete counts[k]; }
