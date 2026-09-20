/** Shared vocabulary for the unified action/evidence design contract. */
export type EvidenceState = 'empty' | 'no-action' | 'unavailable' | 'stale';
export type ActionOutcomeState = 'in-progress' | 'success' | 'failed' | 'cancelled';

export interface EvidenceContract {
  source?: string | null;
  observedAt?: string | null;
  confidence?: string | null;
  state?: EvidenceState;
}

export interface ConsequentialActionContract {
  action: string;
  outcome: ActionOutcomeState;
  details?: Record<string, unknown>;
  mission_id?: string | null;
}
