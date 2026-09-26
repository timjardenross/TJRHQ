import { describe, expect, it } from 'vitest';
import { isEvidenceState, isFreshnessState, type DomainRecord } from '@/lib/designContracts';

describe('shared domain contracts', () => {
  it('accepts only the canonical evidence and freshness states', () => {
    expect(isEvidenceState('stale')).toBe(true);
    expect(isEvidenceState('missing')).toBe(false);
    expect(isFreshnessState('unavailable')).toBe(true);
    expect(isFreshnessState('old')).toBe(false);
  });

  it('supports a complete cross-portal domain envelope', () => {
    const record: DomainRecord = {
      id: 'task-1', title: 'Review queue', state: 'awaiting-owner',
      owner: { label: 'Captain TJR', kind: 'captain' },
      freshness: { state: 'fresh', observedAt: '2026-09-21T00:00:00Z' },
      attention: { state: 'needs-action', reason: 'Waiting for a decision' },
      evidence: { source: 'Task registry', state: 'no-action' },
      actions: [{ action: 'review', label: 'Review', outcome: 'in-progress' }],
    };
    expect(record.attention.state).toBe('needs-action');
    expect(record.owner.kind).toBe('captain');
  });
});
