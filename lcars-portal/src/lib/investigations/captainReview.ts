/**
 * MSN-0357 — Investigation type definitions: Trend Scan, Noise Triage, and
 * Decision Traceback — the three Captain-facing (or shared) investigation
 * types identified in MSN-0353 §1.8-§1.10, grounded in the real journeys
 * MSN-0350 reconstructed (docs/MSN-0350-INVESTIGATION-JOURNEYS.md #12, #16,
 * #18, #19, #20, #21).
 *
 * All three read real, live Supabase tables directly — `intelligence_briefs`
 * (Trend Scan), `intelligence_events` (Noise Triage, via the shared
 * `deriveRisk` classifier already fixed by MSN-0351), and
 * `architecture_records` / `commander_decisions` / `decide_ledger`
 * (Decision Traceback). None of the three reimplement risk derivation —
 * Noise Triage imports `deriveRisk` from `lib/intelligenceRisk.ts` directly,
 * the same single source of truth the Intelligence page's badge and its
 * server-side filter already share.
 */

import type { InvestigationDefinition, TriggerContext } from '@/lib/investigationEngine';
import { supabase } from '@/lib/supabase';
import { deriveRisk, type RiskLevel } from '@/lib/intelligenceRisk';

// ─── Shared fetch helper ────────────────────────────────────────────────
// Every definition below distinguishes a genuine query failure (network
// error, malformed query) from a successful-but-empty result — the same
// honest-omission discipline ros-data.ts/human-systems.ts already apply to
// health data (MSN-0355). A failed fetch surfaces as `queryFailed: true` in
// the assembled evidence and blocks cleanly at evidence_validation, rather
// than being silently indistinguishable from "genuinely nothing found."

interface FetchResult<T> {
  rows: T[];
  failed: boolean;
}

async function fetchRows<T>(
  run: () => PromiseLike<{ data: T[] | null; error: unknown }>
): Promise<FetchResult<T>> {
  if (!supabase) return { rows: [], failed: false };
  try {
    const { data, error } = await run();
    if (error) return { rows: [], failed: true };
    return { rows: (data ?? []) as T[], failed: false };
  } catch {
    return { rows: [], failed: true };
  }
}

// ─── 1. Trend Scan ──────────────────────────────────────────────────────
// MSN-0353 §1.8. Trigger: a periodic habit - end-of-week, or noticing a
// personal pattern - not a single alert. Journey #18's real shape: a
// five-brief weekly ORI risk-trend read, RED→AMBER→AMBER→GREEN→GREEN across
// four weeks, correctly read as genuine de-escalation once the two elevated
// briefs' bottom_line was checked. This reads the real, live
// `intelligence_briefs` table - the exact same table and fields journey #18
// cites - in chronological order (oldest → newest), because a trend is read
// as a sequence, never as "most recent first."
//
// Owner: captain. This is inherently personal/operational judgment (MSN-0353
// §1.8) - not something staff performs on the Captain's behalf.

const TREND_WINDOW_SIZE = 5;

export interface TrendScanPoint {
  brief_id: string;
  generated_at: string;
  period_start: string | null;
  period_end: string | null;
  overall_risk: string;
  bottom_line: string | null;
}

export type TrendDirection = 'worsening' | 'improving' | 'stable' | 'insufficient';

export interface TrendScanEvidence {
  /** Chronological order, oldest first — a sequence, not a single alert. */
  window: TrendScanPoint[];
  windowRequested: number;
  /** True when fewer real briefs exist than the window asked for - the honest completion signal per MSN-0353 §1.8 ("reached the edge of what exists"), not "scanned everything available." */
  reachedEndOfData: boolean;
  queryFailed: boolean;
  /** Points at AMBER or RED - the ones whose reasoning text actually matters, per journey #18 ("plus the reasoning text attached to the one or two points that were elevated - never the full underlying record set"). */
  elevatedPoints: TrendScanPoint[];
  direction: TrendDirection;
}

/** RED/AMBER/GREEN/UNKNOWN is the real field shape already used by
 * lib/interruptAssembly.ts's intelligenceBriefNominator. UNKNOWN or any
 * unrecognised value is excluded from the severity trend, never fabricated
 * into a number. */
function riskSeverity(level: string | null | undefined): number | null {
  const l = (level ?? '').toUpperCase();
  if (l === 'GREEN') return 0;
  if (l === 'AMBER') return 1;
  if (l === 'RED') return 2;
  return null;
}

