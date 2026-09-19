// Briefs/Captain's Brief consolidation Phase 2-3
// (BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md §4.1/§6) — mirrors
// intelligence/brief/domains_view.py's DomainSummary/DomainsDocument
// dataclasses verbatim. One normalised shape for both OSINT domain_picture
// buckets and Captain's Brief's event-bus domain sections, so the Domains
// tab renders one document instead of reconciling two incompatible shapes
// itself.

export type DomainSource = 'osint' | 'event_bus';
export type DomainAvailability = 'ok' | 'no_data' | 'degraded' | 'unavailable';
export type Posture = 'RED' | 'AMBER' | 'GREEN' | 'UNKNOWN';

export interface DomainEvidenceItem {
  title: string;
  detail: string | null;
  risk: string | null;
}

export interface DomainSummary {
  key: string;
  label: string;
  source: DomainSource;
  posture: Posture;
  confidence: number | null;
  what_changed: string | null;
  what_matters: string[];
  watch_conditions: string[];
  // Coverage/data-quality caveats — e.g. "N event(s) aggregated as a
  // count/trend" — distinct from what_matters (findings) and
  // watch_conditions (near-threshold risk items). See domains_view.py's
  // `_aggregation_constraints()`.
  constraints: string[];
  evidence_count: number;
  evidence: DomainEvidenceItem[];
  as_of: string | null;
  availability: DomainAvailability;
  detail_href: string | null;
}

export interface DomainsDocument {
  generated_at: string;
  domains: DomainSummary[];
  event_bus_as_of: string | null;
  osint_as_of: string | null;
  osint_available: boolean;
  warnings: string[];
}

export const AVAILABILITY_LABEL: Record<DomainAvailability, string> = {
  ok: 'Current',
  no_data: 'No signals right now',
  degraded: 'Degraded coverage',
  unavailable: 'Unavailable',
};
