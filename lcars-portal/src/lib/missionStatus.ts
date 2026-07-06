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
