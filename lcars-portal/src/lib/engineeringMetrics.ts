// Engineering deck — real underlying rates.
//
// MSN-0351 (Operational Workbench Integrity Programme): the Engineering deck
// previously synthesised a single "Cognitive Load Reduction /100" score by
// applying invented 40/30/30 point weightings and 80/50/25 severity bands to
// these three real inputs. That composite had no external basis — a fabricated
// metric wearing real data. It has been removed. What remains here are the
// three genuinely-measured rates it was built from, exposed separately so each
// can be shown as the honest number it is, never recombined into an invented
// score.

export interface AgentPerfLike {
  success: boolean;
}

export interface BatchJobLike {
  total_requests: number | null;
  succeeded_requests: number | null;
}

export interface BuildRequestLike {
  status: string;
}

// Build request statuses that represent work actually delivered/cleared from
// the pipeline (as opposed to still pending or rejected).
export const DELIVERED_STATUSES = ['engineering_delivered', 'approved'];

export interface EngineeringRate {
  key: 'agent_success' | 'batch_success' | 'pipeline_delivery';
  label: string;
  /** Fraction 0–1, or null when there is no underlying data to compute it from. */
  ratio: number | null;
  /** Numerator (e.g. successful tasks). */
  numerator: number;
  /** Denominator (e.g. total tasks). null when there is nothing to measure. */
  denominator: number;
  /** Human-readable "N of M …" description of what the ratio is made of. */
  detail: string;
}

function pctText(ratio: number | null): string {
  return ratio == null ? '—' : `${Math.round(ratio * 100)}%`;
}

/**
 * Compute the three real engineering rates. Each is null when its denominator
 * is zero — an unmeasured rate, never silently reported as 0%.
 */
export function engineeringRates(
  perfs: AgentPerfLike[],
  jobs: BatchJobLike[],
  requests: BuildRequestLike[],
): { rates: EngineeringRate[]; hasData: boolean } {
  // 1. Agent task success rate
  const agentTotal = perfs.length;
  const agentOk = perfs.filter((p) => p.success).length;
  const agentRatio = agentTotal > 0 ? agentOk / agentTotal : null;

  // 2. Batch request success rate (across all recent batch jobs)
  const batchTotal = jobs.reduce((s, j) => s + (j.total_requests ?? 0), 0);
  const batchOk = jobs.reduce((s, j) => s + (j.succeeded_requests ?? 0), 0);
  const batchRatio = batchTotal > 0 ? batchOk / batchTotal : null;

  // 3. Build pipeline delivery rate
  const reqTotal = requests.length;
  const delivered = requests.filter((r) => DELIVERED_STATUSES.includes(r.status)).length;
  const pipelineRatio = reqTotal > 0 ? delivered / reqTotal : null;

  const rates: EngineeringRate[] = [
    {
      key: 'agent_success',
      label: 'Agent task success rate',
      ratio: agentRatio,
      numerator: agentOk,
      denominator: agentTotal,
      detail: agentTotal > 0 ? `${agentOk} of ${agentTotal} tasks succeeded` : 'No agent tasks recorded',
    },
    {
      key: 'batch_success',
      label: 'Batch request success rate',
      ratio: batchRatio,
      numerator: batchOk,
      denominator: batchTotal,
      detail: batchTotal > 0 ? `${batchOk} of ${batchTotal} batch requests succeeded` : 'No batch requests recorded',
    },
    {
      key: 'pipeline_delivery',
      label: 'Pipeline delivery rate',
      ratio: pipelineRatio,
      numerator: delivered,
      denominator: reqTotal,
      detail: reqTotal > 0 ? `${delivered} of ${reqTotal} build requests delivered` : 'No build requests recorded',
    },
  ];

  const hasData = agentTotal > 0 || jobs.length > 0 || reqTotal > 0;
  return { rates, hasData };
}

export { pctText as engineeringRatePct };
