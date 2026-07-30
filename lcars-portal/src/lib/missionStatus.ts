/**
 * Canonical mission status groupings — single source of truth for any page
 * that needs to bucket missions by lifecycle stage (WP A: Truth & Trust,
 * MSN-0321). Matches Supabase's `missions.status` CHECK constraint values.
 */

export const ACTIVE_STATUSES = [
  'Idea', 'Designed', 'Approved for Engineering', 'Implemented', 'Tested',
  'Awaiting Number One Review', 'Validated', 'Requires Rework', 'Blocked',
];

export const COMPLETED_STATUSES = ['Approved', 'Closed', 'Archived', 'Validated'];

/** Mirrors CaptainApprovalQueue.tsx's AWAITING_STATUSES. */
export const AWAITING_CAPTAIN_STATUSES = ['Awaiting Captain Approval', 'Awaiting XO Approval'];

/**
 * True terminal states — a mission here cannot become active again without a
 * status change, so nothing that only reads current state should ever
 * resurface one (MSN hygiene cleanup). NOT the same set as
 * COMPLETED_STATUSES above: that bucket also includes 'Approved' and
 * 'Validated', which are still-open, still-actionable states (11 and several
 * live rows respectively as of 2026-07 — excluding them would hide real
 * in-flight work, not just noise). 'Completed'/'Cancelled'/'Superseded' are
 * not live CHECK-constraint values today (only 'Closed' and 'Archived' are)
 * but are kept here defensively in case the status vocabulary grows to match
 * common lifecycle terminology. Note 'Requires Rework' (the real status a
 * Captain rejection lands on) is deliberately NOT terminal — a rejected
 * mission still needs someone to act on it, so hygiene checks should keep
 * catching it if it goes stale.
 */
export const TERMINAL_STATUSES = ['Closed', 'Archived', 'Completed', 'Cancelled', 'Superseded'];

/**
 * Statuses that mean "sitting waiting on a human review/approval decision".
 * Used by the "awaiting review" hygiene check — the pre-fix version matched
 * the literal string 'REVIEW', which is not and has never been a value the
 * missions.status CHECK constraint allows, so that check silently never
 * fired.
 */
export const REVIEW_PENDING_STATUSES = ['Awaiting Number One Review', ...AWAITING_CAPTAIN_STATUSES];
