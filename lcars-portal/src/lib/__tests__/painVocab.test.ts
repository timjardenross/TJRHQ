import { describe, it, expect } from 'vitest';
import { describePain, painStateLabel, PAIN_STATE_LABELS } from '../pain-vocab';

describe('pain vocabulary (readers)', () => {
  it('labels each state with the approved wording', () => {
    expect(Object.values(PAIN_STATE_LABELS)).toEqual([
      'Lower than usual', 'Around usual', 'Higher than usual', 'Much higher than usual',
    ]);
    expect(painStateLabel('baseline')).toBe('Around usual');
  });
  it('shows a new reading without a number', () => {
    expect(describePain('elevated', null)).toBe('Higher than usual');
  });
  it('labels an old numeric-only value as history', () => {
    expect(describePain(null, 6)).toBe('Older 0–10 record: 6/10');
  });
  it('keeps a real old 0 as history, not as "no pain"', () => {
    expect(describePain(null, 0)).toBe('Older 0–10 record: 0/10');
  });
  it('appends history when both exist', () => {
    expect(describePain('high', 9)).toBe('Much higher than usual (older 0–10 record: 9/10)');
  });
  it('returns null — never zero or "no pain" — when nothing was recorded', () => {
    expect(describePain(null, null)).toBeNull();
    expect(describePain(undefined, undefined)).toBeNull();
    expect(describePain('unknown', null)).toBeNull();
  });
});
