import { describe, it, expect } from 'vitest';
import { deriveRisk, signalMatchesRisk } from '@/lib/intelligenceRisk';

describe('deriveRisk', () => {
  it('returns HIGH when customer_impact is high', () => {
    expect(deriveRisk({ customer_impact: 'high' })).toBe('HIGH');
  });

  it('returns HIGH when banking_relevance is high (even if customer_impact is lower)', () => {
    // Regression: this item used to be dropped by a customer_impact-only filter.
    expect(deriveRisk({ customer_impact: 'low', banking_relevance: 'high' })).toBe('HIGH');
  });

  it('prefers HIGH over MEDIUM when both signals are present', () => {
    expect(deriveRisk({ customer_impact: 'medium', banking_relevance: 'high' })).toBe('HIGH');
  });

  it('returns MEDIUM when either field is medium and neither is high', () => {
    expect(deriveRisk({ banking_relevance: 'medium' })).toBe('MEDIUM');
    expect(deriveRisk({ customer_impact: 'medium', banking_relevance: 'low' })).toBe('MEDIUM');
  });

  it('returns LOW when only low signals are present', () => {
    expect(deriveRisk({ customer_impact: 'low' })).toBe('LOW');
  });

  it('returns empty string when nothing recognisable is set', () => {
    expect(deriveRisk({})).toBe('');
    expect(deriveRisk({ customer_impact: null, banking_relevance: undefined })).toBe('');
    expect(deriveRisk({ customer_impact: 'n/a' })).toBe('');
  });

  it('is case-insensitive on stored values', () => {
    expect(deriveRisk({ customer_impact: 'HIGH' })).toBe('HIGH');
  });
});

describe('signalMatchesRisk', () => {
  it('matches when derived risk equals the wanted level', () => {
    expect(signalMatchesRisk({ customer_impact: 'high' }, 'HIGH')).toBe(true);
    expect(signalMatchesRisk({ banking_relevance: 'high' }, 'HIGH')).toBe(true);
  });

  it('includes items that are HIGH only via banking_relevance (the fixed filter bug)', () => {
    const bankingOnlyHigh = { customer_impact: 'medium', banking_relevance: 'high' };
    expect(signalMatchesRisk(bankingOnlyHigh, 'HIGH')).toBe(true);
    // and it must NOT show up when filtering to MEDIUM — its derived risk is HIGH
    expect(signalMatchesRisk(bankingOnlyHigh, 'MEDIUM')).toBe(false);
  });

  it('does not match a different level', () => {
    expect(signalMatchesRisk({ customer_impact: 'low' }, 'HIGH')).toBe(false);
  });

  it('matches everything when no filter level is given', () => {
    expect(signalMatchesRisk({ customer_impact: 'low' }, '')).toBe(true);
  });
});
