import { describe, expect, it } from 'vitest';
import { isSafetyConcern } from './pain-recovery-studio-guards';
import { activityGuidanceBoundary } from './pain-recovery-activity-guidance';

describe('phase 8 release invariants', () => {
  it('keeps crisis language inside the static safety boundary', () => {
    expect(isSafetyConcern('I want to end my life')).toBe(true);
    expect(isSafetyConcern('something feels concerning')).toBe(true);
  });
  it('keeps activity pauses above activity coaching', () => {
    expect(activityGuidanceBoundary('pause')).toBe('safety_hold');
  });
});
