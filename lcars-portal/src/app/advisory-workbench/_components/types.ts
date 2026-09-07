// Shared types for Advisory.
//
// Unlike the Human Systems Workbench (a single domain-aware GET Payload),
// Advisory is request/response: each view keeps its own request/response
// types and calls the existing advisory endpoints unchanged (/api/advisory,
// /api/ai/chat, /api/xo, /api/perspectives). This file just collects the
// cross-view types — there is no single Payload union.
//
// 2026-09 redesign: four competing modes (Ask / Talk to Someone / Panel of
// Voices / Close Out) collapsed to three (Think / Perspectives / Outcomes).
// The internal domain keys 'board' and 'loops' are kept as accepted legacy
// aliases — existing bookmarks, the investigate/page.tsx deep link, and the
// advisory-sessions mode:'board'|'consult' DB contract all predate this
// rename and are unaffected by it.

import type { ActionResult } from '@/lib/ai-actions';

/** The three Advisory modes. */
export type Domain = 'think' | 'perspectives' | 'outcomes';

const LEGACY_DOMAIN_ALIASES: Record<string, Domain> = {
  board: 'think',
  consult: 'think',
  loops: 'outcomes',
};

/** Accepts both the current domain keys and the pre-redesign aliases
 * ('board', 'consult', 'loops') so existing links/bookmarks keep working. */
export function normalizeDomain(v: string | null): Domain {
  if (v === 'think' || v === 'perspectives' || v === 'outcomes') return v;
  if (v && v in LEGACY_DOMAIN_ALIASES) return LEGACY_DOMAIN_ALIASES[v];
  return 'think';
}

/** Per-domain eyebrow copy shown in the Shell header. */
export const EYEBROW: Record<Domain, string> = {
  think: 'Think',
  perspectives: 'Perspectives',
  outcomes: 'Outcomes',
};

// ── Think ────────────────────────────────────────────────────────────────
export interface OfficerPerspective {
  officer: string;
  recommendation: string;
  confidence: number;
  stance?: string;
  reasoning?: string;
  sources?: string[];
}
export interface Confidence {
  value: number;
  band: string;
  basis?: string;
}
export interface EvidenceItem {
  kind: string;
  reference: string;
  detail: string;
  outcome_score?: number | null;
}
export interface LessonRef {
  lesson_id: string;
  title: string;
  guidance?: string;
  mission_id?: string;
  relevance?: number;
}
export interface AdvisoryResult {
  question?: string;
  executive_summary?: string;
  bottom_line?: string;
  recommendation?: string;
  historical_evidence?: EvidenceItem[];
  related_lessons?: LessonRef[];
  risks_and_challenges?: string[];
  confidence?: Confidence;
  officer_perspectives?: OfficerPerspective[];
  /** True when the live specialist pipeline failed and this result fell back
   * to historical evidence/lessons only (core/advisory/service.py's
   * _degraded_pipeline) — surfaced as a visible badge, not left to the
   * user to notice buried in executive_summary's prose. */
  degraded?: boolean;
  escalation_required?: boolean;
  disagreement?: string;
  reviewer?: string | null;
  advisory_id?: string;
  /** Closed-loop signal from prior outcomes (MSN-0093) — an honest, evidence-
   * gated note, never a fabricated pattern. */
  learning_note?: string;
  sections?: Array<{ heading: string; items?: string[]; text?: string; suppressed?: number }>;
  triggers?: unknown[];
  attention_required?: boolean;
  headline?: string;
  [key: string]: unknown;
}
export interface ThinkSession {
  id: string;
  ts: number;
  question: string;
  result: AdvisoryResult;
}

/** Reasoning lenses (mission §10) — user-facing framings over the SAME
 * advisory answer, not separate backend identities. 'challenge' is the only
 * one that makes a fresh call (to the real challenge/red-team pass); the
 * rest re-filter the specialist perspectives and risks already returned by
 * the one /api/advisory call. */
export type ReasoningLens = 'challenge' | 'human' | 'practical' | 'risk' | 'longterm';

export const REASONING_LENSES: { key: ReasoningLens; label: string }[] = [
  { key: 'challenge', label: 'Challenge it' },
  { key: 'human', label: 'Human impact' },
  { key: 'practical', label: 'Practical reality' },
  { key: 'risk', label: 'Risk' },
  { key: 'longterm', label: 'Long-term view' },
];

/** "Pull apart the reasoning" groupings — a small, honest relabelling of the
 * existing officer/specialist registry (see shared.tsx COUNCIL), not a new
 * taxonomy. 'Evidence' is deliberately not officer-sourced: it holds
 * historical_evidence/related_lessons plus the Investigation/Recommendation
 * engines, kept structurally separate from specialist interpretation. */
export type ReasoningGroup = 'Strategy' | 'Human Systems' | 'Risk' | 'Challenge' | 'Evidence';

// ── Consult (advanced/secondary — see mission §9) ──────────────────────────
export interface Msg {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
  /** MSN-0352: deterministic action-proposal outcomes attached to this
   * message, rendered from the backend's ActionResult objects — never from
   * the model's own prose. */
  proposals?: ActionResult[];
}
export interface CouncilAdvisor {
  id: string;
  label: string;
  subtitle: string;
  group: string;
  /** Advisory-Board challenger voice — rendered in the crit hue. */
  dissent?: boolean;
  useXoEndpoint?: boolean;
}

// ── Perspectives ────────────────────────────────────────────────────────────
export interface Perspective {
  name: string;
  label: string;
  category: string;
}
export interface PerspectiveResponse {
  perspective: Perspective;
  content: string;
  response: string;
  loading: boolean;
  error: string | null;
}
export interface PerspectiveSession {
  id: string;
  ts: number;
  question: string;
  responses: { label: string; response: string }[];
}

/** Conceptual reasoning lenses (mission §11) — the PRIMARY way to ask for a
 * perspective. Each maps to one or more of the 15 Distinguished Voices
 * persona prompts (mission §12); the mapping is an editorial grouping for
 * comprehension, not an authoritative taxonomy, and Distinguished Voices
 * remains reachable directly as a secondary/exploratory option. */
export type PerspectiveLens =
  | 'strategic' | 'human' | 'skeptical' | 'practical'
  | 'systems' | 'longterm' | 'compassionate' | 'contrarian';

export const PERSPECTIVE_LENSES: { key: PerspectiveLens; label: string; personas: string[] }[] = [
  { key: 'strategic',     label: 'Strategic',     personas: ['sun-tzu', 'drucker', 'jobs'] },
  { key: 'human',         label: 'Human',         personas: ['frankl', 'brown'] },
  { key: 'skeptical',     label: 'Skeptical',     personas: ['feynman', 'ginsburg'] },
  { key: 'practical',     label: 'Practical',     personas: ['covey', 'nooyi'] },
  { key: 'systems',       label: 'Systems',       personas: ['picard', 'editorial-strategist'] },
  { key: 'longterm',      label: 'Long-term',     personas: ['churchill', 'obama'] },
  { key: 'compassionate', label: 'Compassionate', personas: ['thich-nhat-hanh', 'ardern'] },
  { key: 'contrarian',    label: 'Contrarian',    personas: ['ginsburg', 'churchill'] },
];
