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

describe('state-based "pain trend elevated": 3 of the last 5 at elevated or high', () => {
  const row = (state: string | null, n: number) => ({ pain_state: state, pain_score: null, captured_at: t(n) });
  // newest first, like the query (order captured_at desc, limit 5)

  it('2 of 5 does not fire', () => {
    expect(evaluatePainSignal([row('baseline', 5), row('elevated', 4), row('baseline', 3), row('elevated', 2), row('low', 1)])).toBeNull();
  });
  it('exactly 3 of 5 fires (boundary), high severity kind', () => {
    expect(evaluatePainSignal([row('baseline', 5), row('elevated', 4), row('baseline', 3), row('elevated', 2), row('elevated', 1)]))
      .toEqual({ kind: 'state_trend_elevated', count: 3, window: 5, evidenceAt: t(5) });
  });
  it('counts "much higher than usual" days that are not the latest', () => {
    expect(evaluatePainSignal([row('baseline', 5), row('high', 4), row('high', 3), row('elevated', 2), row('low', 1)]))
      .toMatchObject({ kind: 'state_trend_elevated', count: 3 });
  });
  it('latest "much higher" is the red flag, not the trend (the trend does not double-fire)', () => {
    expect(evaluatePainSignal([row('high', 5), row('elevated', 4), row('elevated', 3), row('elevated', 2), row('elevated', 1)])?.kind).toBe('state_high');
  });
  it('only the 5 newest rows count (older elevated rows outside the window are ignored)', () => {
    const rows = [row('baseline', 9), row('baseline', 8), row('baseline', 7), row('elevated', 6), row('elevated', 5), row('elevated', 4), row('elevated', 3)];
    // newest 5 = baseline x3 + elevated x2 -> 2 of 5
    expect(evaluatePainSignal(rows)).toBeNull();
  });
  it('a check-in with no pain state is not counted as elevated and not as "no pain"', () => {
    expect(evaluatePainSignal([row(null, 5), row('elevated', 4), row(null, 3), row('elevated', 2), row('baseline', 1)])).toBeNull();
    expect(evaluatePainSignal([row(null, 5), row('elevated', 4), row(null, 3), row('elevated', 2), row('elevated', 1)])?.kind).toBe('state_trend_elevated');
  });
  it('fewer than 5 check-ins: 3 of 3 fires, 2 of 2 does not', () => {
    expect(evaluatePainSignal([row('elevated', 3), row('elevated', 2), row('high', 1)])).toMatchObject({ kind: 'state_trend_elevated', count: 3, window: 3 });
    expect(evaluatePainSignal([row('elevated', 2), row('elevated', 1)])).toBeNull();
  });
  it('legacy numeric critical still wins over the softer state trend', () => {
    const rows = [
      { pain_state: 'elevated', pain_score: 9, captured_at: t(3) },
      { pain_state: 'elevated', pain_score: 9, captured_at: t(2) },
      { pain_state: 'elevated', pain_score: 9, captured_at: t(1) },
    ];
    expect(evaluatePainSignal(rows)?.kind).toBe('trend_critical');
  });
  it('legacy numeric elevated still fires when the state trend does not', () => {
    expect(evaluatePainSignal([
      { pain_state: 'baseline', pain_score: 7, captured_at: t(2) },
      { pain_state: 'baseline', pain_score: 7, captured_at: t(1) },
    ])?.kind).toBe('trend_elevated');
  });
});
