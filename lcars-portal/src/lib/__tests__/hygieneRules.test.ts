import { describe, expect, it } from 'vitest';
import { dedupeMissionSignals, isGeneratedJunkMissionId, isHygieneEligible } from '@/lib/hygieneRules';
import { REVIEW_PENDING_STATUSES, TERMINAL_STATUSES } from '@/lib/missionStatus';

// Every value the missions.status CHECK constraint (migration 0013 +
// 0026/id-registry usage, mirrored in api/missions/route.ts VALID_STATUSES)
// actually allows today, plus the terminal synonyms this mission's brief
// named that aren't live values yet (Completed/Cancelled/Superseded).
const ACTIVE_LIVE_STATUSES = [
  'Idea',
  'Designed',
  'Approved for Engineering',
  'Implemented',
  'Tested',
  'Awaiting Number One Review',
  'Validated',
  'Awaiting XO Approval',
  'Awaiting Captain Approval',
  'Approved',
  'Blocked',
  'Requires Rework', // where a Captain rejection lands -- still actionable, not terminal
];

const TERMINAL_LIVE_STATUSES = ['Closed', 'Archived'];

const TERMINAL_DEFENSIVE_STATUSES = ['Completed', 'Cancelled', 'Superseded'];

describe('isHygieneEligible — every lifecycle state', () => {
  it.each(ACTIVE_LIVE_STATUSES)('keeps active status "%s"', (status) => {
    expect(isHygieneEligible(status, 'MSN-TEST-0001')).toBe(true);
  });

  it.each(TERMINAL_LIVE_STATUSES)('excludes live terminal status "%s"', (status) => {
    expect(isHygieneEligible(status, 'MSN-TEST-0001')).toBe(false);
  });

  it.each(TERMINAL_DEFENSIVE_STATUSES)('excludes defensive terminal status "%s"', (status) => {
    expect(isHygieneEligible(status, 'MSN-TEST-0001')).toBe(false);
  });

  it('never lets a Closed or Archived mission through regardless of ID', () => {
    for (const status of TERMINAL_STATUSES) {
      expect(isHygieneEligible(status, 'MSN-ANYTHING')).toBe(false);
    }
  });
});

describe('isGeneratedJunkMissionId', () => {
  it.each([
    'force-20260610225359',
    'slack-20260611175431',
    'force-1',
    'slack-9999999999999',
  ])('flags generated ID "%s"', (id) => {
    expect(isGeneratedJunkMissionId(id)).toBe(true);
  });

  it.each([
    'MSN-0335',
    'M-20260613-CAPTAIN-VISIBILITY-UNLOCK',
    'USS-TJR-MSN-0061',
    'force-abc', // non-numeric suffix -- not the generator's format
    'forceful-123', // must not match on substring
  ])('does not flag real mission ID "%s"', (id) => {
    expect(isGeneratedJunkMissionId(id)).toBe(false);
  });

  it('excludes a force-/slack- mission even if its status is active (defense in depth)', () => {
    expect(isHygieneEligible('Idea', 'force-20260610225359')).toBe(false);
    expect(isHygieneEligible('Idea', 'slack-20260611175431')).toBe(false);
  });
});

describe('REVIEW_PENDING_STATUSES', () => {
  it('only covers real awaiting-review/approval states', () => {
    expect(REVIEW_PENDING_STATUSES.sort()).toEqual(
      ['Awaiting Number One Review', 'Awaiting Captain Approval', 'Awaiting XO Approval'].sort(),
    );
  });

  it('is a subset of the active statuses (never a terminal one)', () => {
    for (const status of REVIEW_PENDING_STATUSES) {
      expect(TERMINAL_STATUSES.includes(status)).toBe(false);
    }
  });
});

describe('dedupeMissionSignals', () => {
  it('collapses repeat mission_id hits to the most severe signal', () => {
    const result = dedupeMissionSignals([
      { mission_id: 'MSN-1', severity: 'medium' as const, id: 'stalled-MSN-1' },
      { mission_id: 'MSN-1', severity: 'high' as const, id: 'review-MSN-1' },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].severity).toBe('high');
  });

  it('keeps distinct missions separate', () => {
    const result = dedupeMissionSignals([
      { mission_id: 'MSN-1', severity: 'medium' as const, id: 'stalled-MSN-1' },
      { mission_id: 'MSN-2', severity: 'medium' as const, id: 'stalled-MSN-2' },
    ]);
    expect(result).toHaveLength(2);
  });

  it('passes through mission-less signals untouched, even several of them', () => {
    const result = dedupeMissionSignals([
      { severity: 'medium' as const, id: 'log-gap' },
      { severity: 'medium' as const, id: 'recovery-gap' },
    ]);
    expect(result).toHaveLength(2);
  });
});
