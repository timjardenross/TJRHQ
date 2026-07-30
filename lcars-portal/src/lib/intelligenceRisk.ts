// MSN-0351 (Operational Workbench Integrity) — shared derivation for the
// Intelligence Signals risk badge.
//
// IMPORTANT: there is NO stored `risk_rating` column on intelligence_events
// (see src/app/api/intelligence/route.ts, signals view). The HIGH/MEDIUM/LOW
// risk shown on a signal is a DERIVED assessment, computed here from the
// stored `customer_impact` and `banking_relevance` fields. Both the badge
// (intelligence/page.tsx) and the server-side risk filter (route.ts) import
// this single source of truth so the filter can never disagree with the
// badge it filters on.

export type RiskLevel = 'HIGH' | 'MEDIUM' | 'LOW' | '';

export interface RiskInputs {
  customer_impact?: string | null;
  banking_relevance?: string | null;
}

/**
 * Derive a signal's risk level from its impact fields. Returns '' when
 * neither field carries a recognised value (rendered as a neutral badge).
 */
export function deriveRisk(s: RiskInputs): RiskLevel {
  const ci = (s.customer_impact ?? '').toLowerCase();
  const br = (s.banking_relevance ?? '').toLowerCase();
  if (ci === 'high' || br === 'high') return 'HIGH';
  if (ci === 'medium' || br === 'medium') return 'MEDIUM';
  if (ci === 'low' || br === 'low') return 'LOW';
  return '';
}

/**
 * Whether a signal matches a requested risk filter. A signal matches when
 * its DERIVED risk equals the wanted level — so the filter considers both
 * customer_impact AND banking_relevance, exactly like the badge.
 *
 * This closes the filter bug where a server-side `.eq('customer_impact', …)`
 * silently excluded items that were HIGH only via banking_relevance:
 * filtering to "HIGH" used to miss real high-risk items.
 */
export function signalMatchesRisk(s: RiskInputs, wanted: string): boolean {
  const w = wanted.toUpperCase();
  if (!w) return true;
  return deriveRisk(s) === w;
}
