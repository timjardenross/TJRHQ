// Intelligence item -> governed decision request.
//
// Reuses the existing AI-proposal mechanism end to end: a request is a
// build_request_inbox row (status awaiting_review, action_type log_decision)
// created by proposeAction(), approved through approve-action's atomic claim, and
// recorded by logDecision. Nothing new is stored or executed. The source evidence,
// the original item, the reason a decision is needed, the options considered and
// any recommendation travel in action_payload (jsonb), which the existing
// validation and executors ignore.
//
// It is explicit and one-per-item: a person asks for a decision on a specific item;
// nothing turns findings into decisions automatically, and the same item can never
// have two requests (the request_id is derived from the item, and request_id is UNIQUE).
import { createHash } from 'crypto';

export const DECISION_REQUEST_SOURCE = 'hq-intelligence-decision-request';

export interface DecisionRequestInput {
  sourceId: string;
  sourceTitle: string;
  sourceUrl?: string | null;
  sourceLens?: string | null;
  question: string;
  reason: string;
  options: string[];
  recommendation?: string | null;
  evidence?: { label: string; detail: string }[];
}

export interface DecisionRequestPayload {
  kind: 'intelligence_decision_request';
  title: string;
  decision: null;
  rationale: string;
  options: string[];
  recommendation: string | null;
  evidence: { label: string; detail: string }[];
  source: { kind: 'intelligence'; id: string; title: string; url: string | null; lens: string | null };
  dedupe_key: string;
}

const clip = (s: unknown, n: number) => String(s ?? '').trim().slice(0, n);

export function requestIdFor(sourceId: string): string {
  return `HQ-INTEL-${createHash('sha1').update(sourceId).digest('hex').slice(0, 16).toUpperCase()}`;
}

export type Validated = { ok: true; value: DecisionRequestPayload } | { ok: false; error: string };

export function validateDecisionRequest(input: Partial<DecisionRequestInput> | null | undefined): Validated {
  if (!input) return { ok: false, error: 'Missing request.' };
  const sourceId = clip(input.sourceId, 200);
  const sourceTitle = clip(input.sourceTitle, 300);
  const question = clip(input.question, 300);
  const reason = clip(input.reason, 1000);
  if (!sourceId || !sourceTitle) return { ok: false, error: 'The intelligence item is required.' };
  if (!question) return { ok: false, error: 'State what needs to be decided.' };
  if (!reason) return { ok: false, error: 'State why a decision is needed.' };
  const options = [...new Set((input.options ?? []).map((o) => clip(o, 200)).filter(Boolean))];
  if (options.length < 2 || options.length > 5) return { ok: false, error: 'Give between 2 and 5 distinct options.' };
  const recommendation = input.recommendation ? clip(input.recommendation, 200) : null;
  if (recommendation && !options.includes(recommendation)) return { ok: false, error: 'The recommendation must be one of the options.' };
  const evidence = (input.evidence ?? []).slice(0, 8).map((e) => ({ label: clip(e.label, 120), detail: clip(e.detail, 300) })).filter((e) => e.label);
  const url = clip(input.sourceUrl, 500);
  return {
    ok: true,
    value: {
      kind: 'intelligence_decision_request',
      title: question,
      decision: null,
      rationale: reason,
      options,
      recommendation,
      evidence,
      source: { kind: 'intelligence', id: sourceId, title: sourceTitle, url: /^https?:\/\//.test(url) ? url : null, lens: clip(input.sourceLens, 40) || null },
      dedupe_key: sourceId,
    },
  };
}

/** What gets logged when a chosen option is approved. */
export function decisionTextFor(p: Pick<DecisionRequestPayload, 'source'>, option: string): string {
  return `${option} (re: ${p.source.title})`.slice(0, 300);
}
