// HQ Evolution shared types — mirrors scripts/self_improvement/
// opportunity_store.py's Opportunity dataclass (field-for-field, snake_case
// as returned by the Flask bridge) and the pre-existing legacy Finding/
// Decision shapes from dashboard.py's /api/findings, /api/decide.

export type LifecycleState =
  | 'discovered'
  | 'investigating'
  | 'proposed'
  | 'approved'
  | 'implementing'
  | 'verifying'
  | 'learned'
  | 'watching'
  | 'rejected';

export type ChangeClass =
  | 'maintenance'
  | 'configuration'
  | 'reliability'
  | 'cost_optimisation'
  | 'capability'
  | 'product_improvement'
  | 'architecture';

export const MISSION_ONLY_CLASSES: ChangeClass[] = ['capability', 'product_improvement', 'architecture'];

export interface ProvenanceEntry {
  source?: string;
  location?: string | null;
  retrieved_at?: string;
  detail?: string;
}

export interface Investigation {
  why_hq_is_looking_at_this?: string;
  fit_with_hq?: string;
  potential_benefits?: string[];
  cost_impact?: string;
  risks?: string[];
  implementation_effort?: string;
  alternatives?: string[];
  confidence?: number;
  recommendation?: 'worth_pursuing' | 'keep_watching' | 'not_useful' | string;
  recommendation_rationale?: string;
  method?: 'model_synthesis' | 'template_fallback' | 'migrated_legacy_finding' | string;
}

export interface Outcome {
  implementation_success?: boolean | null;
  improvement_success?: boolean | null;
  improvement_success_note?: string;
  remediation_history?: Array<{ timestamp?: string; success?: boolean; message?: string }>;
}

export interface Opportunity {
  opportunity_id: string;
  title: string;
  change_class: ChangeClass;
  discovery_source: 'internal' | 'external';
  lifecycle_state: LifecycleState;
  fingerprint: string;
  summary: string;
  why_relevant: string;
  value: 'low' | 'medium' | 'high' | null;
  cost_impact: 'lower' | 'neutral' | 'higher' | 'unknown' | null;
  complexity: 'low' | 'moderate' | 'high' | null;
  fit: 'weak' | 'moderate' | 'strong' | null;
  risk_level: string | null;
  relevance_score: number | null;
  confidence: number;
  evidence_strength: string;
  investigation: Investigation;
  provenance: ProvenanceEntry[];
  watch_reason: string | null;
  rejection_reason: string | null;
  missing_evidence: string[];
  outcome: Outcome;
  source_finding_id: string | null;
  mission_id: string | null;
  automation_eligibility: string | null;
  policy_decision_rationale: string | null;
  created_at: string;
  updated_at: string;
  run_id: string | null;
}

export type OpportunityDecisionType =
  | 'turn_into_improvement'
  | 'keep_watching'
  | 'not_useful'
  | 'approve_improvement'
  | 'create_mission'
  | 'more_evidence'
  | 'reject';

export interface EvolutionSummary {
  run_id: string | null;
  timestamp: string | null;
  investigated_count: number;
  worth_considering_count: number;
  nothing_worth_changing: boolean;
  highest_value_opportunity: { opportunity_id: string | null; title: string; change_class: string; summary: string } | null;
  pending_decisions_count: number;
  any_verification_failure: boolean;
  has_run_yet: boolean;
}

// ── Legacy (preserved, unmodified pipeline) ─────────────────────────────

export interface LegacyFinding {
  finding_id: string;
  category: string;
  title: string;
  description: string;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  risk_level: string;
  confidence: number;
  evidence: Array<{ type: string; observation: string; location?: string }>;
  proposed_action: { type: string; description: string };
  decision?: 'approved' | 'rejected' | 'more_evidence';
  decision_reasoning?: string;
}

export const CHANGE_CLASS_LABEL: Record<ChangeClass, string> = {
  maintenance: 'Maintenance',
  configuration: 'Configuration',
  reliability: 'Reliability',
  cost_optimisation: 'Cost Opportunity',
  capability: 'New Capability',
  product_improvement: 'Product Improvement',
  architecture: 'Architecture',
};
