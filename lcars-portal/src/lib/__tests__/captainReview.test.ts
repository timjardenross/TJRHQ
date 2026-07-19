import { describe, it, expect, vi, beforeEach } from 'vitest';

// MSN-0357: three real, evidence-derived investigation type definitions -
// Trend Scan, Noise Triage, Decision Traceback - grounded in
// docs/MSN-0353-INVESTIGATION-ARCHITECTURE.md §1.8-§1.10 and the real
// journeys in docs/MSN-0350-INVESTIGATION-JOURNEYS.md. Two of the cases
// below are direct regressions of real data confirmed live via Supabase MCP
// during this mission:
//   - journey #16: intelligence_events rows with banking_relevance='high'
//     but customer_impact='low' (e.g. "How Embodied Regulation Helps When
//     Words Fail", Iran/Ukraine geopolitics items) - 336 total HIGH-badge
//     rows, 324 of them uncorroborated by customer_impact.
//   - journey #19: architecture_records has exactly one live row,
//     ADR-20260608-140000 "Command Memory Data Store Selection"
//     (decision_summary: "...No embeddings or vector DB needed initially."),
//     which the static 26-title ADR Index snapshot (ADR-001..ADR-026) does
//     not contain any title matching "vector"/"database" for.

type TableRow = Record<string, unknown>;
const tableData: Record<string, { data: TableRow[] | null; error: unknown }> = {};

function setTable(table: string, data: TableRow[] | null, error: unknown = null) {
  tableData[table] = { data, error };
}

function makeChain(table: string) {
  const resolve = () => Promise.resolve(tableData[table] ?? { data: [], error: null });
  const chain: {
    select: () => typeof chain;
    eq: () => typeof chain;
    order: () => typeof chain;
    limit: () => typeof chain;
    then: (
      onFulfilled?: (v: { data: TableRow[] | null; error: unknown }) => unknown,
      onRejected?: (e: unknown) => unknown
    ) => Promise<unknown>;
  } = {
    select: () => chain,
    eq: () => chain,
    order: () => chain,
    limit: () => chain,
    then: (onFulfilled, onRejected) => resolve().then(onFulfilled, onRejected),
  };
  return chain;
}

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: (table: string) => makeChain(table),
  },
}));

import { openInvestigation, resolveInvestigation } from '@/lib/investigationEngine';
import {
  trendScan,
  noiseTriage,
  decisionTraceback,
  extractSearchTerms,
  type TrendScanDecision,
  type NoiseTriageDecision,
  type DecisionTracebackDecision,
} from '@/lib/investigations/captainReview';

function trigger(reason: string, originRef?: string) {
  return {
    investigationType: 'test',
    reason,
    originatedAt: '2026-07-09T00:00:00.000Z',
    originRef,
  };
}

beforeEach(() => {
  setTable('intelligence_briefs', []);
  setTable('intelligence_events', []);
  setTable('architecture_records', []);
  setTable('commander_decisions', []);
  setTable('decide_ledger', []);
});

// ─── Trend Scan ─────────────────────────────────────────────────────────

