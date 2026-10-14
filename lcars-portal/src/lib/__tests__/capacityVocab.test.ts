import { describe, it, expect } from 'vitest';
import { normalizeCapacityCode, capacityLabel, helpfulFactorCode, helpfulFactorLabel, HELPFUL_FACTOR_LABELS } from '../capacity-vocab';
import { deriveSystemPosture, type TodayCheckinInput } from '@/app/api/human-systems/derive-system-posture';

const base: TodayCheckinInput = {
  capacity_state: null,
  regulation_state: 'settled',
  executive_function: 'good',
  compensation_load: 'low',
  stimulation_state: 'balanced',
  pain_state: 'baseline',
};

describe('normalizeCapacityCode', () => {
  it.each([
    ['green', 'green'], ['Green', 'green'], ['GREEN', 'green'], ['sustainable', 'green'],
    ['orange', 'orange'], ['amber', 'orange'], ['Amber', 'orange'], ['AMBER', 'orange'], ['stretched', 'orange'],
    ['red', 'red'], ['Red', 'red'], ['depleted', 'red'],
  ])('%s -> %s', (input, expected) => {
    expect(normalizeCapacityCode(input)).toBe(expected);
  });
  it('returns null for unknown, empty, null', () => {
    expect(normalizeCapacityCode('purple')).toBeNull();
    expect(normalizeCapacityCode('')).toBeNull();
    expect(normalizeCapacityCode(null)).toBeNull();
    expect(normalizeCapacityCode(undefined)).toBeNull();
  });
});

describe('capacityLabel', () => {
  it('uses the shared labels', () => {
    expect(capacityLabel('green')).toBe('Sustainable');
    expect(capacityLabel('Amber')).toBe('Stretched');
    expect(capacityLabel('red')).toBe('Depleted');
  });
  it('never shows raw codes for unknown values', () => {
    expect(capacityLabel(null)).toBe('Not yet known');
    expect(capacityLabel('UNKNOWN')).toBe('Not yet known');
  });
});

describe('deriveSystemPosture normalises stored capacity_state', () => {
  it.each(['amber', 'Amber', 'AMBER', 'orange'])('stored %s -> PROTECT, not STEADY', (cap) => {
    expect(deriveSystemPosture({ ...base, capacity_state: cap }).posture).toBe('PROTECT');
  });
  it.each(['Red', 'red'])('stored %s -> RECOVER', (cap) => {
    expect(deriveSystemPosture({ ...base, capacity_state: cap }).posture).toBe('RECOVER');
  });
  it('Green with balanced stimulation -> ENGAGE', () => {
    expect(deriveSystemPosture({ ...base, capacity_state: 'Green' }).posture).toBe('ENGAGE');
  });
});

describe('helpfulFactorCode', () => {
  it.each(Object.entries(HELPFUL_FACTOR_LABELS))('code %s and its label both map to the code', (code, label) => {
    expect(helpfulFactorCode(code)).toBe(code);
    expect(helpfulFactorCode(label)).toBe(code);
    expect(helpfulFactorCode(label.toUpperCase())).toBe(code);
    expect(helpfulFactorLabel(code)).toBe(label);
  });
  it('maps unknown text to null, never guessing', () => {
    expect(helpfulFactorCode('Coffee')).toBeNull();
    expect(helpfulFactorCode('Interesting')).toBeNull();
    expect(helpfulFactorLabel('Coffee')).toBeNull();
  });
  it('maps null/undefined/empty to null', () => {
    expect(helpfulFactorCode(null)).toBeNull();
    expect(helpfulFactorCode(undefined)).toBeNull();
    expect(helpfulFactorCode('')).toBeNull();
  });
});