function trendDirection(window: TrendScanPoint[]): TrendDirection {
  const severities = window.map((p) => riskSeverity(p.overall_risk)).filter((s): s is number => s !== null);
  if (severities.length < 2) return 'insufficient';
  const first = severities[0];
  const last = severities[severities.length - 1];
  if (last > first) return 'worsening';
  if (last < first) return 'improving';
  return 'stable';
}

async function assembleTrendScanEvidence(): Promise<TrendScanEvidence> {
  const { rows, failed } = await fetchRows<TrendScanPoint>(() =>
    supabase!
      .from('intelligence_briefs')
      .select('brief_id, generated_at, period_start, period_end, overall_risk, bottom_line')
      .order('generated_at', { ascending: false })
      .limit(TREND_WINDOW_SIZE)
  );
  const window = [...rows].reverse();
  const elevatedPoints = window.filter((p) => (riskSeverity(p.overall_risk) ?? 0) >= 1);
  return {
    window,
    windowRequested: TREND_WINDOW_SIZE,
    reachedEndOfData: rows.length < TREND_WINDOW_SIZE,
    queryFailed: failed,
    elevatedPoints,
    direction: trendDirection(window),
  };
}

export type TrendScanDecision = 'continue-as-is' | 'note-trend-in-log' | 'escalate-trend';

export const trendScan: InvestigationDefinition<TrendScanEvidence, TrendScanDecision> = {
  type: 'trend-scan',
  label: 'Trend Scan',
  owner: 'captain',
  triggerDescription:
    'A periodic habit - end-of-week, or noticing a personal pattern - not a single alert. (MSN-0353 §1.8; journey #12 - the two-day Bali pain-spike arc; journey #18 - the real five-brief weekly ORI risk-trend read, RED→AMBER→AMBER→GREEN→GREEN.)',
  requiredEvidence: [
    'the last 5 intelligence_briefs rows (generated_at, period_start, period_end, overall_risk, bottom_line), read in chronological order - a sequence, not a single alert',
    'which points in that window are elevated (AMBER/RED) - the only ones whose bottom_line reasoning actually matters',
  ],
  evidenceSources: ['lcars-portal Supabase: intelligence_briefs (generated_at, period_start, period_end, overall_risk, bottom_line)'],
  validationRules: [
    'at least 2 real briefs must exist in the window - a trend is a sequence of dated points, not a single reading',
    'a genuine query failure blocks the run (queryFailed) rather than being read as "nothing elevated"',
  ],
  possibleDecisionKinds: ['continue-as-is', 'note-trend-in-log', 'escalate-trend'],
  completionCriteria:
    'Either a convergence signal (the trend has settled - direction stable/improving with no elevated points remaining), or reaching the real edge of the window (fewer briefs exist than requested) - never "I scanned everything available." Per MSN-0353 §1.8, there is no execute/verify stage on this type - see the comment on `execute` below.',
  auditOutputs: [
    'the full chronological window read (brief_id, generated_at, overall_risk)',
    'which points were elevated and their direction (worsening/improving/stable/insufficient)',
    'the chosen decision id',
    'a "precedent" learning insight when a genuine trend (not noise) was found',
  ],
  assembleEvidence: assembleTrendScanEvidence,
  validateEvidence: (evidence) => {
    const problems: string[] = [];
    if (evidence.queryFailed) problems.push('the intelligence_briefs query failed - cannot honestly read a trend from a failed fetch');
    else if (evidence.window.length === 0) problems.push('no intelligence briefs exist to scan - there is no sequence to read');
    else if (evidence.window.length === 1) problems.push('only one intelligence brief exists in the window - a trend read requires a sequence of dated points, not a single alert');
    return { ok: problems.length === 0, problems };
  },
  decisionOptions: (evidence) => {
    const options: { id: string; label: string; value: TrendScanDecision; isReversible: boolean }[] = [
      {
        id: 'continue-as-is',
        label:
          evidence.elevatedPoints.length === 0
            ? `No elevated points across ${evidence.window.length} briefs - continue as-is`
            : `Trend read as ${evidence.direction} - continue as-is, nothing in the trend itself is concerning`,
        value: 'continue-as-is',
        isReversible: true,
      },
    ];
    if (evidence.elevatedPoints.length > 0) {
      options.push({
        id: 'note-trend-in-log',
        label: `Log this read - ${evidence.elevatedPoints.length} elevated point(s) (${evidence.elevatedPoints.map((p) => p.overall_risk).join(', ')}) worth a record, even though the trend itself (${evidence.direction}) isn't escalating`,
        value: 'note-trend-in-log',
        isReversible: true,
      });
    }
    if (evidence.direction === 'worsening') {
      options.push({
        id: 'escalate-trend',
        label: `Escalate - the trend itself is worsening across the window, not just one elevated point`,
        value: 'escalate-trend',
        isReversible: true,
      });
    }
    return options;
  },
  // No execute/verify: per MSN-0353 §1.8, Trend Scan is read-only personal
  // judgment - reading a sequence and deciding whether to continue, note, or
  // escalate IS the outcome. There is no downstream action for this
  // definition to perform or verify; inventing one would be exactly the kind
  // of fake execution MSN-0351's Integrity Audit findings exist to prevent.
  isComplete: (state) => {
    const evidence = state.evidence;
    if (state.chosenDecision !== undefined) {
      return { complete: true, reason: `resolved as "${state.chosenDecision}" after reading a ${evidence?.window.length ?? 0}-point window` };
    }
    if (evidence?.reachedEndOfData) {
      return { complete: true, reason: 'reached the edge of what exists - fewer intelligence briefs exist than the scan window requested, no more data to read' };
    }
    return { complete: false, reason: 'awaiting a decision on the read trend' };
  },
  learn: (state) => {
    const evidence = state.evidence;
    if (!evidence) return { insight: null, category: 'none' };
    if (state.chosenDecision === 'note-trend-in-log' || state.chosenDecision === 'escalate-trend') {
      const sequence = evidence.window.map((p) => p.overall_risk).join('→');
      return {
        insight: `Trend Scan read a genuine risk arc across ${evidence.window.length} intelligence briefs (${sequence}) - ${
          state.chosenDecision === 'escalate-trend' ? 'still elevated at the most recent point' : 'elevated then resolved'
        }.`,
        category: 'precedent',
      };
    }
    return { insight: null, category: 'none' };
  },
};

