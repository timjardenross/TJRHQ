import { describe, expect, it } from 'vitest';
import { resourceLibrary } from './pain-recovery-resource-library';
import { contextualReason, resourcesForNeed } from './pain-recovery-resource-context';
describe('phase 9 contextual resource presentation', () => {
  it('maps a practical need to curated pacing resources only', () => {
    const resources = resourcesForNeed(resourceLibrary, 'pace');
    expect(resources.length).toBeGreaterThan(0);
    expect(resources.every((resource) => resource.kind === 'pacing' || resource.domain === 'biological')).toBe(true);
    expect(resources.every((resource) => resource.url.startsWith('https://'))).toBe(true);
  });
  it('keeps exploration available when a context has no direct match', () => {
    const resources = resourcesForNeed(resourceLibrary, 'connect');
    expect(resources.length).toBeGreaterThan(0);
    expect(contextualReason(resources[0], 'explore')).toContain('resource');
  });
});
