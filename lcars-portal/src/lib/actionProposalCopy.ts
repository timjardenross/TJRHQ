import type { ActionResult } from './ai-actions';

// MSN-0352: the one place chat-surface copy is generated for a proposed
// action's outcome. Deliberately a plain, testable function rather than
// JSX-inline text, so "never claims completed when only proposed" is a
// property this file can assert in a unit test - not just a convention
// developers are trusted to preserve by eye. Called from the code path
// that reads the backend's own ActionResult objects, never from anything
// the model itself generated.

export function describeProposalOutcome(result: ActionResult): string {
  if (result.success) {
    return `Proposed, not yet performed. ${result.detail}. Nothing will happen until you approve it in Decide.`;
  }
  return `Could not queue this proposal. ${result.detail}`;
}

const COMPLETION_CLAIM_WORDS = ['created', 'logged', 'dispatched', 'registered', 'executed', 'performed the'];

/** Guards against the exact regression this mission exists to prevent: a
 * "success" proposal message that reads as if the action already happened.
 * Used both by the UI copy above and by its own test. */
export function assertNeverClaimsCompletion(message: string): void {
  const lower = message.toLowerCase();
  for (const word of COMPLETION_CLAIM_WORDS) {
    if (lower.includes(word)) {
      throw new Error(`Proposal copy must never claim completion (found "${word}"): ${message}`);
    }
  }
}
