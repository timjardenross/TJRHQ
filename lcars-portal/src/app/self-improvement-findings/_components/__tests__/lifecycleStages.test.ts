import { describe, expect, it } from 'vitest';

import { normaliseOpportunity, type LifecycleStage, type LifecycleState } from '../types';

// The workbench shows 4 stages (To decide / In progress / Done / Closed) but the
// engine still acts on the finer state, which survives as stage_detail. The
// portal must read either vocabulary so it can deploy before OR after the
// engine change.

const FINE_TO_STAGE: Array<[LifecycleState, LifecycleStage]> = [
  ['discovered', 'researching'],
  ['investigating', 'researching'],
  ['proposed', 'to_decide'],
  ['approved', 'in_progress'],
  ['implementing', 'in_progress'],
  ['verifying', 'in_progress'],
  ['learned', 'done'],
  ['watching', 'closed'],
  ['rejected', 'closed'],
  ['resolved_before_research', 'closed'],
];

describe('normaliseOpportunity', () => {
  it.each(FINE_TO_STAGE)('old API: lifecycle_state %s -> stage %s, fine state kept', (fine, stage) => {
    const out = normaliseOpportunity({ opportunity_id: 'EVO-1', lifecycle_state: fine });
    expect(out.lifecycle_state).toBe(fine);
    expect(out.stage_detail).toBe(fine);
    expect(out.stage).toBe(stage);
  });

  it.each(FINE_TO_STAGE)('new API: stage %s + stage_detail %s -> same result', (fine, stage) => {
    const out = normaliseOpportunity({ opportunity_id: 'EVO-1', lifecycle_state: stage, stage_detail: fine });
    expect(out.lifecycle_state).toBe(fine);
    expect(out.stage_detail).toBe(fine);
    expect(out.stage).toBe(stage);
  });

  it('new API without stage_detail falls back to a sensible fine state for the stage', () => {
    expect(normaliseOpportunity({ lifecycle_state: 'to_decide' }).lifecycle_state).toBe('proposed');
    expect(normaliseOpportunity({ lifecycle_state: 'in_progress' }).lifecycle_state).toBe('approved');
    expect(normaliseOpportunity({ lifecycle_state: 'done' }).lifecycle_state).toBe('learned');
    expect(normaliseOpportunity({ lifecycle_state: 'closed' }).lifecycle_state).toBe('rejected');
    expect(normaliseOpportunity({ lifecycle_state: 'researching' }).stage).toBe('researching');
  });

  it('a stage_detail that contradicts nothing but is unknown is ignored in favour of lifecycle_state', () => {
    const out = normaliseOpportunity({ lifecycle_state: 'verifying', stage_detail: 'made_up' });
    expect(out.lifecycle_state).toBe('verifying');
    expect(out.stage).toBe('in_progress');
  });

  it('an unknown or missing state does not crash and is treated as still researching', () => {
    expect(normaliseOpportunity({ lifecycle_state: 'bogus' }).stage).toBe('researching');
    expect(normaliseOpportunity({ lifecycle_state: '' }).stage).toBe('researching');
  });

  it('keeps every other field untouched', () => {
    const out = normaliseOpportunity({ opportunity_id: 'EVO-9', title: 'T', mission_id: 'M-1', lifecycle_state: 'verifying' });
    expect(out).toMatchObject({ opportunity_id: 'EVO-9', title: 'T', mission_id: 'M-1' });
  });
});
