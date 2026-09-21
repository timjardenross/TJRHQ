import { describe, expect, it } from 'vitest';
import { calculateOperationalConfidence } from '../operationalConfidence';

describe('calculateOperationalConfidence', () => {
  it('returns high confidence for complete fresh sources', () => {
    const result = calculateOperationalConfidence([
      { id: 'a', label: 'A', completeness: 1, freshness: 'fresh' },
      { id: 'b', label: 'B', completeness: 1, freshness: 'fresh' },
    ]);
    expect(result).toMatchObject({ score: 100, band: 'high', completenessPct: 100, freshSourcePct: 100 });
  });

  it('makes stale and incomplete evidence visible in the score', () => {
    const result = calculateOperationalConfidence([
      { id: 'a', label: 'A', completeness: 0.5, freshness: 'stale' },
      { id: 'b', label: 'B', completeness: null, freshness: 'unavailable' },
    ]);
    expect(result.band).toBe('low');
    expect(result.score).toBe(30);
    expect(result.reasons.join(' ')).toContain('unknown or unavailable');
  });

  it('does not invent a score when completeness is absent', () => {
    expect(calculateOperationalConfidence([{ id: 'a', label: 'A', completeness: null, freshness: 'fresh' }])).toMatchObject({ score: null, band: 'unknown' });
    expect(calculateOperationalConfidence([]).band).toBe('unknown');
  });
});