// ─── 2. Noise Triage ────────────────────────────────────────────────────
// MSN-0353 §1.9. Trigger: scanning a list specifically to identify which
// flagged items to *discount*, not to act on. Journey #16's real shape: the
// banking_relevance classifier assigning HIGH-risk badges to unrelated news
// (an "Embodied Regulation" wellbeing article, Iran/Ukraine geopolitics
// items) purely because banking_relevance='high', regardless of actual
// relevance - confirmed live against intelligence_events during this
// mission (336 banking_relevance='high' rows, 324 of them with
// customer_impact != 'high' - the classifier's HIGH badge overwhelmingly
// riding on one field alone).
//
// IMPORTANT, per MSN-0353 §1.9 explicitly: this is NOT a standing Captain
// capability worth building comfortable furniture for. "Where Noise Triage
// recurs on the same source repeatedly, that recurrence itself is the
// trigger for an Integrity Audit - this type should be treated as a signal
// to close, not a workflow to design comfortable furniture for." The
// `recurring-pattern-file-integrity-audit` decision below is that exact
// mechanism, made real and explicit in code: choosing it produces a
// `classifier-defect` learning insight - the same category Integrity Audit
// reads (lib/investigations/integrityAudit.ts) - not just a note in prose.
//
// This reuses `deriveRisk` from lib/intelligenceRisk.ts directly rather
// than re-deriving HIGH/MEDIUM/LOW here, so the flagged pattern can never
// disagree with the real badge the Intelligence page itself renders.

const NOISE_TRIAGE_WINDOW = 30;
const RECURRENCE_THRESHOLD = 3;

export interface NoiseTriageFlaggedItem {
  event_id: string;
  raw_title: string;
  banking_relevance: string | null;
  customer_impact: string | null;
  derivedRisk: RiskLevel;
  collected_at: string | null;
}

export interface NoiseTriageEvidence {
  scanned: number;
  queryFailed: boolean;
  /** Items whose HIGH badge is driven by banking_relevance alone - customer_impact does not corroborate it. This is the exact real pattern journey #16 found, computed via the shared deriveRisk(), not reimplemented. */
  flagged: NoiseTriageFlaggedItem[];
  recurrenceCount: number;
  patternConfirmed: boolean;
}

interface RawIntelligenceEventRow {
  event_id: string;
  raw_title: string;
  banking_relevance: string | null;
  customer_impact: string | null;
  collected_at: string | null;
}

