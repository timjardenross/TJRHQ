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
  | 'rejected'
  | 'resolved_before_research';

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
  related_experience?: RelatedExperienceItem[];
  related_experience_summary?: string;
}

export type MeasurementType = 'quantitative' | 'deterministic' | 'qualitative' | 'mixed' | 'unknown';
export type OutcomeResult = 'improved' | 'no_material_change' | 'regressed' | 'inconclusive' | 'not_yet_ready';

export interface OutcomeContract {
  expected_benefit: string;
  measurement_type: MeasurementType;
  baseline:
    | { available: true; value: any; description: string; provenance: string; captured_at: string }
    | { available: false; reason: string; captured_at: string };
  success_signal: string;
  regression_signal: string;
  observation_window: { type: 'immediate' | 'cycles' | 'events' | 'days'; count: number };
  evidence_sources: string[];
  evaluation_status: 'pending_implementation' | 'observing' | 'ready_to_evaluate' | 'evaluated';
  observation_started_at: string | null;
  created_at: string;
}

export interface RelatedExperienceItem {
  opportunity_id: string;
  title: string;
  change_class: string;
  relationship: 'learned' | 'rejected' | 'watching' | 'resolved_before_research';
  outcome_result: string | null;
  outcome_confidence: string | null;
  outcome_summary: string | null;
  rejection_reason: string | null;
  watch_reason: string | null;
  future_implication: string | null;
  resolution_note: string | null;
  relevance_score: number;
}

export interface Outcome {
  implementation_success?: boolean | null;
  improvement_success?: boolean | null;
  improvement_success_note?: string;
  remediation_history?: Array<{ timestamp?: string; success?: boolean; message?: string }>;
  outcome_result?: OutcomeResult | null;
  confidence?: 'low' | 'moderate' | 'high' | null;
  evidence_summary?: string;
  what_worked?: string;
  what_did_not?: string;
  unexpected_effects?: string[];
  future_implication?: string;
  attribution_risk?: string | null;
  method?: 'deterministic' | 'model_synthesis' | 'template_fallback' | null;
  evaluated_at?: string | null;
  implementation_source?: 'remediation' | 'mission' | 'manual' | null;
  implementation_verified_at?: string | null;
  evaluation_history?: Array<{ outcome_result: string; confidence: string; evidence_summary: string; evaluated_at: string; method: string }>;
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
  outcome_contract: OutcomeContract | Record<string, never>; // {} before approval
  validation_result: 'confirmed' | 'resolved' | 'unclear' | null;
  validation_evidence: string[];
  validated_at: string | null;
  source_finding_id: string | null;
  mission_id: string | null;
  automation_eligibility: string | null;
  policy_decision_rationale: string | null;
  created_at: string;
  updated_at: string;
  run_id: string | null;
  // Read-only join of auto_remediation.py's own outcome log (2026-09-06) —
  // present only once that engine has actually acted on this opportunity's
  // source_finding_id; absent for anything not yet touched, or with no
  // source_finding_id at all.
  remediation_status?: 'succeeded' | 'failed';
  remediation_message?: string;
  remediation_pr_url?: string | null;
  remediation_at?: string;
}

export type OpportunityDecisionType =
  | 'turn_into_improvement'
  | 'keep_watching'
  | 'not_useful'
  | 'approve_improvement'
  | 'create_mission'
  | 'more_evidence'
  | 'reject'
  | 'mark_implemented';

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
  outcomes_completed_count: number;
  regressions_count: number;
  latest_material_learning: { opportunity_id: string; title: string; outcome_result: string; future_implication: string } | null;
  cycle_status: 'ok' | 'failed' | 'skipped' | 'unknown';
  freshness: string | null;
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
