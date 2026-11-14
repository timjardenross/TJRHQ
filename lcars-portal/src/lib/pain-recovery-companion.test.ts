import { describe, expect, it } from 'vitest';
import { companionCopy, primaryJourneyCopy, resolvePrimaryJourney, shouldOfferReentry } from './pain-recovery-companion';

describe('Phase 3 active-day companion', () => {
  it('offers non-judgemental re-entry after a gap', () => {
    expect(shouldOfferReentry('2026-11-12', '2026-11-14')).toBe(true);
    expect(companionCopy({stage:'morning',returningAfterGap:true}).title).toContain('today');
  });
  it('keeps deferred actions adaptive', () => expect(companionCopy({stage:'deferred',actionStatus:'deferred'}).body).toMatch(/smaller|stop/i));
  it('holds safety above the day guide', () => expect(companionCopy({stage:'safety_hold'}).primary).toBe('Open safety card'));
});

describe('phase 9 slice A primary journeys', () => {
  it('resolves explicit journey intent before internal stage', () => {
    expect(resolvePrimaryJourney({ stage: 'active', journey: 'start_my_day' })).toBe('start_my_day');
    expect(resolvePrimaryJourney({ stage: 'active', journey: 'something_changed' })).toBe('something_changed');
  });

  it('maps an untouched morning to a short start-my-day journey', () => {
    const guide = primaryJourneyCopy({ stage: 'morning' });
    expect(guide.journey).toBe('start_my_day');
    expect(guide.primary).toBe('Check in with today');
    expect(guide.nextStep).toMatch(/capacity/i);
    expect(guide.showSafety).toBe(true);
  });

  it('makes help-me-now action-first and non-punitive', () => {
    const guide = primaryJourneyCopy({ stage: 'active', currentAction: 'Take the shortest familiar walk.' });
    expect(guide.journey).toBe('help_me_now');
    expect(guide.title).toContain('shortest familiar walk');
    expect(guide.primary).toBe('Help me do this');
    expect(guide.body).toMatch(/smaller|stop/i);
  });

  it('turns something-changed into adjustment rather than catch-up', () => {
    const guide = primaryJourneyCopy({ stage: 'active', journey: 'something_changed' });
    expect(guide.journey).toBe('something_changed');
    expect(guide.primary).toBe('Tell the Studio what changed');
    expect(guide.body).toMatch(/without starting over/i);
    expect(guide.nextStep).toMatch(/least demanding/i);
  });

  it('keeps a Red day separate from the safety boundary and exercise plan', () => {
    const guide = primaryJourneyCopy({ stage: 'deferred', chosenColour: 'Red' });
    expect(guide.journey).toBe('something_changed');
    expect(guide.primary).toBe('Open the Red-day plan');
    expect(guide.body).toMatch(/Peter’s exercise plan/);
    expect(guide.showSafety).toBe(true);
  });

  it('makes an explicit safety hold the highest-priority journey', () => {
    const guide = primaryJourneyCopy({ stage: 'safety_hold', journey: 'help_me_now' });
    expect(guide.journey).toBe('something_changed');
    expect(guide.primary).toBe('Open the safety card');
    expect(guide.body).toMatch(/will not interpret/i);
  });
});
