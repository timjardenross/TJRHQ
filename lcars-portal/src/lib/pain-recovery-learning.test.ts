import { describe, expect, it } from 'vitest';
import { findSimilarDays, normalizeCost, tomorrowPrompt, upsertLearningRecord } from './pain-recovery-learning';

describe('phase 5 learning loop', () => {
  it('starts lighter after a costly day', () => expect(tomorrowPrompt('Today was harder than expected.')).toContain('start lighter'));
  it('carries forward a useful ingredient without demanding repetition', () => expect(tomorrowPrompt('I know one thing to repeat tomorrow.')).toContain('ingredient'));
  it('has a gentle default after an incomplete record', () => expect(tomorrowPrompt()).toContain('Start with today'));
  it('normalises a zero cost without turning it into a truthy value', () => expect(normalizeCost('0')).toBe(0));
  it('updates a date rather than duplicating it', () => expect(upsertLearningRecord([{date:'2026-11-14',learningNote:'old'}], {date:'2026-11-14',learningNote:'new'})).toHaveLength(1));
  it('only offers a pattern from comparable days', () => expect(findSimilarDays({date:'2026-11-15',colour:'Amber',energy:'low',sleep:'poor',demand:'heavy'}, [{date:'2026-11-14',colour:'Amber',energy:'low',sleep:'poor',demand:'heavy'}])).toHaveLength(1));
});
