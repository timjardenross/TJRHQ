import { describe, it, expect } from 'vitest';
import { evaluatePainSignal } from '../painSignal';

const t = (n: number) => `2026-10-1${n}T08:00:00Z`;

describe('red flag: latest pain_state "high", regardless of capacity', () => {
  it('fires on a high state with no number at all', () => {
    expect(evaluatePainSignal([{ pain_state: 'high', pain_score: null, captured_at: t(2) }]))
      .toEqual({ kind: 'state_high', evidenceAt: t(2) });
  });
  it('fires whatever the capacity — capacity is not even an input', () => {
    // Same rows shape for Sustainable / Stretched / Depleted days: the signal cannot depend on it.
    const rows = [{ pain_state: 'high', captured_at: t(2) }];
    expect(evaluatePainSignal(rows)?.kind).toBe('state_high');
  });
  it('fires from the LATEST check-in only (an old high does not fire)', () => {
    expect(evaluatePainSignal([
      { pain_state: 'baseline', captured_at: t(3) },
      { pain_state: 'high', captured_at: t(2) },
    ])).toBeNull();
  });
  it.each(['low', 'baseline', 'elevated'])('does not fire on %s', (state) => {
    expect(evaluatePainSignal([{ pain_state: state, pain_score: null, captured_at: t(2) }])).toBeNull();
  });
});

describe('missing values are unknown — never zero', () => {
  it('no rows -> no signal', () => {
    expect(evaluatePainSignal([])).toBeNull();
  });
  it('rows with no state and no number -> no signal', () => {
    expect(evaluatePainSignal([{ captured_at: t(2) }, { pain_state: null, pain_score: null, captured_at: t(1) }])).toBeNull();
  });
  it('new check-ins without a number do NOT dilute the legacy average toward zero', () => {
    // Old behaviour: (9 + 0 + 0 + 0 + 0) / 5 = 1.8 -> silent. Now: only recorded numbers count -> 9.
    const rows = [
      { pain_state: 'baseline', pain_score: null, captured_at: t(5) },
      { pain_state: 'baseline', pain_score: null, captured_at: t(4) },
      { pain_state: 'baseline', pain_score: null, captured_at: t(3) },
      { pain_state: 'baseline', pain_score: null, captured_at: t(2) },
      { pain_state: null, pain_score: 9, captured_at: t(1) },
    ];
    expect(evaluatePainSignal(rows)).toMatchObject({ kind: 'trend_critical', avg: 9, n: 1 });
  });
});

describe('legacy numeric history (thresholds unchanged)', () => {
  it('> 8 is critical, > 6 is elevated, <= 6 is silent', () => {
    expect(evaluatePainSignal([{ pain_score: 9, captured_at: t(2) }, { pain_score: 9, captured_at: t(1) }])?.kind).toBe('trend_critical');
    expect(evaluatePainSignal([{ pain_score: 7, captured_at: t(2) }, { pain_score: 7, captured_at: t(1) }])?.kind).toBe('trend_elevated');
    expect(evaluatePainSignal([{ pain_score: 6, captured_at: t(2) }])).toBeNull();
  });
});
