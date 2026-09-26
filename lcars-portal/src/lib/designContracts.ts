/** Shared domain vocabulary for every workbench data-bearing surface. */
export type EvidenceState = 'empty' | 'no-action' | 'unavailable' | 'stale';
export type ActionOutcomeState = 'in-progress' | 'success' | 'failed' | 'cancelled';
export type DomainLifecycleState = 'active' | 'blocked' | 'overdue' | 'stale' | 'awaiting-owner' | 'completed' | 'cancelled';
export type DomainOwnerKind = 'captain' | 'person' | 'team' | 'system' | 'unassigned';
export type FreshnessState = 'fresh' | 'stale' | 'unknown' | 'unavailable';
export type AttentionState = 'none' | 'needs-action' | 'important' | 'watch';

export interface DomainOwner {
  id?: string | null;
  label: string;
  kind: DomainOwnerKind;
}

export interface FreshnessContract {
  state: FreshnessState;
  observedAt?: string | null;
  expiresAt?: string | null;
  maxAgeSeconds?: number | null;
}

export interface AttentionContract {
  state: AttentionState;
  reason?: string | null;
  actionLabel?: string | null;
}

export interface EvidenceContract {
  id?: string | null;
  source?: string | null;
  observedAt?: string | null;
  confidence?: string | null;
  state?: EvidenceState;
  freshness?: FreshnessContract;
}

export interface ConsequentialActionContract {
  id?: string | null;
  action: string;
  label?: string | null;
  outcome: ActionOutcomeState;
  state?: DomainLifecycleState;
  owner?: DomainOwner;
  evidence?: EvidenceContract;
  attention?: AttentionContract;
  details?: Record<string, unknown>;
  mission_id?: string | null;
}

/** Canonical envelope for a workbench item. Adapters may add domain fields,
 * but these fields must retain their shared meanings across portals. */
export interface DomainRecord {
  id: string;
  title: string;
  state: DomainLifecycleState;
  owner: DomainOwner;
  freshness: FreshnessContract;
  attention: AttentionContract;
  evidence?: EvidenceContract;
  actions?: ConsequentialActionContract[];
}

export const EVIDENCE_STATES: readonly EvidenceState[] = ['empty', 'no-action', 'unavailable', 'stale'];
export const FRESHNESS_STATES: readonly FreshnessState[] = ['fresh', 'stale', 'unknown', 'unavailable'];
export const ATTENTION_STATES: readonly AttentionState[] = ['none', 'needs-action', 'important', 'watch'];

export function isEvidenceState(value: unknown): value is EvidenceState {
  return typeof value === 'string' && EVIDENCE_STATES.includes(value as EvidenceState);
}

export function isFreshnessState(value: unknown): value is FreshnessState {
  return typeof value === 'string' && FRESHNESS_STATES.includes(value as FreshnessState);
}
