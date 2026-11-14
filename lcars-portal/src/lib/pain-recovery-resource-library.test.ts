import { describe, expect, it } from 'vitest';
import { resourceLibrary } from './pain-recovery-resource-library';

describe('phase 6 human resource governance', () => {
  it('keeps every resource labelled with format, energy, accessibility and review date', () => {
    expect(resourceLibrary.every(resource => resource.format && resource.energy && resource.accessibility && /^2026-/.test(resource.reviewed))).toBe(true);
  });
  it('includes human-led media landing pages without autoplay requirements', () => {
    expect(resourceLibrary.find(resource => resource.format === 'video')?.accessibility).toContain('no autoplay');
    expect(resourceLibrary.find(resource => resource.format === 'podcast')?.accessibility).toContain('transcript');
  });
});
