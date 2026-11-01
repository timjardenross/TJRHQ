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

  it('caps the band at moderate when unknown-freshness sources exceed 20% even though the score qualifies as high', () => {
    // Mirrors the live HQ Status observation: 146 sources, 100% completeness,
    // 110/146 (~75%) fresh, 36/146 (~24.7%) unknown freshness.
    // Score = round(1 * 0.6 + 0.7534... * 0.4) * 100 = 90, which clears the
    // >=85 "high" threshold, but 24.7% unknown exceeds the 20% cap.
    const sources = [
      ...Array.from({ length: 110 }, (_, i) => ({ id: `fresh-${i}`, label: `Fresh ${i}`, completeness: 1, freshness: 'fresh' as const })),
      ...Array.from({ length: 36 }, (_, i) => ({ id: `unknown-${i}`, label: `Unknown ${i}`, completeness: 1, freshness: 'unknown' as const })),
    ];
    const result = calculateOperationalConfidence(sources);
    expect(result.score).toBe(90);
    expect(result.completenessPct).toBe(100);
    expect(result.freshSourcePct).toBe(75);
    expect(result.band).toBe('moderate');
    expect(result.reasons.join(' ')).toContain('capped at moderate');
  });

  it('keeps the high band when unknown-freshness sources are at or under the 20% cap', () => {
    const sources = [
      ...Array.from({ length: 80 }, (_, i) => ({ id: `fresh-${i}`, label: `Fresh ${i}`, completeness: 1, freshness: 'fresh' as const })),
      ...Array.from({ length: 20 }, (_, i) => ({ id: `unknown-${i}`, label: `Unknown ${i}`, completeness: 1, freshness: 'unknown' as const })),
    ];
    const result = calculateOperationalConfidence(sources);
    // 20/100 = 20% unknown, exactly at the cap (not over it), and score
    // (1 * 0.6 + 0.8 * 0.4) * 100 = 92 clears the high threshold.
    expect(result.score).toBe(92);
    expect(result.band).toBe('high');
    expect(result.reasons.join(' ')).not.toContain('capped at moderate');
  });

  it('does not cap bands that are already moderate or low due to unknown freshness', () => {
    const sources = [
      { id: 'a', label: 'A', completeness: 0.5, freshness: 'unknown' as const },
      { id: 'b', label: 'B', completeness: 0.5, freshness: 'unknown' as const },
    ];
    const result = calculateOperationalConfidence(sources);
    expect(result.band).toBe('low');
    expect(result.reasons.join(' ')).not.toContain('capped at moderate');
  });
});
