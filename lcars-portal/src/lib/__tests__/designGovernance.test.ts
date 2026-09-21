import { describe, expect, it } from 'vitest';
import { CANONICAL_TERMS, DENSITY_CLASSES, LEGACY_TERM_REPLACEMENTS, validatePrimaryAction } from '@/lib/designGovernance';

describe('design-system governance', () => {
  it('keeps legacy labels mapped to canonical terms', () => {
    expect(LEGACY_TERM_REPLACEMENTS.Home).toBe(CANONICAL_TERMS.hub);
    expect(LEGACY_TERM_REPLACEMENTS["Captain's Brief"]).toBe(CANONICAL_TERMS.briefs);
  });

  it('defines an explicit density scale', () => {
    expect(Object.keys(DENSITY_CLASSES)).toEqual(['comfortable', 'compact', 'data-dense']);
  });

  it('rejects missing or generic primary actions', () => {
    expect(validatePrimaryAction(undefined)).toContain('missing primary action');
    expect(validatePrimaryAction({ label: 'Open', href: '/hub' })).toContain('primary action needs a specific verb');
    expect(validatePrimaryAction({ label: 'Review active alerts', href: '/alerts' })).toEqual([]);
  });
});
