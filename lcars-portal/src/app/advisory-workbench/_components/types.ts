// Shared types for the Advisory Workbench.
//
// Unlike the Human Systems Workbench (a single domain-aware GET Payload), the
// Advisory Workbench is request/response: each view keeps its own
// request/response types and calls the existing advisory endpoints unchanged
// (/api/advisory, /api/ai/chat, /api/xo, /api/perspectives). This file just
// collects the cross-view types — there is no single Payload union.
//
// See ADVISORY-COUNCIL-WORKBENCH-MIGRATION-PLAN.md §6.1.

import type { ActionResult } from '@/lib/ai-actions';

/** The three advisory domains — one per legacy Advisory Council tab. */
export type Domain = 'consult' | 'board' | 'perspectives';

export function isDomain(v: string | null): v is Domain {
  return v === 'consult' || v === 'board' || v === 'perspectives';
}

/** Per-domain eyebrow copy shown in the Shell header. */
export const EYEBROW: Record<Domain, string> = {
  board: 'Ask',
  consult: 'Officer Advisors',
  perspectives: 'Distinguished Voices',
};

// ── Advisory (Board) ────────────────────────────────────────────────────────
export interface OfficerPerspective {
  officer: string;
  recommendation: string;
  confidence: number;
  stance?: string;
}
export interface Confidence {
  value: number;
  band: string;
  basis?: string;
}
export interface AdvisoryResult {
  question?: string;
  executive_summary?: string;
  bottom_line?: string;
  recommendation?: string;
  risks_and_challenges?: string[];
  confidence?: Confidence;
  officer_perspectives?: OfficerPerspective[];
  /** True when the live specialist pipeline failed and this result fell back
   * to historical evidence/lessons only (core/advisory/service.py's
   * _degraded_pipeline) — surfaced as a visible badge, not left to the
   * Captain to notice buried in executive_summary's prose (2026-08 UX
   * review finding). */
  degraded?: boolean;
  sections?: Array<{ heading: string; items?: string[]; text?: string; suppressed?: number }>;
  triggers?: unknown[];
  attention_required?: boolean;
  headline?: string;
  [key: string]: unknown;
}
export interface BoardSession {
  id: string;
  ts: number;
  question: string;
  result: AdvisoryResult;
}

// ── Consult ─────────────────────────────────────────────────────────────────
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
