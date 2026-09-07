import { describe, it, expect } from 'vitest';
import { buildReportPrompt, buildFallbackReport, parseReportResponse } from '../summary';
import type { TrendDayRow } from '../../trends/summary';

function row(overrides: Partial<TrendDayRow> & { log_date: string }): TrendDayRow {
  return {
    energy: null,
    nervous_system_state: null,
    capacity_state: null,
    stimulation_state: null,
    pain_state: null,
    pain_score: null,
    regulation_state: null,
    executive_function: null,
    compensation_load: null,
    emotional_state: null,
    social_state: null,
    ...overrides,
  };
}

// Dates relative to "today" so the 14-day cutoff in buildReportPrompt
// always includes them regardless of when the suite runs.
function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

describe('buildReportPrompt', () => {
  it('restricts the window to the last 14 calendar days', () => {
    const trends = [
      row({ log_date: daysAgo(20), capacity_state: 'red' }), // outside window
      row({ log_date: daysAgo(5), capacity_state: 'green' }),
      row({ log_date: daysAgo(1), capacity_state: 'orange' }),
    ];
    const { windowed, stats } = buildReportPrompt(trends);
    expect(windowed).toHaveLength(2);
    expect(stats.capacityCounts).toEqual({ green: 1, orange: 1, red: 0 });
  });

  it('includes a computed-statistics block ahead of the raw daily log', () => {
    const trends = [
      row({ log_date: daysAgo(3), capacity_state: 'green', pain_score: 2 }),
      row({ log_date: daysAgo(1), capacity_state: 'red', pain_score: 7 }),
    ];
    const { prompt } = buildReportPrompt(trends);
    const statsIndex = prompt.indexOf('Computed statistics');
    const rawIndex = prompt.indexOf('Raw daily log');
    expect(statsIndex).toBeGreaterThanOrEqual(0);
    expect(rawIndex).toBeGreaterThan(statsIndex);
    expect(prompt).toContain('green=1, orange=0, red=1');
  });
});

describe('parseReportResponse', () => {
  it('parses a well-formed JSON reply', () => {
    const raw = JSON.stringify({ highlights: ['a'], changes: ['b'], focus: ['c'] });
    expect(parseReportResponse(raw)).toEqual({ highlights: ['a'], changes: ['b'], focus: ['c'] });
  });

  it('tolerates a stray markdown code fence around the JSON', () => {
    const raw = '```json\n' + JSON.stringify({ highlights: [], changes: [], focus: [] }) + '\n```';
    expect(parseReportResponse(raw)).toEqual({ highlights: [], changes: [], focus: [] });
  });

  it('returns null for malformed JSON', () => {
    expect(parseReportResponse('not json at all')).toBeNull();
  });

  it('returns null when a field is missing or the wrong type', () => {
    expect(parseReportResponse(JSON.stringify({ highlights: ['a'], changes: ['b'] }))).toBeNull();
    expect(parseReportResponse(JSON.stringify({ highlights: 'a', changes: [], focus: [] }))).toBeNull();
  });
});

describe('buildFallbackReport', () => {
  it('reports no data plainly when nothing was recorded', () => {
    const { windowed: _windowed, stats } = buildReportPrompt([]);
    const report = buildFallbackReport(stats);
    expect(report.highlights).toEqual(['No check-ins recorded in this window yet.']);
    expect(report.changes).toEqual([]);
    expect(report.focus).toEqual([]);
  });

  it('summarizes capacity counts and pain stats directly from the stats block', () => {
    const trends = [
      row({ log_date: daysAgo(2), capacity_state: 'red', pain_score: 8 }),
      row({ log_date: daysAgo(1), capacity_state: 'green', pain_score: 2 }),
    ];
    const { stats } = buildReportPrompt(trends);
    const report = buildFallbackReport(stats);
    expect(report.highlights.some((h) => h.includes('1 sustainable day(s), 0 stretched, 1 depleted'))).toBe(true);
    expect(report.changes.some((c) => c.includes('peaking at 8/10'))).toBe(true);
  });

  it('names the same candidate drivers computeSummaryStats surfaced, and only those', () => {
    const trends = Array.from({ length: 6 }, (_, i) =>
      row({ log_date: daysAgo(i), regulation_state: i < 4 ? 'overloaded' : 'settled' })
    );
    const { stats } = buildReportPrompt(trends);
    const report = buildFallbackReport(stats);
    expect(report.focus.some((f) => f.startsWith('Regulation was in a concerning state'))).toBe(true);
  });
});