async function assembleNoiseTriageEvidence(): Promise<NoiseTriageEvidence> {
  const { rows, failed } = await fetchRows<RawIntelligenceEventRow>(() =>
    supabase!
      .from('intelligence_events')
      .select('event_id, raw_title, banking_relevance, customer_impact, collected_at')
      .eq('banking_relevance', 'high')
      .order('collected_at', { ascending: false })
      .limit(NOISE_TRIAGE_WINDOW)
  );

  const flagged: NoiseTriageFlaggedItem[] = rows
    .map((row) => ({
      event_id: row.event_id,
      raw_title: row.raw_title,
      banking_relevance: row.banking_relevance,
      customer_impact: row.customer_impact,
      derivedRisk: deriveRisk(row),
      collected_at: row.collected_at,
    }))
    // The real journey #16 pattern: deriveRisk() says HIGH, but it is riding
    // entirely on banking_relevance - customer_impact never corroborates it.
    .filter((item) => item.derivedRisk === 'HIGH' && (item.customer_impact ?? '').toLowerCase() !== 'high');

  const recurrenceCount = flagged.length;

  return {
    scanned: rows.length,
    queryFailed: failed,
    flagged,
    recurrenceCount,
    patternConfirmed: recurrenceCount >= RECURRENCE_THRESHOLD,
  };
}

export type NoiseTriageDecision = 'discount-as-noise' | 'recurring-pattern-file-integrity-audit';

export const noiseTriage: InvestigationDefinition<NoiseTriageEvidence, NoiseTriageDecision> = {
  type: 'noise-triage',
  label: 'Noise Triage',
  owner: 'captain',
  triggerDescription:
    'Scanning a list specifically to identify which flagged items to discount, not to act on. (MSN-0353 §1.9; journeys #16, #20, #21.) NOTE per MSN-0353 §1.9: this is not a legitimate standing capability - a recurring pattern here is itself the trigger for an Integrity Audit against the classifier, not a workflow to keep manually running. Owner is "captain" only in the sense that today, nobody else does it; the target state is the classifier gets fixed and this type stops recurring.',
  requiredEvidence: [
    'up to 30 recent intelligence_events rows with banking_relevance=\'high\' (title, badge inputs, provenance timestamp only - deliberately minimal, per MSN-0353 §1.9)',
    'the derived risk for each row via the shared deriveRisk() (lib/intelligenceRisk.ts), never re-derived locally',
    'whether the same false-positive pattern (HIGH via banking_relevance alone, uncorroborated by customer_impact) has recurred 3+ times in this window',
  ],
  evidenceSources: [
    'lcars-portal Supabase: intelligence_events (event_id, raw_title, banking_relevance, customer_impact, collected_at)',
    'lcars-portal/src/lib/intelligenceRisk.ts (deriveRisk - the same function the Intelligence page badge and server-side filter both already use)',
  ],
  validationRules: [
    'the scanned window must be a real, bounded read of intelligence_events (up to 30 rows) - reflecting the deliberately minimal evidence this type requires, never the full table',
    'a genuine query failure blocks the run rather than being read as "nothing flagged"',
  ],
  possibleDecisionKinds: ['discount-as-noise', 'recurring-pattern-file-integrity-audit'],
  completionCriteria:
    'The pattern is recognized, not any specific item resolved (MSN-0353 §1.9). Recurrence of 3+ same-shape false positives in the window is itself the completion signal for "this needs an Integrity Audit," not a per-item resolution.',
  auditOutputs: [
    'how many intelligence_events rows were scanned',
    'every flagged item (title, banking_relevance, customer_impact, derived risk)',
    'the recurrence count and whether the 3+ pattern threshold was met',
    'the chosen decision id',
    'a "classifier-defect" learning insight when the recurring-pattern decision is chosen - the real mechanism feeding Integrity Audit',
  ],
  assembleEvidence: assembleNoiseTriageEvidence,
  validateEvidence: (evidence) => {
    const problems: string[] = [];
    if (evidence.queryFailed) problems.push('the intelligence_events query failed - cannot honestly triage a failed fetch');
    return { ok: problems.length === 0, problems };
  },
  decisionOptions: (evidence) => {
    const options: { id: string; label: string; value: NoiseTriageDecision; isReversible: boolean }[] = [
      {
        id: 'discount-as-noise',
        label:
          evidence.flagged.length === 0
            ? `No banking_relevance-only HIGH badges in this window - nothing to discount`
            : `Discount ${evidence.flagged.length} item(s) with a HIGH badge driven by banking_relevance alone (e.g. "${evidence.flagged[0]?.raw_title}") as noise for this pass`,
        value: 'discount-as-noise',
        isReversible: true,
      },
    ];
    if (evidence.patternConfirmed) {
      options.push({
        id: 'recurring-pattern-file-integrity-audit',
        label: `Pattern recurred ${evidence.recurrenceCount} times in this window (≥${RECURRENCE_THRESHOLD}) - file as an Integrity Audit item against the banking_relevance classifier instead of continuing to discount manually`,
        value: 'recurring-pattern-file-integrity-audit',
        isReversible: true,
      });
    }
    return options;
  },
  // No execute/verify: the actual classifier fix this type points at (per
  // MSN-0353 §1.9) is out-of-band engineering work - an Integrity Audit
  // diagnose run (lib/investigations/integrityAudit.ts) and a real code
  // change - not something this definition performs itself.
  isComplete: (state) => {
    if (state.chosenDecision === undefined) {
      return { complete: false, reason: 'awaiting a decision on the flagged window' };
    }
    return { complete: true, reason: `resolved as "${state.chosenDecision}"` };
  },
  learn: (state) => {
    const evidence = state.evidence;
    if (!evidence || state.chosenDecision !== 'recurring-pattern-file-integrity-audit') {
      return { insight: null, category: 'none' };
    }
    const examples = evidence.flagged.slice(0, 3).map((f) => f.raw_title).join('; ');
    return {
      insight: `Noise Triage found the banking_relevance classifier assigning a HIGH badge to ${evidence.recurrenceCount} item(s) in this window with no corroborating customer_impact (e.g. ${examples}) - recurred ${RECURRENCE_THRESHOLD}+ times. Per MSN-0353 §1.9 this recurrence is itself the trigger for an Integrity Audit against the classifier, not a standing manual-discount workflow.`,
      category: 'classifier-defect',
    };
  },
};