describe('trendScan', () => {
  it('declares all nine metadata fields with real, specific values', () => {
    expect(trendScan.type).toBe('trend-scan');
    expect(trendScan.owner).toBe('captain');
    expect(trendScan.requiredEvidence.length).toBeGreaterThan(0);
    expect(trendScan.evidenceSources).toContain('lcars-portal Supabase: intelligence_briefs (generated_at, period_start, period_end, overall_risk, bottom_line)');
    expect(trendScan.validationRules.length).toBeGreaterThan(0);
    expect(trendScan.possibleDecisionKinds).toEqual(['continue-as-is', 'note-trend-in-log', 'escalate-trend']);
    expect(trendScan.completionCriteria.length).toBeGreaterThan(0);
    expect(trendScan.auditOutputs.length).toBeGreaterThan(0);
  });

  it('has no execute/verify - read-only judgment per MSN-0353 §1.8', () => {
    expect(trendScan.execute).toBeUndefined();
    expect(trendScan.verify).toBeUndefined();
  });

  it('blocks at evidence_validation when fewer than 2 briefs exist', async () => {
    setTable('intelligence_briefs', [{ brief_id: '1', generated_at: '2026-07-01T00:00:00Z', period_start: null, period_end: null, overall_risk: 'GREEN', bottom_line: null }]);
    const state = await openInvestigation(trendScan, trigger('weekly ORI risk-trend read'));
    expect(state.validation?.ok).toBe(false);
    expect(state.decisionOptions).toBeUndefined();
  });

  it('journey #18 shape: reads a real 5-brief RED→AMBER→AMBER→GREEN→GREEN window as improving and offers note-trend-in-log', async () => {
    // Rows returned newest-first (as the real query orders them); the
    // definition reverses to chronological order internally.
    setTable('intelligence_briefs', [
      { brief_id: '5', generated_at: '2026-06-28T00:00:00Z', period_start: '2026-06-14', period_end: '2026-06-28', overall_risk: 'GREEN', bottom_line: 'Settled.' },
      { brief_id: '4', generated_at: '2026-06-20T00:00:00Z', period_start: '2026-06-06', period_end: '2026-06-20', overall_risk: 'GREEN', bottom_line: 'Calm.' },
      { brief_id: '3', generated_at: '2026-06-13T00:00:00Z', period_start: '2026-05-30', period_end: '2026-06-13', overall_risk: 'AMBER', bottom_line: 'Watching a cluster of outages.' },
      { brief_id: '2', generated_at: '2026-06-06T00:00:00Z', period_start: '2026-05-23', period_end: '2026-06-06', overall_risk: 'AMBER', bottom_line: 'Elevated concern.' },
      { brief_id: '1', generated_at: '2026-05-30T00:00:00Z', period_start: '2026-05-16', period_end: '2026-05-30', overall_risk: 'RED', bottom_line: 'Critical alert.' },
    ]);
    const opened = await openInvestigation(trendScan, trigger('weekly ORI risk-trend scan'));
    expect(opened.validation?.ok).toBe(true);
    expect(opened.evidence?.window.map((p) => p.overall_risk)).toEqual(['RED', 'AMBER', 'AMBER', 'GREEN', 'GREEN']);
    expect(opened.evidence?.direction).toBe('improving');
    expect(opened.evidence?.elevatedPoints).toHaveLength(3);
    const ids = opened.decisionOptions?.map((o) => o.id);
    expect(ids).toContain('continue-as-is');
    expect(ids).toContain('note-trend-in-log');
    expect(ids).not.toContain('escalate-trend');

    const resolved = await resolveInvestigation(opened, 'note-trend-in-log' as TrendScanDecision);
    expect(resolved.execution).toEqual({ attempted: false, success: null, detail: 'this investigation type has no execution stage — the decision itself is the outcome' });
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.learning?.category).toBe('precedent');
    expect(resolved.learning?.insight).toMatch(/RED→AMBER→AMBER→GREEN→GREEN/);
  });

  it('offers escalate-trend when the trend is genuinely worsening across the window', async () => {
    setTable('intelligence_briefs', [
      { brief_id: '5', generated_at: '2026-07-08T00:00:00Z', period_start: null, period_end: null, overall_risk: 'RED', bottom_line: 'Still elevated.' },
      { brief_id: '4', generated_at: '2026-07-01T00:00:00Z', period_start: null, period_end: null, overall_risk: 'AMBER', bottom_line: null },
      { brief_id: '3', generated_at: '2026-06-24T00:00:00Z', period_start: null, period_end: null, overall_risk: 'GREEN', bottom_line: null },
    ]);
    const opened = await openInvestigation(trendScan, trigger('checking the risk trend before the week closes'));
    expect(opened.evidence?.direction).toBe('worsening');
    const ids = opened.decisionOptions?.map((o) => o.id);
    expect(ids).toContain('escalate-trend');

    const resolved = await resolveInvestigation(opened, 'escalate-trend' as TrendScanDecision);
    expect(resolved.learning?.category).toBe('precedent');
    expect(resolved.learning?.insight).toMatch(/still elevated at the most recent point/);
  });

  it('reachedEndOfData is honest - a window smaller than requested completes without a decision', async () => {
    setTable('intelligence_briefs', [
      { brief_id: '2', generated_at: '2026-07-01T00:00:00Z', period_start: null, period_end: null, overall_risk: 'GREEN', bottom_line: null },
      { brief_id: '1', generated_at: '2026-06-24T00:00:00Z', period_start: null, period_end: null, overall_risk: 'GREEN', bottom_line: null },
    ]);
    const opened = await openInvestigation(trendScan, trigger('quick trend check'));
    const resolved = await resolveInvestigation(opened, undefined);
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.completion?.reason).toMatch(/reached the edge of what exists/);
  });

  it('blocks cleanly on a genuine query failure rather than reading it as "nothing elevated"', async () => {
    setTable('intelligence_briefs', null, { message: 'network error' });
    const state = await openInvestigation(trendScan, trigger('weekly scan'));
    expect(state.validation?.ok).toBe(false);
    expect(state.validation?.problems[0]).toMatch(/query failed/);
  });
});

