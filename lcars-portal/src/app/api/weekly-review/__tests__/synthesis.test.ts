import { describe, it, expect } from 'vitest';
import { buildSynthesis } from '../synthesis';
import type { Signal, WorkbenchSection } from '@/lib/weeklyReview';

// Human Execution Loop mission — Weekly Review must (brief §29) distinguish
// "still open" from "deserves carry-forward attention," must never invent a
// causal claim from a correlation (brief §27/§58), and must never silently
// mutate or discard evidence about what actually happened (brief §21/§50).

function sig(key: string, count: number, tone: Signal['tone'], items: Signal['items'] = []): Signal {
  return { key, label: key, count, tone, items, unavailable: false };
}

function readyRoomSection(overrides: Partial<Record<string, Signal>> = {}): WorkbenchSection {
  return {
    key: 'ready-room', title: 'Ready Room', href: '/ready-room',
    signals: [
      overrides.completed ?? sig('completed', 0, 'ok'),
      overrides['important-open'] ?? sig('important-open', 0, 'warn'),
      overrides['newly-waiting'] ?? sig('newly-waiting', 0, 'neutral'),
      overrides.parked ?? sig('parked', 0, 'neutral'),
    ],
  };
}

function baseSections(readyRoom: WorkbenchSection): WorkbenchSection[] {
  return [
    { key: 'chair', title: "Captain's Chair", href: '/captains-chair-workbench', signals: [sig('decisions', 0, 'warn')] },
    { key: 'osint', title: 'Technical OSINT', href: '/intelligence-workbench', signals: [sig('high-confidence', 0, 'ok'), sig('escalated', 0, 'crit'), sig('uncorroborated', 0, 'warn')] },
    { key: 'health-osint', title: 'Health OSINT', href: '/health-osint', signals: [sig('published', 0, 'neutral'), sig('flagged', 0, 'crit'), sig('appraisal', 0, 'warn')] },
    { key: 'content', title: 'Content Workbench', href: '/content-workbench', signals: [sig('blocked', 0, 'crit'), sig('ready', 0, 'warn')] },
    { key: 'human-systems', title: 'Human Systems', href: '/human-systems-workbench', signals: [] },
    readyRoom,
    { key: 'advisory', title: 'Advisory', href: '/advisory-workbench', signals: [] },
    { key: 'briefs', title: 'Briefs', href: '/briefs', signals: [] },
    { key: 'agent-status', title: 'HQ Status', href: '/agent-status-workbench', signals: [sig('stale', 0, 'warn'), sig('never', 0, 'crit'), sig('repeated', 0, 'crit')] },
  ];
}

describe('Weekly Review synthesis — carry-forward is an attention decision, not "all open" (brief §29)', () => {
  it('surfaces important-open Ready Room items as carry-forward, but never parked or waiting items', () => {
    const readyRoom = readyRoomSection({
      'important-open': sig('important-open', 1, 'warn', [{ id: 't1', title: 'Crisis-plan feedback' }]),
      parked: sig('parked', 3, 'neutral', [{ id: 'p1', title: 'Low priority A' }]),
      'newly-waiting': sig('newly-waiting', 2, 'neutral', [{ id: 'w1', title: 'Waiting on accountant' }]),
    });
    const synthesis = buildSynthesis(baseSections(readyRoom), null, 'steady', 'Steady.', true);
    const carryForwardTitles = synthesis.carryForward.map((c) => c.detail);
    expect(carryForwardTitles.some((d) => d.includes('Crisis-plan feedback'))).toBe(true);
    expect(carryForwardTitles.some((d) => d.includes('Low priority A'))).toBe(false);
    expect(carryForwardTitles.some((d) => d.includes('Waiting on accountant'))).toBe(false);
  });

  it('parked items appear in You Can Ignore, not carry-forward, and only when evidence supports it (brief §31)', () => {
    const readyRoom = readyRoomSection({ parked: sig('parked', 4, 'neutral') });
    const synthesis = buildSynthesis(baseSections(readyRoom), null, 'steady', 'Steady.', true);
    expect(synthesis.youCanIgnore.some((l) => l.includes('4') && l.toLowerCase().includes('parked'))).toBe(true);
    expect(synthesis.carryForward.some((c) => c.title === 'Ready Room' && c.detail.includes('parked'))).toBe(false);
  });

  it('completed items (tone ok) never appear in What Mattered — routine completion is not treated as a headline event', () => {
    const readyRoom = readyRoomSection({ completed: sig('completed', 5, 'ok', [{ id: 'c1', title: 'Did a thing' }]) });
    const synthesis = buildSynthesis(baseSections(readyRoom), null, 'steady', 'Steady.', true);
    expect(synthesis.whatMattered.some((m) => m.title.includes('Ready Room'))).toBe(false);
  });
});

describe('Weekly Review synthesis — cautious, non-causal learning (brief §27/§58)', () => {
  it('notes completions during a constrained posture descriptively, without claiming causation', () => {
    const readyRoom = readyRoomSection({ completed: sig('completed', 2, 'ok') });
    const synthesis = buildSynthesis(baseSections(readyRoom), null, 'protect', 'Capacity is stretched.', true);
    const item = synthesis.learned.find((l) => l.key === 'ready-room-progress-during-constraint');
    expect(item).toBeDefined();
    expect(item!.lesson.toLowerCase()).not.toMatch(/\bcaused\b|\bbecause of\b/);
  });

  it('does not fabricate the same learning item on a non-restrictive week even with completions', () => {
    const readyRoom = readyRoomSection({ completed: sig('completed', 2, 'ok') });
    const synthesis = buildSynthesis(baseSections(readyRoom), null, 'engage', 'Capacity is available.', true);
    expect(synthesis.learned.find((l) => l.key === 'ready-room-progress-during-constraint')).toBeUndefined();
  });
});

describe('Weekly Review synthesis — Week in Review reflects real execution evidence', () => {
  it('reports completed and important-open counts in the Execution line', () => {
    const readyRoom = readyRoomSection({
      completed: sig('completed', 2, 'ok'),
      'important-open': sig('important-open', 1, 'warn'),
    });
    const synthesis = buildSynthesis(baseSections(readyRoom), null, 'steady', 'Steady.', true);
    const execLine = synthesis.weekInReview.lines.find((l) => l.key === 'execution');
    expect(execLine).toBeDefined();
    expect(execLine!.detail).toContain('2 completed');
    expect(execLine!.detail).toContain('1 important still open');
  });
});
