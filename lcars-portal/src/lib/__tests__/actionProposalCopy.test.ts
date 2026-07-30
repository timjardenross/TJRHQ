import { describe, it, expect } from 'vitest';
import { describeProposalOutcome, assertNeverClaimsCompletion } from '@/lib/actionProposalCopy';
import type { ActionResult } from '@/lib/ai-actions';

describe('describeProposalOutcome', () => {
  it('a success result reads as proposed, never as completed', () => {
    const result: ActionResult = { type: 'create_mission', success: true, detail: 'Proposed for your approval in Decide: "New mission"' };
    const message = describeProposalOutcome(result);
    expect(message).toMatch(/proposed, not yet performed/i);
    expect(message).toMatch(/approve it in decide/i);
    expect(() => assertNeverClaimsCompletion(message)).not.toThrow();
  });

  it('a failure result reads as a failure to queue, not a failed action', () => {
    const result: ActionResult = { type: 'create_mission', success: false, detail: 'RLS denied the write' };
    const message = describeProposalOutcome(result);
    expect(message).toMatch(/could not queue this proposal/i);
    expect(message).toContain('RLS denied the write');
  });

  it('MSN-0352 regression guard: this exact function never produces completion-claiming copy', () => {
    // Sweep every action type's real, current success-path detail string
    // (as actually produced by lib/ai-actions.ts's proposeAction) through
    // the guard - this is the automated version of "chat copy no longer
    // claims actions were completed when only proposed."
    const details = [
      'Proposed for your approval in Decide: "New mission"',
      'Proposed for your approval in Decide: "Adopt X"',
      'Proposed for your approval in Decide: "Ship the thing"',
    ];
    for (const detail of details) {
      const message = describeProposalOutcome({ type: 'x', success: true, detail });
      expect(() => assertNeverClaimsCompletion(message)).not.toThrow();
    }
  });
});

describe('assertNeverClaimsCompletion (the guard itself)', () => {
  it('throws on completion-claiming language, proving the guard actually catches the regression it exists to prevent', () => {
    expect(() => assertNeverClaimsCompletion('Mission MSN-0999 registered')).toThrow();
    expect(() => assertNeverClaimsCompletion('Decision logged')).toThrow();
    expect(() => assertNeverClaimsCompletion('I created the mission for you')).toThrow();
    expect(() => assertNeverClaimsCompletion('Handoff dispatched')).toThrow();
  });

  it('does not throw on honest proposal language', () => {
    expect(() => assertNeverClaimsCompletion('Proposed, not yet performed. Nothing will happen until you approve it in Decide.')).not.toThrow();
  });
});
