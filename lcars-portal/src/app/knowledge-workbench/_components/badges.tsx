'use client';

import type {
  DocumentSensitivity,
  ReviewDecision,
  ReviewStatus,
} from '@/lib/types';

export const DECISION_LABELS: Record<ReviewDecision, string> = {
  approved_metadata: 'Approve — Metadata Only',
  approved_summary: 'Approve — Summary to Memory',
  approved_chunks: 'Approve — Full Chunk Memory',
  rejected: 'Reject',
  needs_review: 'Mark Needs Review',
};

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  awaiting_followup: 'Awaiting Follow-Up',
  resolved: 'Resolved',
  rejected: 'Rejected',
};

export function sensitivityTone(s: DocumentSensitivity): 'status' | 'command' | 'operations' {
  if (s === 'restricted') return 'operations';
  if (s === 'sensitive') return 'command';
  return 'status';
}

export function formatBytes(n: number | null): string {
  if (!n) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
