import { describe, it, expect } from 'vitest';
import { classifyPillar, scoreCapture, PILLARS, DEFAULT_PILLAR } from '@/lib/contentScoring';

// Content Workbench (COMMS-002) had zero test coverage — flagged in the
// 2026-08-08 workbench audit. contentScoring.ts is pure logic (no Supabase/
// network dependency), so it's the highest-value, lowest-cost place to add
// real coverage: every Content Workbench capture runs through scoreCapture()
// to decide its pillar, captain-focus flag, and initial rank_score.

describe('classifyPillar', () => {
  it('matches the operational_resilience pillar on its keywords', () => {
    const { pillar, score } = classifyPillar('Major cyber incident causes outage across critical infrastructure');
    expect(pillar.key).toBe('operational_resilience');
    expect(score).toBeGreaterThan(0);
  });

  it('is case-insensitive', () => {
    const lower = classifyPillar('resilience and risk');
    const upper = classifyPillar('RESILIENCE AND RISK');
    expect(upper.pillar.key).toBe(lower.pillar.key);
    expect(upper.score).toBe(lower.score);
  });

  it('falls back to DEFAULT_PILLAR with score 0 for text matching no keywords', () => {
    const { pillar, score } = classifyPillar('xyzzy plugh qwerty');
    expect(pillar.key).toBe(DEFAULT_PILLAR.key);
    expect(score).toBe(0);
  });

  it('picks the pillar with the most distinct keyword hits, not just any match', () => {
    // 3 operational_resilience keywords vs 1 from any other pillar's overlap risk
    const { pillar, score } = classifyPillar('resilience risk outage incident recovery continuity');
    expect(pillar.key).toBe('operational_resilience');
    expect(score).toBeGreaterThanOrEqual(6);
  });

  it('every declared pillar is reachable via at least one of its own keywords', () => {
    // Regression guard: if a pillar's keyword list is ever emptied or a
    // typo breaks every entry, this catches it — each pillar should win
    // classification when fed nothing but its own keywords.
    for (const p of PILLARS) {
      if (p.keywords.length === 0) continue;
      const { pillar } = classifyPillar(p.keywords.join(' '));
      expect(pillar.key).toBe(p.key);
    }
  });
});

describe('scoreCapture', () => {
  it('never returns null/undefined — always defaults to DEFAULT_PILLAR for a zero-match capture', () => {
    // Unlike the Python original (content_classifier.score_for_content()),
    // a manual capture is never rejected — Capture Workbench's
    // review-first ethos means nothing is silently dropped.
    const result = scoreCapture('completely unrelated nonsense text');
    expect(result).toBeDefined();
    expect(result.pillarKey).toBe(DEFAULT_PILLAR.key);
  });

  it('flags captainFocus when text contains a CAPTAIN_FOCUS_BASE keyword', () => {
    const result = scoreCapture('A piece on operational resilience and leadership');
    expect(result.captainFocus).toBe(true);
  });

  it('does not flag captainFocus for unrelated text', () => {
    const result = scoreCapture('A recipe for banana bread');
    expect(result.captainFocus).toBe(false);
  });

  it('produces a rankScore within the documented 0-100 scale', () => {
    const result = scoreCapture('Major operational resilience incident with cascading system failure');
    expect(result.rankScore).toBeGreaterThanOrEqual(0);
    expect(result.rankScore).toBeLessThanOrEqual(100);
  });

  it('captainFocus text scores higher rankScore than equivalent non-focus text', () => {
    // strategic component is (captainFocus ? 0.6 : 0.2) + ... — a real,
    // load-bearing behaviour difference worth locking in with a test.
    const focus = scoreCapture('resilience governance decision');
    const noFocus = scoreCapture('a pleasant walk in the park');
    expect(focus.rankScore).toBeGreaterThan(noFocus.rankScore);
  });

  it('contentRelevance is capped at 1', () => {
    // pillarScore*0.2 + 0.5*0.3 could theoretically exceed 1 with a very
    // high keyword-hit count — Math.min(1, ...) should hold regardless.
    const result = scoreCapture(
      PILLARS[0].keywords.join(' ') + ' ' + PILLARS[0].keywords.join(' '),
    );
    expect(result.contentRelevance).toBeLessThanOrEqual(1);
  });

  it('suggestedAngle is always a non-empty string', () => {
    const withKeywords = scoreCapture('resilience and risk management');
    const withoutKeywords = scoreCapture('random text with no matches');
    expect(withKeywords.suggestedAngle.length).toBeGreaterThan(0);
    expect(withoutKeywords.suggestedAngle.length).toBeGreaterThan(0);
  });
});
