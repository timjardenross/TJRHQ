import { describe, it, expect } from 'vitest';
import {
  engineeringRates,
  engineeringRatePct,
  DELIVERED_STATUSES,
  type AgentPerfLike,
  type BatchJobLike,
  type BuildRequestLike,
} from '@/lib/engineeringMetrics';

const perfs = (successes: boolean[]): AgentPerfLike[] => successes.map((success) => ({ success }));
const jobs = (rows: [number | null, number | null][]): BatchJobLike[] =>
  rows.map(([total_requests, succeeded_requests]) => ({ total_requests, succeeded_requests }));
const reqs = (statuses: string[]): BuildRequestLike[] => statuses.map((status) => ({ status }));

describe('engineeringRates', () => {
  it('reports hasData=false and all ratios null when there is nothing to measure', () => {
    const { rates, hasData } = engineeringRates([], [], []);
    expect(hasData).toBe(false);
    for (const r of rates) {
      expect(r.ratio).toBeNull();
      expect(r.denominator).toBe(0);
    }
  });

  it('never fabricates a 0% for an unmeasured rate — an empty denominator is null, not zero', () => {
    // Only agent data present; batch + pipeline must be null (unmeasured), not 0.
    const { rates } = engineeringRates(perfs([true, true]), [], []);
    const byKey = Object.fromEntries(rates.map((r) => [r.key, r]));
    expect(byKey.agent_success.ratio).toBe(1);
    expect(byKey.batch_success.ratio).toBeNull();
    expect(byKey.pipeline_delivery.ratio).toBeNull();
  });

  it('computes the agent success rate from real records', () => {
    const { rates } = engineeringRates(perfs([true, true, false, false]), [], []);
    const agent = rates.find((r) => r.key === 'agent_success')!;
    expect(agent.ratio).toBe(0.5);
    expect(agent.numerator).toBe(2);
    expect(agent.denominator).toBe(4);
    expect(agent.detail).toBe('2 of 4 tasks succeeded');
  });

  it('sums batch success across jobs and ignores null counts', () => {
    const { rates } = engineeringRates([], jobs([[10, 8], [null, null], [10, 7]]), []);
    const batch = rates.find((r) => r.key === 'batch_success')!;
    expect(batch.numerator).toBe(15);
    expect(batch.denominator).toBe(20);
    expect(batch.ratio).toBe(0.75);
  });

  it('counts only delivered/approved build requests toward the pipeline rate', () => {
    const { rates } = engineeringRates([], [], reqs(['engineering_delivered', 'approved', 'pending', 'rejected']));
    const pipeline = rates.find((r) => r.key === 'pipeline_delivery')!;
    expect(pipeline.numerator).toBe(2);
    expect(pipeline.denominator).toBe(4);
    expect(pipeline.ratio).toBe(0.5);
    // Guard the delivered-status contract the ratio depends on.
    expect(DELIVERED_STATUSES).toEqual(['engineering_delivered', 'approved']);
  });

  it('exposes the three real rates separately and does not synthesize a composite score', () => {
    const { rates } = engineeringRates(perfs([true]), jobs([[2, 1]]), reqs(['approved']));
    expect(rates.map((r) => r.key)).toEqual(['agent_success', 'batch_success', 'pipeline_delivery']);
    // No field on any rate is an out-of-/100 composite.
    for (const r of rates) {
      expect(Object.keys(r)).not.toContain('score');
    }
  });
});

describe('engineeringRatePct', () => {
  it('renders a real fraction as a rounded percent', () => {
    expect(engineeringRatePct(0.5)).toBe('50%');
    expect(engineeringRatePct(0.756)).toBe('76%');
  });

  it('renders an unmeasured (null) rate as an em-dash, never 0%', () => {
    expect(engineeringRatePct(null)).toBe('—');
  });
});
