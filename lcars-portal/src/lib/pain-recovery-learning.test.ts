import { describe, expect, it } from 'vitest';
import { tomorrowPrompt } from './pain-recovery-learning';

describe('phase 5 learning loop', () => {
  it('starts lighter after a costly day', () => expect(tomorrowPrompt('Today was harder than expected.')).toContain('start lighter'));
  it('carries forward a useful ingredient without demanding repetition', () => expect(tomorrowPrompt('I know one thing to repeat tomorrow.')).toContain('ingredient'));
  it('has a gentle default after an incomplete record', () => expect(tomorrowPrompt()).toContain('Start with today'));
});