// ─── 3. Decision Traceback ──────────────────────────────────────────────
// MSN-0353 §1.10. Trigger: about to act on something related, and wanting to
// check whether a prior decision already settled the question - avoiding
// re-litigation. Journey #19's real shape: a decision search that missed on
// the static 26-title ADR Index (no vector-database entry exists in the
// hand-maintained list) and succeeded on the live architecture_records
// table (one real row, ADR-20260608-140000 "Command Memory Data Store
// Selection", decision_summary: "Use Supabase only... No embeddings or
// vector DB needed initially.") - confirmed live against both sources
// during this mission.
//
// Owner: shared - Captain for governance/product precedent, staff for
// technical precedent ahead of implementation work (MSN-0353 §1.10). Same
// type, different callers; this definition doesn't fork behavior by caller
// because the evidence and decision shape are identical either way.

const TRACEBACK_STOPWORDS = new Set([
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'to', 'of', 'in', 'on', 'for', 'and', 'or',
  'before', 'already', 'existed', 'exists', 'question', 'check', 'checking', 'whether', 'about', 'it', 'this',
  'that', 'avoid', 'avoiding', 'repeating', 'debate', 'decision', 'prior', 'again', 'once', 'with', 'have',
  'has', 'had', 'we', 'us', 'our', 'do', 'does', 'did', 'if', 'so', 'than', 'still', 'settled',
]);

/** Pulls concrete search terms out of the Captain/engineer's own trigger.reason prose - not a full-text index, a plain word filter, disclosed here rather than hidden. */
export function extractSearchTerms(reason: string): string[] {
  return Array.from(
    new Set(
      reason
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, ' ')
        .split(/\s+/)
        .filter((word) => word.length > 3 && !TRACEBACK_STOPWORDS.has(word))
    )
  );
}

function textMatchesAnyTerm(text: string | null | undefined, terms: string[]): string[] {
  const haystack = (text ?? '').toLowerCase();
  return terms.filter((term) => haystack.includes(term));
}

