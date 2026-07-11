import { describe, it, expect } from 'vitest';
import { scanEscalation, isNegated } from '@/lib/human-systems';

// MSN-0351 (clinical safety): the red-flag scan must fire on a genuine report
// but NOT on a denial ("no chest pain", "denies suicidal ideation"). These
// tests lock in both the true-positive path per category and the negated
// false-positive path per category.

describe('isNegated — preceding-window negation check', () => {
  it('treats a match at the very start of the note as NOT negated', () => {
    const text = 'chest pain since this morning';
    expect(isNegated(text, text.indexOf('chest'))).toBe(false);
  });

  it('flags a match preceded by "no"', () => {
    const text = 'no chest pain today';
    expect(isNegated(text, text.indexOf('chest'))).toBe(true);
  });

  it('flags a match preceded by "denies"', () => {
    const text = 'denies suicidal ideation';
    expect(isNegated(text, text.indexOf('suicidal'))).toBe(true);
  });

  it('flags a match preceded by "negative for"', () => {
    const text = 'negative for infection on review';
    expect(isNegated(text, text.indexOf('infection'))).toBe(true);
  });

  it('flags a match preceded by "ruled out"', () => {
    const text = 'ruled out infection at the GP';
    expect(isNegated(text, text.indexOf('infection'))).toBe(true);
  });

  it('does NOT flag a genuine report several words in', () => {
    const text = 'woke feeling rough and then chest pain started';
    expect(isNegated(text, text.indexOf('chest'))).toBe(false);
  });
});

describe('scanEscalation — true positives per red-flag category', () => {
  it('fires on suicidal ideation', () => {
    const out = scanEscalation('I keep thinking I want to die');
    expect(out).not.toBeNull();
    expect(out).toMatch(/999|Samaritans|crisis/i);
  });

  it('fires on chest pain / breathing difficulty', () => {
    const out = scanEscalation('chest pain since this morning, feels tight');
    expect(out).not.toBeNull();
    expect(out).toMatch(/emergency|999/i);
  });

  it('fires on new neurological symptoms', () => {
    const out = scanEscalation('new numbness in my left leg since yesterday');
    expect(out).not.toBeNull();
    expect(out).toMatch(/neurological|urgent/i);
  });

  it('fires on fever / infection', () => {
    const out = scanEscalation('spiking a fever overnight and feel awful');
    expect(out).not.toBeNull();
    expect(out).toMatch(/fever|infection|GP|111/i);
  });
});

describe('scanEscalation — negated notes must NOT fire (per category)', () => {
  it('does not fire on denied suicidal ideation', () => {
    expect(scanEscalation('denies suicidal ideation, mood stable')).toBeNull();
  });

  it('does not fire on denied chest pain', () => {
    expect(scanEscalation('no chest pain today, breathing fine')).toBeNull();
  });

  it('does not fire on denied new neuro symptoms', () => {
    expect(scanEscalation('no new numbness or weakness')).toBeNull();
  });

  it('does not fire on ruled-out infection', () => {
    expect(scanEscalation('negative for infection, no fever')).toBeNull();
  });
});

describe('scanEscalation — robustness', () => {
  it('returns null for empty / nullish notes', () => {
    expect(scanEscalation(null)).toBeNull();
    expect(scanEscalation(undefined)).toBeNull();
    expect(scanEscalation('')).toBeNull();
  });

  it('still escalates when a denial is followed by a genuine report of the same category', () => {
    const out = scanEscalation('no chest pain earlier but chest tightness now');
    expect(out).not.toBeNull();
    expect(out).toMatch(/emergency|999/i);
  });

  it('prioritises the urgent message first when multiple flags are present', () => {
    const out = scanEscalation('chest pain and also a fever');
    expect(out).not.toBeNull();
    // urgent (chest) sorts ahead of non-urgent (fever)
    expect(out!.indexOf('999')).toBeLessThan(out!.search(/GP|111/i));
  });
});
