// Shared constants for the Mission Workbench (look-and-feel migration of
// (app)/missions + (app)/missions/[id]). Mirrors comms-workbench /
// intelligence-workbench: standalone Shell (no LCARS app chrome), TJR
// Design System components (@/components/ui), wb-* tokens.
//
// All mutation logic (routes, eligibility lists, status vocabulary) is
// copied VERBATIM from the LCARS originals — this file changes nothing
// about what's allowed, only how it's rendered. See:
//   - lcars-portal/src/lib/missionStatus.ts (still imported directly, unchanged)
//   - lcars-portal/src/app/(app)/missions/[id]/page.tsx (APPROVAL_ELIGIBLE / REJECTION_ELIGIBLE / STATUS_OPTIONS)

import type { BadgeStatus } from '@/components/ui';

// Canonical Supabase status values (CHECK constraint on missions.status).
export const STATUS_OPTIONS = [
  'Idea', 'Designed', 'Approved for Engineering', 'Implemented', 'Tested',
  'Awaiting Number One Review', 'Validated', 'Awaiting XO Approval',
  'Awaiting Captain Approval', 'Approved',
  'Blocked', 'Requires Rework', 'Closed', 'Archived',
];

// MSN-0328 (WP-C/D): mirrors the eligibility lists the governed /approve and
// /reject routes themselves enforce (api/missions/[id]/{approve,reject}/route.ts)
// — kept in sync manually since these routes have no shared client-exported
// constant; a mismatch here only affects which buttons render, since the
// routes remain the actual source of truth (a 409 is still possible if this
// list ever drifts).
export const APPROVAL_ELIGIBLE = ['Awaiting Captain Approval', 'Awaiting XO Approval', 'Validated', 'Tested'];
export const REJECTION_ELIGIBLE = ['Awaiting Captain Approval', 'Awaiting XO Approval', 'Validated', 'Tested', 'Implemented', 'Designed'];

export function statusToBadge(status: string): BadgeStatus {
  if (status === 'Blocked' || status === 'Requires Rework') return 'error';
  if (status.startsWith('Awaiting') || status === 'Validated' || status === 'Tested') return 'warning';
  if (status === 'Approved' || status === 'Closed') return 'success';
  return 'neutral';
}

export function fmtDate(iso?: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}
