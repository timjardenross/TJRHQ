import { describe, expect, it } from 'vitest';
import { sanitiseWeeklyReview, type RawWeeklyReview } from '../weeklyReview';

const sig = (key: string, tone: 'warn' | 'crit' | 'ok', count: number, titles: string[] = []) => ({
  key, label: key, count, tone, items: titles.map((t, i) => ({ id: `${key}${i}`, title: t, href: '/x' })),
});
const raw: RawWeeklyReview = {
  summary: { weekStart: '2026-11-17', weekEnd: '2026-11-24', lastCompletedAt: '2026-11-17T00:00:00Z', reviewDebtDays: 7 },
  workbenches: [
    { key: 'chair', title: 'Today', signals: [sig('blocked', 'warn', 2, ['Mission blocked']), sig('unreviewed', 'warn', 3, ['Private capture title']), sig('notes', 'warn', 1, ['Notebook text'])] },
    { key: 'osint', title: 'Technical OSINT', signals: [sig('escalated', 'crit', 1, ['Escalated signal'])] },
    { key: 'human-systems', title: 'Human Systems', signals: [sig('overload', 'crit', 4, ['Personal capacity'])] },
    { key: 'ready-room', title: 'Ready Room', signals: [sig('important-open', 'warn', 5, ['Call the doctor'])] },
    { key: 'advisory', title: 'Advisory', signals: [sig('sessions', 'warn', 2, ['Should I take the job?'])] },
  ],
};

describe('weekly review for HQ is sanitised server-side', () => {
  const out = sanitiseWeeklyReview(raw);
  it('drops personal-health, personal-task and advisory sections entirely', () => {
    const text = JSON.stringify(out);
    for (const leak of ['Personal capacity', 'Call the doctor', 'Should I take the job?', 'Human Systems', 'Ready Room']) expect(text).not.toContain(leak);
  });
  it('drops capture and notebook signals from kept sections', () => {
    const text = JSON.stringify(out);
    expect(text).not.toContain('Private capture title');
    expect(text).not.toContain('Notebook text');
  });
  it('recomputes counts from what is kept, not from the whole review', () => {
    expect(out.looks).toBe(2); // only chair:blocked
    expect(out.urgent).toBe(1); // only osint:escalated
  });
  it('lists the most urgent items first and keeps the review-debt fields', () => {
    expect(out.items[0]).toMatchObject({ title: 'Escalated signal', tone: 'crit' });
    expect(out.reviewDebtDays).toBe(7);
    expect(out.lastCompletedAt).toBe('2026-11-17T00:00:00Z');
  });
  it('says what was left out', () => {
    expect(out.excluded.join(' ')).toMatch(/personal/i);
  });
  it('skips unavailable signals', () => {
    const r = sanitiseWeeklyReview({ workbenches: [{ key: 'osint', title: 'T', signals: [{ key: 'x', label: 'x', count: 9, tone: 'crit', unavailable: true }] }] });
    expect(r.urgent).toBe(0);
  });
});
