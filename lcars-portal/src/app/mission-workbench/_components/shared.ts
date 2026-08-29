// Shared constants for the Mission Workbench (look-and-feel migration of
// (app)/missions + (app)/missions/[id]). Mirrors comms-workbench /
// intelligence-workbench: standalone Shell (no LCARS app chrome), TJR
// Design System components (@/components/ui), wb-* tokens.
//
// Status vocabulary is copied VERBATIM from the LCARS originals — this
// file changes nothing about what's allowed, only how it's rendered. See:
//   - lcars-portal/src/lib/missionStatus.ts (still imported directly, unchanged)
//
// 2026-08-29: APPROVAL_ELIGIBLE/REJECTION_ELIGIBLE removed along with the
// governed approve/reject routes they mirrored — see
// mission-workbench/[id]/page.tsx's header comment.

import type { BadgeStatus } from '@/components/ui';

// Canonical Supabase status values (CHECK constraint on missions.status).
export const STATUS_OPTIONS = [
  'Idea', 'Designed', 'Approved for Engineering', 'Implemented', 'Tested',
  'Awaiting Number One Review', 'Validated', 'Awaiting XO Approval',
  'Awaiting Captain Approval', 'Approved',
  'Blocked', 'Requires Rework', 'Closed', 'Archived',
];

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