// Point-in-time snapshot of the static, hand-maintained ADR Index titles
// rendered on lcars-portal/src/app/(app)/knowledge/page.tsx's "ADR Index"
// tab (26 entries, ADR-001 through ADR-026). Deliberately NOT imported from
// that file - it's a 'use client' UI component, and this lib file builds no
// UI. This snapshot exists for exactly one purpose: to let this definition
// honestly check, per journey #19, whether the same query that found a real
// answer in the live architecture_records table would have come back empty
// against the static list - the actual false-negative journey #19 hit
// searching for "vector database". If the static page's list changes, this
// snapshot may drift from it; that drift is itself further evidence for
// MSN-0353 §4's finding that the static index should be retired in favour
// of the live table, not a bug in this check.
const STATIC_ADR_INDEX_SNAPSHOT: string[] = [
  'ADR-001 — Supabase as primary data store',
  'ADR-002 — Next.js 14 App Router for LCARS Portal',
  'ADR-003 — Python FastAPI for Command Centre backend',
  'ADR-004 — SQLite for local mission state (missions.db)',
  'ADR-005 — Slack as primary push notification channel',
  'ADR-006 — Captain Brief delivered via Slack + Dashy',
  'ADR-007 — Context assembly pipeline (WP-A through WP-D)',
  'ADR-008 — LLM synthesis for weekly intelligence (v2.0)',
  'ADR-009 — 30-day rolling baselines for health/capacity',
  'ADR-010 — Separate health_daily_logs and captains_log_entries',
  'ADR-011 — lessons_learned table for organisational memory',
  'ADR-012 — outcome_quality field on commander_decisions',
  'ADR-013 — Readiness history accumulation pattern',
  'ADR-014 — Captain Profile Memory Bank (captain_profile.txt)',
  'ADR-015 — Engineering handoff advisory-only read model',
  'ADR-016 — 5-status lifecycle (Pending Triage → Completed)',
  'ADR-017 — Universal Search across all tables (Phase 3A)',
  'ADR-018 — Unified Timeline with cross-domain interleaving',
  'ADR-019 — Notification engine single push source (WP-6)',
  'ADR-020 — Mission lifecycle CLI commands',
  'ADR-021 — Proactive scheduler for mission triggers',
  'ADR-022 — Engineering governance review cadence',
  'ADR-023 — P0 security action tracking',
  'ADR-024 — ADR approval workflow (Captain sign-off)',
  'ADR-025 — D-series decision numbering convention',
  'ADR-026 — MSN numbering and phase gate convention',
].map((t) => t.toLowerCase());

function staticAdrIndexWouldMiss(terms: string[]): boolean {
  if (terms.length === 0) return false;
  return !STATIC_ADR_INDEX_SNAPSHOT.some((title) => terms.some((term) => title.includes(term)));
}

export type DecisionTracebackSource = 'architecture_records' | 'commander_decisions' | 'decide_ledger';

export interface DecisionTracebackMatch {
  source: DecisionTracebackSource;
  id: string;
  summary: string;
  status: string | null;
  matchedOn: string[];
}

export interface DecisionTracebackEvidence {
  searchTerms: string[];
  primaryMatch: DecisionTracebackMatch | null;
  /** Which sources were actually queried this run - architecture_records first, falling through to commander_decisions then decide_ledger only when the prior source found nothing (MSN-0353 §1.10's "one authoritative record", searched in the order most likely to hold it). */
  sourcesSearched: DecisionTracebackSource[];
  queryFailed: boolean;
  /** Whether the same search terms would have found nothing in the static, hand-maintained ADR Index snapshot - journey #19's real false-negative finding, checked directly rather than asserted in prose. */
  staticAdrIndexWouldHaveMissed: boolean;
}

interface RawArchitectureRecordRow {
  id: string;
  title: string;
  decision_summary: string | null;
  problem_statement: string | null;
  status: string | null;
  decision_date: string | null;
}

interface RawCommanderDecisionRow {
  id: string;
  decision_title: string;
  decision_summary: string | null;
  status: string | null;
  created_at: string;
}

interface RawDecideLedgerRow {
  id: string;
  question: string;
  action: string | null;
  outcome: string | null;
  decided_at: string;
}

