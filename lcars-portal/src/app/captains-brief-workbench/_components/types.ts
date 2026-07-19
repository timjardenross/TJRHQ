// Types + pure helpers for the Captain's Brief Workbench.
//
// These mirror the Python dataclasses assembled by
// core/platform/captain_brief_orchestrator.py's CaptainBriefDocument (MSN-0313)
// and captain_brief_contract.py's CaptainBriefItem/Recommendation — the exact
// same shape the (app)/captains-brief LCARS page consumed. Lifted here verbatim
// (no field changes) so the workbench is a presentation migration only.
//
// insights (list[Any], MSN-0329) is always [] via the service's /brief/full
// (which calls assemble_captain_brief_document, not the evolved assembler) —
// rendered defensively so it appears faithfully if the pipeline ever opts in.
// interrupt_now (list[CaptainBriefItem], MSN-0339) IS populated: the raw
// Attention Engine INTERRUPT_NOW bucket the old UI discarded.

export interface Recommendation {
  description: string;
  action_type: string | null;
  confidence: number | null;
  evidence: string[];
  requires_approval: boolean;
  supporting_context: string | null;
}

export interface CaptainBriefItem {
  event_id: string | null;
  domain: string;
  event_type: string;
  category: string;
  reason: string;
  priority_score: number | null;
  priority_explanation: string | null;
  risk_score: number | null;
  recommendation: Recommendation | null;
  related_event_ids: string[];
  aggregation_key: string | null;
  // MSN-0328 Wave 2/3: structured per-domain detail attached at emission time.
  metrics?: Record<string, unknown>;
}

// Mirrors core/platform/insight_engine.py's Insight. Typed `Any` on the Python
// side, so every field is optional here and rendered only when present.
export interface Insight {
  observation?: string;
  why_it_matters?: string;
  evidence_chain?: string[];
  confidence?: number | null;
  potential_impact?: string;
  source_kind?: string;
  source_domains?: string[];
  generated_at?: string;
}

export interface CaptainBriefDocument {
  version: string;
  generated_at: string;
  summary: string;
  priorities: CaptainBriefItem[];
  recommendations: Recommendation[];
  health: CaptainBriefItem[];
  operational_intelligence: CaptainBriefItem[];
  engineering: CaptainBriefItem[];
  learning: CaptainBriefItem[];
  opportunities: CaptainBriefItem[];
  warnings: CaptainBriefItem[];
  next_actions: string[];
  metadata?: Record<string, unknown>;
  confidence: number | null;
  insights: Insight[];
  interrupt_now: CaptainBriefItem[];
}

// ── Domain toggle (Brief | Domains) ──────────────────────────────────────────
export type Domain = 'brief' | 'domains';

export const EYEBROW: Record<Domain, string> = {
  brief: 'Continuous Captain Brief Orchestration · MSN-0313',
  domains: 'By domain · Health · Ops · Engineering · Learning · Opportunities',
};

export function isDomain(v: unknown): v is Domain {
  return v === 'brief' || v === 'domains';
}

// The five domain-grouped sections (unchanged from the LCARS page's DOMAIN_SECTIONS).
export const DOMAIN_SECTIONS: {
  key: 'health' | 'operational_intelligence' | 'engineering' | 'learning' | 'opportunities';
  label: string;
}[] = [
  { key: 'health', label: 'Health' },
  { key: 'operational_intelligence', label: 'Operational Intelligence' },
  { key: 'engineering', label: 'Engineering' },
  { key: 'learning', label: 'Learning' },
  { key: 'opportunities', label: 'Opportunities' },
];

// MSN-0328 Wave 3 metric labels — carried verbatim from the LCARS page.
export const METRIC_LABELS: Record<string, string> = {
  open_count: 'Open',
  high_risk_count: 'High-risk',
  constraint: 'Constraint',
  constraint_count: 'At constraint',
  active_count: 'Active',
  active_domains: 'Domains',
  orphan_count: 'Unaligned',
  expected_impact: 'Expected impact',
  opportunity_cost: 'Opportunity cost',
  recommended_deferral: 'Can wait',
  strategic_alignment: 'Alignment',
  overall_risk: 'Risk',
  bottom_line: 'Bottom line',
};

// Priority Engine's risk_score (0-100) bucketed to the same 1/2/3 escalation
// level the LCARS page used. Pure — identical logic to the old warningsLevel().
export function warningsLevel(warnings: CaptainBriefItem[]): 1 | 2 | 3 {
  const maxRisk = warnings.reduce((max, w) => Math.max(max, w.risk_score ?? 0), 0);
  if (maxRisk >= 80) return 3;
  if (maxRisk >= 60) return 2;
  return 1;
}

// Confidence → state tone, matching ConfidenceIndicator.confidenceStateTone
// (MSN-0315 Phase 1B): >=75 ok, >=50 warn, else crit; null → unknown.
export type Tone = 'ok' | 'warn' | 'crit' | 'unknown';
export function confidenceTone(score: number | null): Tone {
  if (score == null) return 'unknown';
  if (score >= 75) return 'ok';
  if (score >= 50) return 'warn';
  return 'crit';
}
