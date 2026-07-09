import { describe, it, expect } from 'vitest';
import {
  INTERRUPT_COVERAGE_REGISTRY,
  validateCoverage,
  capabilitiesWithRealEvaluator,
  openDegradationGaps,
} from '@/lib/interruptCoverageRegistry';

describe('INTERRUPT_COVERAGE_REGISTRY', () => {
  it('is internally consistent - no capability claims more coverage than it declares', () => {
    const { ok, problems } = validateCoverage();
    expect(problems).toEqual([]);
    expect(ok).toBe(true);
  });

  it('has no duplicate capability ids', () => {
    const ids = INTERRUPT_COVERAGE_REGISTRY.map((e) => e.capability);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every entry declares whether its degradation path is honest, per MSN-0351', () => {
    for (const entry of INTERRUPT_COVERAGE_REGISTRY) {
      expect(typeof entry.degradationIsHonest).toBe('boolean');
      expect(entry.degradationBehaviour.length).toBeGreaterThan(0);
    }
  });

  it('lists exactly the server-evaluated capabilities today (EOS Canonical Architecture Decisions §1 alerts.ts reconciliation added automation-centre, delivery-bottlenecks, human-systems-redflag, recovery-brief-posture, recovery-pain-trend)', () => {
    const real = capabilitiesWithRealEvaluator().map((e) => e.capability).sort();
    expect(real).toEqual([
      'advisory-proactive',
      'automation-centre',
      'captains-brief',
      'delivery-bottlenecks',
      'health-insights-risk-flags',
      'human-systems-redflag',
      'intelligence-signals',
      'missions',
      'recovery-brief-posture',
      'recovery-pain-trend',
    ]);
  });

  it('honestly reports the remaining false-calm gaps MSN-0351 did not close', () => {
    const gaps = openDegradationGaps();
    // MSN-0351 fixed the highest-severity/most-tractable degradation gaps but
    // explicitly did not build new server-side schedulers - some entries are
    // expected to remain open. This test guards against silently marking a
    // gap "honest" without doing the work, not against gaps existing.
    expect(gaps.length).toBeGreaterThan(0);
    expect(gaps.some((g) => g.capability === 'captains-brief')).toBe(true);
  });
});