async function assembleDecisionTracebackEvidence(trigger: TriggerContext): Promise<DecisionTracebackEvidence> {
  const searchTerms = extractSearchTerms(trigger.reason);
  const sourcesSearched: DecisionTracebackSource[] = [];
  let queryFailed = false;

  if (searchTerms.length === 0) {
    return { searchTerms, primaryMatch: null, sourcesSearched, queryFailed, staticAdrIndexWouldHaveMissed: false };
  }

  // 1. architecture_records - the real, live decision table, journey #19's
  // actual source of the correct answer.
  sourcesSearched.push('architecture_records');
  const archResult = await fetchRows<RawArchitectureRecordRow>(() =>
    supabase!
      .from('architecture_records')
      .select('id, title, decision_summary, problem_statement, status, decision_date')
      .order('decision_date', { ascending: false })
      .limit(100)
  );
  queryFailed = queryFailed || archResult.failed;
  for (const row of archResult.rows) {
    const matchedOn = Array.from(
      new Set([
        ...textMatchesAnyTerm(row.title, searchTerms),
        ...textMatchesAnyTerm(row.decision_summary, searchTerms),
        ...textMatchesAnyTerm(row.problem_statement, searchTerms),
      ])
    );
    if (matchedOn.length > 0) {
      return {
        searchTerms,
        primaryMatch: { source: 'architecture_records', id: row.id, summary: row.title, status: row.status, matchedOn },
        sourcesSearched,
        queryFailed,
        staticAdrIndexWouldHaveMissed: staticAdrIndexWouldMiss(searchTerms),
      };
    }
  }

  // 2. commander_decisions - secondary source, per the task: real Telegram/
  // Slack-approved decisions that aren't (yet) promoted to an architecture
  // record.
  sourcesSearched.push('commander_decisions');
  const cdResult = await fetchRows<RawCommanderDecisionRow>(() =>
    supabase!
      .from('commander_decisions')
      .select('id, decision_title, decision_summary, status, created_at')
      .order('created_at', { ascending: false })
      .limit(100)
  );
  queryFailed = queryFailed || cdResult.failed;
  for (const row of cdResult.rows) {
    const matchedOn = Array.from(
      new Set([...textMatchesAnyTerm(row.decision_title, searchTerms), ...textMatchesAnyTerm(row.decision_summary, searchTerms)])
    );
    if (matchedOn.length > 0) {
      return {
        searchTerms,
        primaryMatch: { source: 'commander_decisions', id: row.id, summary: row.decision_title, status: row.status, matchedOn },
        sourcesSearched,
        queryFailed,
        staticAdrIndexWouldHaveMissed: staticAdrIndexWouldMiss(searchTerms),
      };
    }
  }

  // 3. decide_ledger - final fallback, the governed-queue outcome record.
  sourcesSearched.push('decide_ledger');
  const ledgerResult = await fetchRows<RawDecideLedgerRow>(() =>
    supabase!
      .from('decide_ledger')
      .select('id, question, action, outcome, decided_at')
      .order('decided_at', { ascending: false })
      .limit(100)
  );
  queryFailed = queryFailed || ledgerResult.failed;
  for (const row of ledgerResult.rows) {
    const matchedOn = textMatchesAnyTerm(row.question, searchTerms);
    if (matchedOn.length > 0) {
      return {
        searchTerms,
        primaryMatch: { source: 'decide_ledger', id: row.id, summary: row.question, status: row.outcome ?? row.action, matchedOn },
        sourcesSearched,
        queryFailed,
        staticAdrIndexWouldHaveMissed: staticAdrIndexWouldMiss(searchTerms),
      };
    }
  }

  return {
    searchTerms,
    primaryMatch: null,
    sourcesSearched,
    queryFailed,
    staticAdrIndexWouldHaveMissed: staticAdrIndexWouldMiss(searchTerms),
  };
}

export type DecisionTracebackDecision = 'proceed-precedent-stands' | 'reopen-stale-precedent' | 'no-precedent-found';

