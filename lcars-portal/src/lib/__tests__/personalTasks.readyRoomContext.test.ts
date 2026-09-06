import { describe, it, expect } from 'vitest';
import {
  rankToday,
  capacityLimitForPosture,
  buildStatusSentence,
  type PersonalTask,
} from '../personalTasks';

// Human Execution Loop mission — Ready Room's side of the Human Systems
// boundary: capacity context may shrink the algorithm-ranked cap (brief
// §44/§55 "PROTECT can reduce recommended attention load"), but it must
// never remove a task the Captain explicitly pinned (brief §13/§45/§56),
// never expose the whole backlog even on a strong day (brief §45/§55), and
// never break when there's no check-in at all (brief §43/§55).

function task(overrides: Partial<PersonalTask> = {}): PersonalTask {
  return {
    id: overrides.id ?? Math.random().toString(36).slice(2),
    title: 'Task',
    context: null,
    category: 'task',
    urgency: 2,
    importance: 2,
    effort_minutes: 30,
    work_state: 'captured',
    due_date: null,
    waiting_on: null,
    micro_action: null,
    mvp_note: null,
    stop_point: null,
    restart_cue: null,
    source_capture_id: null,
    created_at: new Date('2026-01-01').toISOString(),
    started_at: null,
    completed_at: null,
    updated_at: new Date('2026-01-01').toISOString(),
    follow_through_mode: 'normal',
    next_review_at: null,
    snoozed_until: null,
    nudge_count: 0,
    deferral_count: 0,
    blocker_category: null,
    follow_through_paused: false,
    pinned_today: false,
    ...overrides,
  };
}

describe('capacityLimitForPosture — informs the cap, never vetoes (brief §7/§44/§45)', () => {
  it('shrinks the cap under PROTECT/RESET/RECOVER without reaching zero', () => {
    expect(capacityLimitForPosture('RECOVER')).toBeGreaterThan(0);
    expect(capacityLimitForPosture('PROTECT')).toBeGreaterThan(0);
    expect(capacityLimitForPosture('RESET')).toBeGreaterThan(0);
    expect(capacityLimitForPosture('RECOVER')).toBeLessThan(capacityLimitForPosture('STEADY'));
  });

  it('does not unbound the cap on a strong day (brief §45 — no backlog dump)', () => {
    expect(capacityLimitForPosture('ENGAGE')).toBeLessThanOrEqual(3);
  });

  it('defaults to the steady cap on UNKNOWN (no/stale check-in, brief §43)', () => {
    expect(capacityLimitForPosture('UNKNOWN')).toBe(capacityLimitForPosture('STEADY'));
  });
});

describe('rankToday — pinned tasks always survive a shrinking cap (brief §13/§56)', () => {
  it('keeps a pinned task in Today even when capacityLimit is 1 and ranking would not have picked it', () => {
    const pinned = task({ id: 'pinned', pinned_today: true, urgency: 1, created_at: new Date('2026-01-05').toISOString() });
    const urgent = task({ id: 'urgent', urgency: 5 });
    const result = rankToday([urgent, pinned], { capacityLimit: 1 });
    expect(result.map((t) => t.id)).toContain('pinned');
  });

  it('fills remaining capacity slots with ranked tasks after pinned ones', () => {
    const pinned = task({ id: 'pinned', pinned_today: true });
    const a = task({ id: 'a', urgency: 5 });
    const b = task({ id: 'b', urgency: 5, created_at: new Date('2026-01-02').toISOString() });
    const result = rankToday([pinned, a, b], { capacityLimit: 2 });
    expect(result.map((t) => t.id)).toEqual(['pinned', 'a']);
  });

  it('never exceeds a strong-day cap just because many tasks exist (brief §45)', () => {
    const many = Array.from({ length: 20 }, (_, i) => task({ id: `t${i}`, urgency: 5 }));
    const result = rankToday(many, { capacityLimit: capacityLimitForPosture('ENGAGE') });
    expect(result.length).toBeLessThanOrEqual(3);
  });
});

describe('buildStatusSentence — no-checkin degrades gracefully, never reads as constrained (brief §42/§43)', () => {
  it('adds an honest note when there is no fresh check-in, without implying low capacity', () => {
    const sentence = buildStatusSentence({ todayCount: 2, waitingCount: 0, capacityLow: false, hasCheckinToday: false });
    expect(sentence).toMatch(/no recent capacity check-in/i);
    expect(sentence).not.toMatch(/limited/i);
  });

  it('stays silent about check-in freshness once one exists today', () => {
    const sentence = buildStatusSentence({ todayCount: 2, waitingCount: 0, capacityLow: false, hasCheckinToday: true });
    expect(sentence).not.toMatch(/check-in/i);
  });
});
