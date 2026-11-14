import { describe, expect, it } from 'vitest';
import { companionCopy, shouldOfferReentry } from './pain-recovery-companion';

describe('Phase 3 active-day companion', () => {
  it('offers non-judgemental re-entry after a gap', () => {
    expect(shouldOfferReentry('2026-11-12', '2026-11-14')).toBe(true);
    expect(companionCopy({stage:'morning',returningAfterGap:true}).title).toContain('today');
  });
  it('keeps deferred actions adaptive', () => expect(companionCopy({stage:'deferred',actionStatus:'deferred'}).body).toMatch(/smaller|stop/i));
  it('holds safety above the day guide', () => expect(companionCopy({stage:'safety_hold'}).primary).toBe('Open safety card'));
});