export const decisionTraceback: InvestigationDefinition<DecisionTracebackEvidence, DecisionTracebackDecision> = {
  type: 'decision-traceback',
  label: 'Decision Traceback',
  owner: 'shared',
  triggerDescription:
    'About to act on something related, and wanting to check whether a prior decision already settled the question - avoiding re-litigation. (MSN-0353 §1.10; journey #19 - checking whether a vector-database decision already existed before repeating the debate.) Owner is shared: Captain when the precedent is a governance/product decision, staff when it is a technical precedent ahead of implementation work - same type, different callers.',
  requiredEvidence: [
    'search terms extracted from trigger.reason (the Captain/engineer\'s own words, not a system event name)',
    'one authoritative record\'s summary and current status - architecture_records first, falling through to commander_decisions then decide_ledger only when the prior source found nothing',
    'whether the same search would have found nothing in the static, hand-maintained ADR Index (journey #19\'s real false-negative finding)',
  ],
  evidenceSources: [
    'lcars-portal Supabase: architecture_records (id, title, decision_summary, problem_statement, status, decision_date)',
    'lcars-portal Supabase: commander_decisions (id, decision_title, decision_summary, status, created_at) - secondary source',
    'lcars-portal Supabase: decide_ledger (id, question, action, outcome, decided_at) - tertiary source',
    'lcars-portal/src/app/(app)/knowledge/page.tsx ADR Index tab (static snapshot, for the false-negative check only)',
  ],
  validationRules: [
    'trigger.reason must yield at least one real search term - a traceback needs something concrete to search for',
    'a genuine query failure against any searched source blocks the run rather than being read as "no precedent found"',
  ],
  possibleDecisionKinds: ['proceed-precedent-stands', 'reopen-stale-precedent', 'no-precedent-found'],
  completionCriteria:
    'One record found whose status directly answers the question (MSN-0353 §1.10), or a genuine confirmation that no record exists across all three sources - never inferred from "the static index didn\'t have it."',
  auditOutputs: [
    'the extracted search terms',
    'which sources were actually searched, in order, and where (if anywhere) a match was found',
    'the matched record\'s id, summary, and status',
    'whether the static ADR Index snapshot would have missed the same query',
    'the chosen decision id',
  ],
  assembleEvidence: assembleDecisionTracebackEvidence,
  validateEvidence: (evidence) => {
    const problems: string[] = [];
    if (evidence.searchTerms.length === 0) problems.push('trigger.reason yielded no usable search terms - a decision traceback needs something concrete to search for');
    if (evidence.queryFailed) problems.push('a source query failed - cannot honestly report "no precedent found" from a failed fetch');
    return { ok: problems.length === 0, problems };
  },
  decisionOptions: (evidence) => {
    if (!evidence.primaryMatch) {
      return [
        {
          id: 'no-precedent-found',
          label: `No prior decision found for "${evidence.searchTerms.join(', ')}" across ${evidence.sourcesSearched.join(', ')} - this is genuinely new ground, not a repeated debate`,
          value: 'no-precedent-found',
          isReversible: true,
        },
      ];
    }
    return [
      {
        id: 'proceed-precedent-stands',
        label: `Proceed without reopening - ${evidence.primaryMatch.source} record "${evidence.primaryMatch.summary}" (status: ${evidence.primaryMatch.status ?? 'unknown'}) already settled this`,
        value: 'proceed-precedent-stands',
        isReversible: true,
      },
      {
        id: 'reopen-stale-precedent',
        label: `Reopen deliberately - the record itself looks stale, or the situation has materially changed since "${evidence.primaryMatch.summary}" was decided`,
        value: 'reopen-stale-precedent',
        isReversible: true,
      },
    ];
  },
  // No execute/verify: proceeding or reopening IS the outcome of this
  // decision - there is no separate downstream action for this definition
  // to perform. Reopening produces a new question for a future Decision
  // Traceback or Queue Resolution run, not something executed in-band here.
  isComplete: (state) => {
    const evidence = state.evidence;
    if (state.chosenDecision !== undefined) {
      return { complete: true, reason: `resolved as "${state.chosenDecision}"` };
    }
    if (evidence && !evidence.primaryMatch) {
      return { complete: false, reason: 'no precedent record was found - awaiting a decision that this is genuinely new ground' };
    }
    return { complete: false, reason: 'a precedent record was found - awaiting a decision on whether it still stands' };
  },
  learn: (state) => {
    const evidence = state.evidence;
    if (!evidence) return { insight: null, category: 'none' };

    // The structurally important finding: the live architecture_records
    // table answered the question while the static ADR Index snapshot would
    // have missed it - journey #19's real drift, checked directly rather
    // than assumed. Scoped to architecture_records specifically (not
    // commander_decisions/decide_ledger matches) because that's the exact
    // pair journey #19 and MSN-0353 §4 name as having drifted apart.
    if (evidence.primaryMatch && evidence.primaryMatch.source === 'architecture_records' && evidence.staticAdrIndexWouldHaveMissed) {
      return {
        insight: `Decision Traceback found ${evidence.primaryMatch.source} record "${evidence.primaryMatch.summary}" answering this question directly, while the static, hand-maintained ADR Index (knowledge/page.tsx) has no title matching the same search terms (${evidence.searchTerms.join(', ')}) - a confirmed false negative, the same drift journey #19 found for the vector-database question.`,
        category: 'coverage-gap',
      };
    }
    if (state.chosenDecision === 'reopen-stale-precedent' && evidence.primaryMatch) {
      return {
        insight: `Precedent ${evidence.primaryMatch.source}: "${evidence.primaryMatch.summary}" was judged stale and reopened rather than assumed still valid.`,
        category: 'process-gap',
      };
    }
    if (state.chosenDecision === 'proceed-precedent-stands' && evidence.primaryMatch) {
      return {
        insight: `Existing precedent (${evidence.primaryMatch.source}: "${evidence.primaryMatch.summary}") reused to avoid re-litigating a settled question.`,
        category: 'precedent',
      };
    }
    return { insight: null, category: 'none' };
  },
};