// ─── Noise Triage ───────────────────────────────────────────────────────

describe('noiseTriage', () => {
  it('declares all nine metadata fields with real, specific values', () => {
    expect(noiseTriage.type).toBe('noise-triage');
    expect(noiseTriage.owner).toBe('captain');
    expect(noiseTriage.triggerDescription).toMatch(/Integrity Audit/);
    expect(noiseTriage.evidenceSources.some((s) => s.includes('intelligenceRisk.ts'))).toBe(true);
    expect(noiseTriage.possibleDecisionKinds).toEqual(['discount-as-noise', 'recurring-pattern-file-integrity-audit']);
  });

  it('has no execute/verify - the classifier fix is out-of-band engineering work', () => {
    expect(noiseTriage.execute).toBeUndefined();
    expect(noiseTriage.verify).toBeUndefined();
  });

  // Regression: journey #16's real classifier pattern, confirmed live via
  // Supabase MCP - banking_relevance='high' driving a HIGH badge on content
  // with no real banking relevance (wellbeing article, geopolitics items).
  it('journey #16 regression: flags the real banking_relevance-only false-positive pattern via the shared deriveRisk()', async () => {
    setTable('intelligence_events', [
      { event_id: 'a', raw_title: 'How Embodied Regulation Helps When Words Fail', banking_relevance: 'high', customer_impact: 'low', collected_at: '2026-07-08T20:00:12Z' },
      { event_id: 'b', raw_title: "Trump grants Ukraine licence to produce Patriot missiles", banking_relevance: 'high', customer_impact: 'low', collected_at: '2026-07-08T20:00:11Z' },
      { event_id: 'c', raw_title: 'US launches new wave of Iran strikes after attacks on tankers', banking_relevance: 'high', customer_impact: 'low', collected_at: '2026-07-08T03:51:51Z' },
      // A genuine HIGH item, corroborated by customer_impact - must NOT be flagged.
      { event_id: 'd', raw_title: 'Major outage affecting core banking rails', banking_relevance: 'high', customer_impact: 'high', collected_at: '2026-07-08T03:00:00Z' },
    ]);
    const opened = await openInvestigation(noiseTriage, trigger('scanning today\'s HIGH-badged signals for noise'));
    expect(opened.validation?.ok).toBe(true);
    expect(opened.evidence?.scanned).toBe(4);
    expect(opened.evidence?.flagged.map((f) => f.event_id)).toEqual(['a', 'b', 'c']);
    expect(opened.evidence?.recurrenceCount).toBe(3);
    expect(opened.evidence?.patternConfirmed).toBe(true);
    const ids = opened.decisionOptions?.map((o) => o.id);
    expect(ids).toEqual(['discount-as-noise', 'recurring-pattern-file-integrity-audit']);

    const resolved = await resolveInvestigation(opened, 'recurring-pattern-file-integrity-audit' as NoiseTriageDecision);
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.learning?.category).toBe('classifier-defect');
    expect(resolved.learning?.insight).toMatch(/Embodied Regulation/);
    expect(resolved.learning?.insight).toMatch(/Integrity Audit/);
  });

  it('does not offer recurring-pattern when fewer than 3 flagged items are found', async () => {
    setTable('intelligence_events', [
      { event_id: 'a', raw_title: 'Payments Summit', banking_relevance: 'high', customer_impact: 'low', collected_at: '2026-07-08T20:00:12Z' },
    ]);
    const opened = await openInvestigation(noiseTriage, trigger('quick noise check'));
    expect(opened.evidence?.patternConfirmed).toBe(false);
    const ids = opened.decisionOptions?.map((o) => o.id);
    expect(ids).toEqual(['discount-as-noise']);

    const resolved = await resolveInvestigation(opened, 'discount-as-noise' as NoiseTriageDecision);
    expect(resolved.learning?.category).toBe('none');
  });

  it('never flags a real HIGH item corroborated by customer_impact', async () => {
    setTable('intelligence_events', [
      { event_id: 'x', raw_title: 'Core banking outage', banking_relevance: 'high', customer_impact: 'high', collected_at: '2026-07-08T00:00:00Z' },
    ]);
    const opened = await openInvestigation(noiseTriage, trigger('noise check'));
    expect(opened.evidence?.flagged).toHaveLength(0);
  });

  it('blocks cleanly on a genuine query failure', async () => {
    setTable('intelligence_events', null, { message: 'down' });
    const state = await openInvestigation(noiseTriage, trigger('noise check'));
    expect(state.validation?.ok).toBe(false);
  });
});

