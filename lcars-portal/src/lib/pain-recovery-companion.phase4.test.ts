import { describe, expect, it } from 'vitest';
import { dayGuideCopy } from './pain-recovery-companion';

describe('phase 4 day orchestration', () => {
  it('keeps the active day focused on now, next and later', () => {
    expect(dayGuideCopy({ stage: 'active', valuedActivity: 'dog walking', currentAction: 'Take the shortest familiar walk.' })).toEqual({
      now: 'Take the shortest familiar walk.',
      next: 'Check what has changed before continuing',
      later: 'Close the day without measuring your worth',
      primary: 'Guide me from here',
    });
  });

  it('does not turn a missed or deferred day into catch-up work', () => {
    expect(dayGuideCopy({ stage: 'deferred' }).later).toBe('No catch-up is required');
  });

  it('puts safety before day progression', () => {
    expect(dayGuideCopy({ stage: 'safety_hold' }).next).toBe('Pause ordinary coaching');
  });

  it('makes a scheduled return visible without adding urgency', () => {
    expect(dayGuideCopy({ stage: 'deferred', hasReminder: true }).next).toBe('Return when your check-in is ready');
  });
});
