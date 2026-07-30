// EOS Phase 2 Priority 2 - thin client for the Investigation Engine bridge
// (api/investigations/route.ts). Mirrors lib/recommendations.ts's
// fetchRecommendations() and lib/decide.ts's fetchDecideCount(): a simple,
// typed, no-business-logic wrapper. All lifecycle/evidence/decision logic
// stays in lib/investigationEngine.ts and lib/investigations/*.ts.

export interface InvestigationRunResult {
  type: string;
  label: string;
  owner: string;
  triggerDescription: string;
  stagesReached: string[];
  validation: { ok: boolean; problems: string[] } | null;
  decisionOptions: { id: string; label: string; isReversible: boolean }[];
  completion: { complete: boolean; reason: string } | null;
  audit: { stage: string; summary: string; evidenceRefs: string[] }[];
}

/** Runs one investigation type through the real engine. Returns null on any
 * failure - callers degrade to "couldn't run this" rather than a fabricated
 * empty-but-successful result. Read-only: this can never mutate anything,
 * see api/investigations/route.ts's own header comment for why. */
export async function fetchInvestigation(
  type: string,
  reason: string,
  originRef?: string
): Promise<InvestigationRunResult | null> {
  try {
    const params = new URLSearchParams({ type, reason });
    if (originRef) params.set('originRef', originRef);
    const resp = await fetch(`/api/investigations?${params.toString()}`);
    if (!resp.ok) return null;
    const data = await resp.json();
    if (!data || typeof data !== 'object' || !Array.isArray(data.stagesReached)) return null;
    return data as InvestigationRunResult;
  } catch {
    return null;
  }
}

/** Maps an interrupt's domain (lib/interruptAssembly.ts's Interrupt.domain)
 * to the investigation type that can genuinely follow it, based on what
 * each type's real evidence source actually is (docs/MSN-0357-
 * INVESTIGATION-ENGINE.md's Coverage Matrix) - not every domain has a
 * natural investigation to offer, and this deliberately returns null
 * rather than forcing a fit. */
export function investigationTypeForDomain(domain: string): string | null {
  if (domain === 'Intelligence briefs') return 'trend-scan';
  if (domain === 'Operational intelligence') return 'noise-triage';
  return null;
}