// ─── Decision Traceback ─────────────────────────────────────────────────

describe('extractSearchTerms', () => {
  it('pulls concrete terms out of prose and drops stopwords', () => {
    const terms = extractSearchTerms('checking whether a vector-database decision already existed before repeating the debate');
    expect(terms).toContain('vector-database');
    expect(terms).not.toContain('whether');
    expect(terms).not.toContain('already');
  });
});

describe('decisionTraceback', () => {
  it('declares all nine metadata fields with real, specific values', () => {
    expect(decisionTraceback.type).toBe('decision-traceback');
    expect(decisionTraceback.owner).toBe('shared');
    expect(decisionTraceback.evidenceSources.some((s) => s.includes('architecture_records'))).toBe(true);
    expect(decisionTraceback.possibleDecisionKinds).toEqual(['proceed-precedent-stands', 'reopen-stale-precedent', 'no-precedent-found']);
  });

  it('has no execute/verify - proceeding or reopening is itself the outcome', () => {
    expect(decisionTraceback.execute).toBeUndefined();
    expect(decisionTraceback.verify).toBeUndefined();
  });

  it('blocks at evidence_validation when trigger.reason yields no usable search terms', async () => {
    const state = await openInvestigation(decisionTraceback, trigger('hmm'));
    expect(state.validation?.ok).toBe(false);
  });

  // Regression: journey #19's real shape, confirmed live via Supabase MCP -
  // architecture_records has exactly one row (ADR-20260608-140000, "Command
  // Memory Data Store Selection", decision_summary mentioning "No
  // embeddings or vector DB needed initially"), which the static ADR Index
  // snapshot has no matching title for.
  it('journey #19 regression: finds the real architecture_records answer and flags the static ADR Index as a false negative for the same query', async () => {
    setTable('architecture_records', [
      {
        id: 'ADR-20260608-140000',
        title: 'Command Memory Data Store Selection',
        decision_summary: 'Use Supabase only. SQL + text search sufficient. No embeddings or vector DB needed initially.',
        problem_statement: 'Should command memory use a dedicated vector database?',
        status: 'Active',
        decision_date: '2026-06-08T14:00:00Z',
      },
    ]);
    const opened = await openInvestigation(
      decisionTraceback,
      trigger('checking whether a vector database decision already existed before repeating the debate')
    );
    expect(opened.validation?.ok).toBe(true);
    expect(opened.evidence?.primaryMatch?.source).toBe('architecture_records');
    expect(opened.evidence?.primaryMatch?.id).toBe('ADR-20260608-140000');
    expect(opened.evidence?.primaryMatch?.status).toBe('Active');
    // The static index's real titles (ADR-001..ADR-026, none about vector
    // databases or command memory storage) do not contain "vector" or
    // "database" - this is a genuine false negative, exactly journey #19.
    expect(opened.evidence?.staticAdrIndexWouldHaveMissed).toBe(true);
    // commander_decisions / decide_ledger were never queried - the match
    // was found on the first, most-authoritative source.
    expect(opened.evidence?.sourcesSearched).toEqual(['architecture_records']);

    const resolved = await resolveInvestigation(opened, 'proceed-precedent-stands' as DecisionTracebackDecision);
    expect(resolved.completion?.complete).toBe(true);
    // The coverage-gap finding (static index drift) takes priority in the
    // learning output over the plain "reused a precedent" note - it's the
    // structurally important one.
    expect(resolved.learning?.category).toBe('coverage-gap');
    expect(resolved.learning?.insight).toMatch(/false negative/);
  });

  it('falls through to commander_decisions when architecture_records has no match', async () => {
    setTable('architecture_records', []);
    setTable('commander_decisions', [
      {
        id: 'cd-1',
        decision_title: 'API-first architecture for all Telegram lifecycle operations',
        decision_summary: 'All mission lifecycle actions route through the LCARS portal API.',
        status: 'confirmed',
        created_at: '2026-06-27T07:23:05Z',
      },
    ]);
    const opened = await openInvestigation(decisionTraceback, trigger('checking whether the telegram lifecycle architecture decision already exists'));
    expect(opened.evidence?.primaryMatch?.source).toBe('commander_decisions');
    expect(opened.evidence?.sourcesSearched).toEqual(['architecture_records', 'commander_decisions']);
  });

  it('falls through to decide_ledger when neither architecture_records nor commander_decisions match', async () => {
    setTable('architecture_records', []);
    setTable('commander_decisions', []);
    setTable('decide_ledger', [
      { id: 'dl-1', question: 'Should we archive the duplicate dead-code audit request?', action: 'archive', outcome: 'archived', decided_at: '2026-06-01T00:00:00Z' },
    ]);
    const opened = await openInvestigation(decisionTraceback, trigger('checking whether the duplicate dead-code audit question was already decided'));
    expect(opened.evidence?.primaryMatch?.source).toBe('decide_ledger');
    expect(opened.evidence?.sourcesSearched).toEqual(['architecture_records', 'commander_decisions', 'decide_ledger']);
  });

  it('returns no-precedent-found as the only option when nothing matches any of the three sources', async () => {
    const opened = await openInvestigation(decisionTraceback, trigger('checking whether a quantum encryption rollout decision already exists'));
    expect(opened.evidence?.primaryMatch).toBeNull();
    expect(opened.decisionOptions?.map((o) => o.id)).toEqual(['no-precedent-found']);

    const resolved = await resolveInvestigation(opened, 'no-precedent-found' as DecisionTracebackDecision);
    expect(resolved.completion?.complete).toBe(true);
    expect(resolved.learning?.category).toBe('none');
  });

  it('reopen-stale-precedent produces a process-gap learning insight', async () => {
    // Matched via commander_decisions (not architecture_records), so this
    // isolates the reopen-stale path from the architecture_records-specific
    // coverage-gap check (journey #19) exercised above.
    setTable('architecture_records', []);
    setTable('commander_decisions', [
      {
        id: 'cd-old',
        decision_title: 'Legacy caching approach',
        decision_summary: 'Use in-memory caching only.',
        status: 'Superseded',
        created_at: '2025-01-01T00:00:00Z',
      },
    ]);
    const opened = await openInvestigation(decisionTraceback, trigger('checking the legacy caching decision before proposing a new one'));
    expect(opened.evidence?.primaryMatch?.source).toBe('commander_decisions');
    expect(opened.evidence?.primaryMatch?.id).toBe('cd-old');
    const resolved = await resolveInvestigation(opened, 'reopen-stale-precedent' as DecisionTracebackDecision);
    expect(resolved.learning?.category).toBe('process-gap');
  });

  it('blocks cleanly on a genuine query failure against any searched source', async () => {
    setTable('architecture_records', null, { message: 'down' });
    const state = await openInvestigation(decisionTraceback, trigger('checking whether a vector database decision already exists'));
    expect(state.validation?.ok).toBe(false);
  });
});
