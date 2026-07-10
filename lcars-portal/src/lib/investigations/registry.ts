/**
 * MSN-0357 — Investigation Engine registry.
 *
 * All ten investigation types defined against docs/MSN-0353-INVESTIGATION-ARCHITECTURE.md
 * §1, in one place — matching the same "one array, one source of truth"
 * pattern lib/interruptAssembly.ts's NOMINATORS already uses. Nothing in
 * this file executes an investigation; it only names what exists.
 */

import type { InvestigationDefinition } from '@/lib/investigationEngine';
import { integrityAuditDiagnose, integrityAuditVerify, redundancyReconciliation } from './integrityAudit';
import { upstreamCoverageGap, downstreamVerificationGap } from './coverageGaps';
import { queueResolution, queueTriage } from './queueGovernance';
import { trendScan, noiseTriage, decisionTraceback } from './captainReview';

export const INVESTIGATION_REGISTRY: InvestigationDefinition<any, any>[] = [
  integrityAuditDiagnose,
  integrityAuditVerify,
  redundancyReconciliation,
  upstreamCoverageGap,
  downstreamVerificationGap,
  queueResolution,
  queueTriage,
  trendScan,
  noiseTriage,
  decisionTraceback,
];

export function investigationByType(type: string) {
  return INVESTIGATION_REGISTRY.find((def) => def.type === type);
}

export {
  integrityAuditDiagnose,
  integrityAuditVerify,
  redundancyReconciliation,
  upstreamCoverageGap,
  downstreamVerificationGap,
  queueResolution,
  queueTriage,
  trendScan,
  noiseTriage,
  decisionTraceback,
};
