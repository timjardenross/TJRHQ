export type LifecycleFilter = 'blocked' | 'overdue' | 'stale' | 'awaiting-owner';

export const LIFECYCLE_FILTERS: readonly { value: LifecycleFilter; label: string }[] = [
  { value: 'blocked', label: 'Blocked' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'stale', label: 'Stale' },
  { value: 'awaiting-owner', label: 'Awaiting owner' },
];

/** Derive one explicit lifecycle state from source-provided command metadata. */
export function deriveLifecycleState(input: {
  status?: unknown;
  lifecycle?: unknown;
  dueAt?: unknown;
  updatedAt?: unknown;
  owner?: unknown;
}): LifecycleFilter | null {
  const status = String(input.lifecycle ?? input.status ?? '').trim().toLowerCase().replace(/[_\s]+/g, '-');
  if (['blocked', 'blocked-from-triage', 'failed'].includes(status)) return 'blocked';
  if (['awaiting-owner', 'unassigned', 'owner-needed', 'needs-owner'].includes(status)) return 'awaiting-owner';

  if (input.dueAt) {
    const due = new Date(String(input.dueAt)).getTime();
    if (Number.isFinite(due) && due < Date.now() && !['completed', 'complete', 'cancelled', 'rejected'].includes(status)) return 'overdue';
  }

  if (['stale', 'expired', 'out-of-date'].includes(status)) return 'stale';
  return null;
}
