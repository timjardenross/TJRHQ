import { describe, expect, it } from 'vitest';
import { evidenceSegments, normaliseEvidence, normaliseRisk, riskTone } from '../vocab';

describe('HQ vocabulary keeps risk and evidence separate', () => {
  it('maps every platform risk spelling to three levels', () => {
    expect(['RED', 'high', 'critical', 'emergency_warning'].map(normaliseRisk)).toEqual(['High', 'High', 'High', 'High']);
    expect(['AMBER', 'medium', 'watch_and_act'].map(normaliseRisk)).toEqual(['Medium', 'Medium', 'Medium']);
    expect(['GREEN', 'low', 'advice'].map(normaliseRisk)).toEqual(['Low', 'Low', 'Low']);
  });
  it('does not guess an unrecognised risk', () => {
    expect(normaliseRisk('unassessed')).toBeNull();
    expect(normaliseRisk(null)).toBeNull();
    expect(normaliseRisk('')).toBeNull();
  });
  it('maps confidence labels and numbers onto the evidence scale', () => {
    expect(normaliseEvidence('high')).toBe('Strong');
    expect(normaliseEvidence('Moderate')).toBe('Moderate');
    expect(normaliseEvidence('low')).toBe('Limited');
    expect(normaliseEvidence('unknown')).toBe('Unknown');
    expect(normaliseEvidence(0.9)).toBe('Strong');
    expect(normaliseEvidence(55)).toBe('Moderate');
    expect(normaliseEvidence(0.1)).toBe('Limited');
  });
  it('high evidence is never a risk colour: evidence has no tone', () => {
    // Evidence is rendered as a neutral bar; only risk has a tone.
    expect(evidenceSegments('Strong')).toBe(3);
    expect(riskTone(normaliseRisk('high'))).toBe('red');
    expect(riskTone(null)).toBe('info');
  });
});
