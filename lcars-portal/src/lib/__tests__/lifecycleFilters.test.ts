import { describe, expect, it } from 'vitest';
import { LIFECYCLE_FILTERS, deriveLifecycleState } from '@/lib/lifecycleFilters';

describe('lifecycle filter contract', () => {
  it('exposes the four shared lifecycle filters used by Search and Timeline', () => {
    expect(LIFECYCLE_FILTERS.map(f => f.value)).toEqual(['blocked', 'overdue', 'stale', 'awaiting-owner']);
  });

  it('derives blocked/awaiting-owner/stale from explicit status or lifecycle metadata', () => {
    expect(deriveLifecycleState({ status: 'blocked' })).toBe('blocked');
    expect(deriveLifecycleState({ lifecycle: 'failed' })).toBe('blocked');
    expect(deriveLifecycleState({ status: 'unassigned' })).toBe('awaiting-owner');
    expect(deriveLifecycleState({ lifecycle: 'owner_needed' })).toBe('awaiting-owner');
    expect(deriveLifecycleState({ status: 'expired' })).toBe('stale');
  });

  it('derives overdue only from an explicit dueAt in the past, and not for terminal statuses', () => {
    const past = new Date(Date.now() - 86_400_000).toISOString();
    const future = new Date(Date.now() + 86_400_000).toISOString();
    expect(deriveLifecycleState({ dueAt: past })).toBe('overdue');
    expect(deriveLifecycleState({ dueAt: future })).toBeNull();
    expect(deriveLifecycleState({ dueAt: past, status: 'completed' })).toBeNull();
    expect(deriveLifecycleState({ dueAt: past, status: 'cancelled' })).toBeNull();
  });

  it('never promotes null/absent metadata to a lifecycle state (regression: null must stay null, not "quiet")', () => {
    expect(deriveLifecycleState({})).toBeNull();
    expect(deriveLifecycleState({ status: null, lifecycle: null, dueAt: null, owner: null })).toBeNull();
    expect(deriveLifecycleState({ status: undefined })).toBeNull();
    expect(deriveLifecycleState({ status: 'in-progress' })).toBeNull();
  });

  it('does not accept or consult title/detail text — the input contract has no such fields', () => {
    // Regression guard for "filters must not infer urgency from title/detail
    // text": deriveLifecycleState's input type only accepts explicit command
    // metadata (status, lifecycle, dueAt, updatedAt, owner). Passing
    // alarming free-text under an unrecognised key must have zero effect,
    // proving the derivation never reads prose for signal.
    const withAlarmingText = {
      status: undefined,
      title: 'URGENT BLOCKED overdue stale awaiting owner action required now',
      detail: 'This is critically overdue and blocked and stale, please action immediately',
    } as Record<string, unknown>;
    expect(deriveLifecycleState(withAlarmingText)).toBeNull();
  });
});
