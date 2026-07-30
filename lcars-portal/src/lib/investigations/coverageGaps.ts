/**
 * MSN-0357 — Investigation type definitions: Upstream Coverage Gap and
 * Downstream Verification Gap.
 *
 * Per MSN-0353 §1.4/§1.5 and §2, these are the same failure shape found at
 * opposite ends of one real pipeline:
 *
 *   real data/condition -> evaluator/nominator -> interrupt surface -> Captain decision -> real-world execution
 *           ^                                                                  ^
 *      Upstream Coverage Gap (1.4)                                Downstream Verification Gap (1.5)
 *      found here - journeys #15, #22                               found here - journey #9
 *
 * Neither definition below invents a parallel check. Both port/reuse the
 * exact mechanisms MSN-0354 and MSN-0356 already built:
 *   - upstreamCoverageGap reuses lib/investigations/integrityAudit.ts's
 *     assembleIntegrityEvidence() - the real registry-vs-live-nominator
 *     comparison MSN-0354 performed by hand for journey #22.
 *   - downstreamVerificationGap is a TypeScript port of
 *     core/coordination/build_request_verifier.py's verify_request /
 *     verify_governed_action / verify_legacy_create_mission /
 *     classify_legacy_shape (MSN-0356) - same tables, same verdict
 *     vocabulary, same thresholds, read live via Supabase instead of
 *     shelled out to Python.
 */

import type { DecisionOption, InvestigationDefinition, TriggerContext } from '@/lib/investigationEngine';
import {
  assembleIntegrityEvidence,
  mismatchSummary,
  validateIntegrityEvidence,
  type IntegrityAuditEvidence,
} from '@/lib/investigations/integrityAudit';
import { createSupabaseServiceRoleClient } from '@/lib/supabase-service-role';
import type { SupabaseClient } from '@supabase/supabase-js';

// ═══════════════════════════════════════════════════════════════════════
// 1. Upstream Coverage Gap (MSN-0353 §1.4)
// ═══════════════════════════════════════════════════════════════════════
//
// Trigger: real data or a real condition exists somewhere, and the question
// is whether *any* evaluator or nominator actually consumes it. Journey #22
// (a real P0 mission never registered with any Interrupt Assembly
// nominator) is exactly the shape assembleIntegrityEvidence() already
// checks: does the live NOMINATORS array (lib/interruptAssembly.ts) and the
// Interrupt Coverage Registry's own declared text (lib/
// interruptCoverageRegistry.ts) agree on what's actually wired? MSN-0353
// itself names this registry as "the home for this investigation type going
// forward, not reinvented" (§1.4) - so this definition does not re-derive
// the comparison, it re-frames the SAME real evidence around Upstream
// Coverage Gap's own trigger language, decision vocabulary (no "acceptable
// to leave" option - MSN-0353 is explicit that an unwired signal has no
// honest all-clear), and completion marker.
//
// Journey #15 (recovery_pulses.nervous_system unread by two queries) is the
// same failure shape in a different domain and was closed by MSN-0355
// wiring analytics_health_daily + recovery_pulses into the
// 'medical-emotional-load' registry entry - that fix is now part of the
// same live registry this check reads, so re-running this definition also
// re-confirms journey #15 stays closed, not just #22.

export type UpstreamCoverageEvidence = IntegrityAuditEvidence;

export type UpstreamCoverageDecision = 'wire-missing-nominator' | 'registry-current-no-gap';

export const upstreamCoverageGap: InvestigationDefinition<UpstreamCoverageEvidence, UpstreamCoverageDecision> = {
  type: 'upstream-coverage-gap',
  label: 'Upstream Coverage Gap',
  owner: 'engineering',
  triggerDescription:
    'Real data or a real condition exists somewhere, and the question is whether any evaluator or nominator actually consumes it. (MSN-0353 §1.4; journey #15 - recovery_pulses.nervous_system sitting unread by both consuming queries, now closed by MSN-0355; journey #22 - a real P0 mission never registered with any Interrupt Assembly nominator, now closed by MSN-0354\'s missionNominator.) This definition makes the check MSN-0354 performed by hand reusable and re-runnable, per MSN-0353\'s own recommendation to treat the Interrupt Coverage Registry as this type\'s standing home rather than rediscovering the gap by accident again.',
  requiredEvidence: [
    'the real, live NOMINATORS array from lib/interruptAssembly.ts, read by function identity (fn.name) - never re-invoked, never re-declared',
    'every nominator function name each INTERRUPT_COVERAGE_REGISTRY entry\'s own declared text (conditions/evidenceSource/falsePositiveGuard/degradationBehaviour/knownGap) claims to be backed by',
    'the result of interruptCoverageRegistry.validateCoverage() against the live registry (MSN-0351 Objective 3\'s own internal-consistency check)',
  ],
  evidenceSources: [
    'lcars-portal/src/lib/interruptAssembly.ts (NOMINATORS) - read via lib/investigations/integrityAudit.ts\'s assembleIntegrityEvidence(), not re-derived here',
    'lcars-portal/src/lib/interruptCoverageRegistry.ts (INTERRUPT_COVERAGE_REGISTRY, validateCoverage)',
  ],
  validationRules: [
    'the Interrupt Coverage Registry must be non-empty - an empty registry cannot be checked against',
    'the live NOMINATORS array must resolve to at least one named function - identity-based comparison requires named function declarations, not anonymous closures',
  ],
  possibleDecisionKinds: ['wire-missing-nominator', 'registry-current-no-gap'],
  completionCriteria:
    'Per MSN-0353 §1.4: the signal is confirmed to reach at least one evaluator that can act on it. A run completes once a decision is recorded - "registry-current-no-gap" when the live wiring and the registry\'s own declared text already agree, or "wire-missing-nominator" when they don\'t. Unlike Integrity Audit, there is deliberately no "reviewed and judged acceptable to leave" option here: an unwired signal is indistinguishable from a genuinely calm one to anyone downstream, which is the specific failure mode this type exists to prevent. The actual wiring is real engineering work performed out-of-band (a code change and PR), same as Integrity Audit - see the comment on `execute` below for why this definition does not perform it itself.',
  auditOutputs: [
    'live nominator names (fn.name) currently wired into NOMINATORS',
    'every nominator name any registry entry\'s own declared text claims to be backed by',
    'any registry-claimed nominator missing from the live array, and any live nominator with no registry entry claiming it',
    'the registry\'s own internal-consistency result (validateCoverage())',
    'the chosen decision id',
    'a coverage-gap learning insight when a real gap was found and the decision was to wire it',
  ],

  // Reuses the exact comparison lib/investigations/integrityAudit.ts already
  // performs (see the import above and the comment on
  // assembleIntegrityEvidence itself) - no parallel logic is declared here.
  assembleEvidence: assembleIntegrityEvidence,
  validateEvidence: (evidence) => validateIntegrityEvidence(evidence),

  decisionOptions: (evidence) => {
    if (evidence.mismatchFound) {
      // Deliberately a single option, not a pair - MSN-0353 §1.4: "There is
      // no 'acceptable to leave' outcome for this type." Contrast with
      // Integrity Audit's diagnose, which does offer a "confirmed-sound"
      // alternative (an in-flight rename can legitimately explain a
      // mismatch there); Upstream Coverage Gap has no such honest out.
      return [
        {
          id: 'wire-missing-nominator',
          label: `Wire the missing nominator - ${mismatchSummary(evidence)}`,
          value: 'wire-missing-nominator',
          isReversible: true,
        },
      ];
    }
    return [
      {
        id: 'registry-current-no-gap',
        label: 'Registry-declared coverage and the live nominator wiring agree - no upstream coverage gap this run',
        value: 'registry-current-no-gap',
        isReversible: true,
      },
    ];
  },

  // No execute/verify. Per MSN-0353 §1.4 (and matching the identical,
  // already-documented reasoning in integrityAudit.ts's three definitions):
  // the actual fix for a confirmed gap is wiring a new nominator into
  // lib/interruptAssembly.ts's NOMINATORS array and/or adding a registry
  // entry that honestly declares it - a real code change and PR, not
  // something an investigation definition can perform on itself without
  // literally editing source files at runtime. The engine records that
  // honestly (`attempted: false`, `not_applicable`) rather than this file
  // inventing a fake execution. This was a deliberate check, not an
  // oversight: the alternative (having `execute` open a PR via some
  // automation) would be new, unreviewed governance surface, which is
  // exactly what this codebase's standing "no parallel routing
  // architecture" rule exists to prevent.
  isComplete: (state) => {
    if (state.chosenDecision === undefined) {
      return { complete: false, reason: 'awaiting a decision - evidence was assembled but nothing has been decided yet' };
    }
    return { complete: true, reason: `resolved as "${state.chosenDecision}"` };
  },
  learn: (state) => {
    const evidence = state.evidence;
    if (!evidence || !evidence.mismatchFound || state.chosenDecision !== 'wire-missing-nominator') {
      return { insight: null, category: 'none' };
    }
    return {
      insight: `Upstream Coverage Gap found a real signal or condition not reaching any Interrupt Assembly evaluator: ${mismatchSummary(evidence)} (MSN-0353 §1.4; same failure shape as journeys #15 and #22).`,
      category: 'coverage-gap',
    };
  },
};

// ═══════════════════════════════════════════════════════════════════════
// 2. Downstream Verification Gap (MSN-0353 §1.5)
// ═══════════════════════════════════════════════════════════════════════
//
// Trigger: a decision was made or approved, and the question is whether the
// real-world action it authorized actually happened. Journey #9 is the real
// row `ca83a08b-cab5-4adf-8e33-f68713e31aa5`: approved, proposing creation
// of "USS-TJR-MSN-0066" - no mission with that id or matching title exists
// in `missions` today. MSN-0356 built core/coordination/
// build_request_verifier.py to close this systemically; this definition is
// a direct TypeScript port of that module's actual logic and thresholds
// (not a re-derivation, not a cross-language shell-out), so a resolution
// recorded here can never silently diverge from what the Python checker
// would say about the same row.

interface BuildRequestActionResult {
  success: boolean;
  detail?: string;
  executed_at?: string;
}

interface BuildRequestRow {
  id: string;
  request_id: string;
  source: string | null;
  requested_by?: string | null;
  title: string | null;
  summary: string | null;
  rationale: string | null;
  status: string;
  action_type: string | null;
  action_payload?: Record<string, unknown> | null;
  action_result: BuildRequestActionResult | null;
  record_path: string | null;
  created_at: string;
}

interface MissionRow {
  mission_id: string;
  title: string;
  status: string;
}

interface DecisionRow {
  id: string;
  decision_title?: string;
  decision_summary?: string;
}

/** Same verdict vocabulary as build_request_verifier.py's PROBLEM_STATUSES. */
export type VerificationVerdict =
  | 'verified'
  | 'not_found_downstream'
  | 'mismatch'
  | 'failed'
  | 'not_attempted'
  | 'unknown_action_type'
  | 'out_of_scope'
  | 'not_approved';

const PROBLEM_STATUSES = new Set<VerificationVerdict>([
  'failed',
  'not_attempted',
  'mismatch',
  'not_found_downstream',
  'unknown_action_type',
]);

export interface VerifiedBuildRequest {
  id: string;
  requestId: string;
  title: string | null;
  source: string | null;
  /** 'governed (MSN-0352, action_type set)' | 'legacy (pre-MSN-0352, no action_type)' | 'n/a' */
  path: string;
  verification: VerificationVerdict;
  evidence: string;
}

// ─── Legacy-path shape classification (text heuristic; no action_type available) ───
// Direct port of build_request_verifier.py's _STOPWORDS / _CREATE_VERB /
// _NEW_MISSION_FORWARD_RE / _NEW_MISSION_BACKWARD_RE / _WORKING_TITLE_RE /
// _MISSION_ID_RE / _TITLE_MATCH_THRESHOLD. Same proximity-window rationale
// documented there: a flat "both words appear somewhere" check produced a
// real false positive (the dead-code-audit row) against live data.

const STOPWORDS = new Set([
  'a', 'an', 'the', 'and', 'or', 'for', 'to', 'of', 'in', 'on', 'system',
  'mission', 'new', 'with', 'via', 'this', 'that', 'into', 'from',
]);

const WORKING_TITLE_RE = /working title[:\s]+\(?([A-Za-z0-9-]+)\)?/i;
const MISSION_ID_RE = /(?:USS-TJR-)?MSN-\d+/i;
const CREATE_VERB = '(?:spawn(?:ing)?|creat(?:e|ing)|establish(?:ing)?|launch(?:ing)?)';
const NEW_MISSION_FORWARD_RE = new RegExp(`\\b${CREATE_VERB}\\b(?:\\W+\\w+){0,5}\\W+\\bmission\\b`, 'i');
const NEW_MISSION_BACKWARD_RE = new RegExp(`\\bmission\\b(?:\\W+\\w+){0,5}\\W+\\b${CREATE_VERB}\\b`, 'i');
const TITLE_MATCH_THRESHOLD = 0.5;

function requestText(row: BuildRequestRow): string {
  return [row.title, row.summary, row.rationale].filter(Boolean).join(' ');
}

/** Direct port of classify_legacy_shape(). */
export function classifyLegacyShape(row: BuildRequestRow): [shape: 'create_mission' | 'other', evidencePhrase: string] {
  const text = requestText(row);
  const match = NEW_MISSION_FORWARD_RE.exec(text) ?? NEW_MISSION_BACKWARD_RE.exec(text);
  if (match) {
    return ['create_mission', `matched mission-creation phrasing: '${match[0]}'`];
  }
  return ['other', 'no mission-creation phrasing detected in title/summary/rationale'];
}

function extractCandidateMissionId(text: string): string | null {
  const workingTitle = WORKING_TITLE_RE.exec(text);
  if (workingTitle) return workingTitle[1].replace(/[).,;:]+$/, '');
  const missionId = MISSION_ID_RE.exec(text);
  if (missionId) return missionId[0];
  return null;
}

/** Direct port of _title_similarity() - Jaccard token overlap. */
function titleSimilarity(a: string, b: string): number {
  const tokenize = (s: string): Set<string> =>
    new Set((s.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => !STOPWORDS.has(w) && w.length > 2));
  const ta = tokenize(a || '');
  const tb = tokenize(b || '');
  if (ta.size === 0 || tb.size === 0) return 0;
  let intersectionSize = 0;
  for (const token of ta) if (tb.has(token)) intersectionSize += 1;
  const unionSize = new Set([...ta, ...tb]).size;
  return intersectionSize / unionSize;
}

/** Direct port of verify_legacy_create_mission() - never returns 'failed'; see build_request_verifier.py's own comment on why. */
export function verifyLegacyCreateMission(row: BuildRequestRow, missions: MissionRow[]): [VerificationVerdict, string] {
  const text = requestText(row);
  const candidateId = extractCandidateMissionId(text);
  if (candidateId) {
    for (const m of missions) {
      if ((m.mission_id || '').toLowerCase().includes(candidateId.toLowerCase())) {
        return ['verified', `mission '${m.mission_id}' matches working-title/referenced id '${candidateId}'`];
      }
    }
  }
  let best: MissionRow | null = null;
  let bestScore = 0;
  for (const m of missions) {
    const score = titleSimilarity(row.title ?? '', m.title ?? '');
    if (score > bestScore) {
      best = m;
      bestScore = score;
    }
  }
  if (best && bestScore >= TITLE_MATCH_THRESHOLD) {
    return ['verified', `mission '${best.mission_id}' ('${best.title}') — title similarity ${bestScore.toFixed(2)}`];
  }
  const detail = candidateId ? `no mission matches candidate id '${candidateId}'` : 'no mission title matches closely enough';
  return [
    'not_found_downstream',
    `${detail}; cannot distinguish never-attempted from silently-failed — no execution-attempt record exists for this pre-MSN-0352 row`,
  ];
}

/** Direct port of verify_governed_action(). */
export function verifyGovernedAction(row: BuildRequestRow, missions: MissionRow[], decisions: DecisionRow[]): [VerificationVerdict, string] {
  const actionType = row.action_type;
  const result = row.action_result ?? null;

  if (actionType === 'create_handoff') {
    return ['verified', 'create_handoff rows are self-fulfilling: the approved row IS the handoff (MSN-0352 precedent)'];
  }
  if (result === null) {
    return ['not_attempted', 'row is approved but carries no action_result — execution route appears not to have run'];
  }
  if (result.success === false) {
    return ['failed', `execution attempt failed: ${result.detail ?? 'no detail recorded'}`];
  }

  if (actionType === 'create_mission') {
    const recordPath = row.record_path ?? '';
    const segments = recordPath.split('/').filter(Boolean);
    const mid = segments.length > 0 ? segments[segments.length - 1] : null;
    const match = mid ? missions.find((m) => m.mission_id === mid) ?? null : null;
    if (match) return ['verified', `mission '${mid}' exists — action_result and missions table agree`];
    return ['mismatch', `action_result claims success (${result.detail}) but no mission '${mid}' found in missions`];
  }

  if (actionType === 'log_decision') {
    const did = row.record_path;
    const match = did ? decisions.find((d) => String(d.id) === String(did)) ?? null : null;
    if (match) return ['verified', `decision '${did}' exists — action_result and commander_decisions table agree`];
    return ['mismatch', `action_result claims success (${result.detail}) but no commander_decisions row '${did}' found`];
  }

  return ['unknown_action_type', `unsupported action_type '${actionType}' — cannot verify`];
}

/** Direct port of verify_request() - the single per-row entry point both the systemic audit and the spot-check mode below call. */
export function verifyRequest(row: BuildRequestRow, missions: MissionRow[], decisions: DecisionRow[]): VerifiedBuildRequest {
  if ((row.status ?? '') !== 'approved') {
    return {
      id: row.id,
      requestId: row.request_id,
      title: row.title,
      source: row.source,
      path: 'n/a',
      verification: 'not_approved',
      evidence: "row is not in status='approved'; nothing to verify",
    };
  }

  let verification: VerificationVerdict;
  let evidence: string;
  let path: string;

  if (row.action_type) {
    [verification, evidence] = verifyGovernedAction(row, missions, decisions);
    path = 'governed (MSN-0352, action_type set)';
  } else {
    const [shape, phrase] = classifyLegacyShape(row);
    if (shape === 'create_mission') {
      const [status, legacyEvidence] = verifyLegacyCreateMission(row, missions);
      verification = status;
      evidence = `${phrase}; ${legacyEvidence}`;
    } else {
      verification = 'out_of_scope';
      evidence = `${phrase} — not mission-creation-shaped; use core.coordination.delivery_reconciler for general engineering/PR-lifecycle verification of this row`;
    }
    path = 'legacy (pre-MSN-0352, no action_type)';
  }

  return { id: row.id, requestId: row.request_id, title: row.title, source: row.source, path, verification, evidence };
}

// ─── Live data access ────────────────────────────────────────────────────
// Same three tables build_request_verifier.py reads (_approved_build_requests
// / _missions / _commander_decisions), queried directly via the same
// service-role Supabase client pattern already used elsewhere in this file
// tree (lib/ai-actions.ts's supabaseAdmin(), lib/supabase-service-role.ts).
// Unlike the Python module's `except Exception: return []` (a silent
// degrade-to-empty), a fetch failure here is carried forward as an explicit
// `fetchError` and validateEvidence blocks the run on it - the same
// fail-closed, no-false-calm principle MSN-0351's degradationIsHonest field
// already enforces everywhere else in this registry.

const APPROVED_COLUMNS =
  'id,request_id,source,requested_by,title,summary,rationale,status,action_type,action_payload,action_result,record_path,created_at';

async function fetchApprovedRows(supabase: SupabaseClient, spotCheckId: string | null): Promise<{ rows: BuildRequestRow[]; error: string | null }> {
  try {
    let query = supabase.from('build_request_inbox').select(APPROVED_COLUMNS).eq('status', 'approved').limit(500);
    if (spotCheckId) query = query.eq('id', spotCheckId);
    const { data, error } = await query;
    if (error) return { rows: [], error: (error as { message?: string }).message ?? String(error) };
    return { rows: (data ?? []) as unknown as BuildRequestRow[], error: null };
  } catch (err) {
    return { rows: [], error: err instanceof Error ? err.message : String(err) };
  }
}

async function fetchMissions(supabase: SupabaseClient): Promise<{ rows: MissionRow[]; error: string | null }> {
  try {
    const { data, error } = await supabase.from('missions').select('mission_id,title,status').limit(1000);
    if (error) return { rows: [], error: (error as { message?: string }).message ?? String(error) };
    return { rows: (data ?? []) as unknown as MissionRow[], error: null };
  } catch (err) {
    return { rows: [], error: err instanceof Error ? err.message : String(err) };
  }
}

async function fetchDecisions(supabase: SupabaseClient): Promise<{ rows: DecisionRow[]; error: string | null }> {
  try {
    const { data, error } = await supabase.from('commander_decisions').select('id,decision_title,decision_summary').limit(1000);
    if (error) return { rows: [], error: (error as { message?: string }).message ?? String(error) };
    return { rows: (data ?? []) as unknown as DecisionRow[], error: null };
  } catch (err) {
    return { rows: [], error: err instanceof Error ? err.message : String(err) };
  }
}

/** Re-checks a specific set of build_request_inbox row ids right now - used by both `execute` (a fresh check) and `verify` (a stability re-check) below, and by the initial evidence assembly. */
async function recheckRows(rowIds: string[] | null): Promise<{ rows: VerifiedBuildRequest[] | null; error: string | null }> {
  let supabase: SupabaseClient;
  try {
    supabase = createSupabaseServiceRoleClient();
  } catch (err) {
    return { rows: null, error: err instanceof Error ? err.message : String(err) };
  }
  const singleId = rowIds && rowIds.length === 1 ? rowIds[0] : null;
  const approved = await fetchApprovedRows(supabase, singleId);
  if (approved.error) return { rows: null, error: approved.error };
  const missionsResult = await fetchMissions(supabase);
  if (missionsResult.error) return { rows: null, error: missionsResult.error };
  const decisionsResult = await fetchDecisions(supabase);
  if (decisionsResult.error) return { rows: null, error: decisionsResult.error };

  const targetRows = rowIds && !singleId ? approved.rows.filter((r) => rowIds.includes(r.id)) : approved.rows;
  return { rows: targetRows.map((r) => verifyRequest(r, missionsResult.rows, decisionsResult.rows)), error: null };
}

export interface DownstreamVerificationEvidence {
  /** 'spot-check' when trigger.originRef named one build_request_inbox row (the Captain "did MY approval land" instance, MSN-0353 §1.5); 'systemic' otherwise (the engineering-owned full-inbox audit). */
  scope: 'spot-check' | 'systemic';
  spotCheckId: string | null;
  fetchError: string | null;
  checkedRows: VerifiedBuildRequest[];
  /** Subset of checkedRows whose verification is one of build_request_verifier.py's PROBLEM_STATUSES. */
  problemRows: VerifiedBuildRequest[];
}

async function assembleDownstreamEvidence(trigger: TriggerContext): Promise<DownstreamVerificationEvidence> {
  const spotCheckId = trigger.originRef ?? null;
  const scope: 'spot-check' | 'systemic' = spotCheckId ? 'spot-check' : 'systemic';
  const result = await recheckRows(spotCheckId ? [spotCheckId] : null);
  if (result.error || result.rows === null) {
    return { scope, spotCheckId, fetchError: result.error, checkedRows: [], problemRows: [] };
  }
  const problemRows = result.rows.filter((r) => PROBLEM_STATUSES.has(r.verification));
  return { scope, spotCheckId, fetchError: null, checkedRows: result.rows, problemRows };
}

// ─── Decision vocabulary ─────────────────────────────────────────────────
// Reuses build_request_verifier.py's own verdict vocabulary, collapsed into
// the three decision kinds a Captain/engineer actually chooses between -
// 'verified' rows need no decision beyond acknowledging 'materialized';
// 'out_of_scope'/'not_approved' rows are outside this checker's remit
// entirely (same as the Python module: "use delivery_reconciler instead").

export type DownstreamDecisionKind = 'materialized' | 'not-found-downstream' | 'mismatch';

/** The rowIds a decision covers travel with it (not just the kind) because
 * `execute`/`verify` below need to know which real row(s) to re-check - the
 * shared engine's `verify` signature does not receive the chosen decision. */
export interface DownstreamVerificationDecision {
  kind: DownstreamDecisionKind;
  rowIds: string[];
}

function bucketFor(verification: VerificationVerdict): DownstreamDecisionKind | null {
  if (verification === 'verified') return 'materialized';
  if (verification === 'not_found_downstream' || verification === 'not_attempted') return 'not-found-downstream';
  if (verification === 'mismatch' || verification === 'failed' || verification === 'unknown_action_type') return 'mismatch';
  return null; // out_of_scope / not_approved
}

function decisionOptionsFor(evidence: DownstreamVerificationEvidence): DecisionOption<DownstreamVerificationDecision>[] {
  if (evidence.scope === 'spot-check') {
    const row = evidence.checkedRows[0];
    if (!row) return [];
    const bucket = bucketFor(row.verification);
    if (!bucket) return [];
    return [
      {
        id: bucket,
        label: `[${row.verification}] ${row.title ?? row.id} — ${row.evidence}`,
        value: { kind: bucket, rowIds: [row.id] },
        isReversible: true,
      },
    ];
  }

  const byBucket = new Map<DownstreamDecisionKind, VerifiedBuildRequest[]>();
  for (const row of evidence.problemRows) {
    const bucket = bucketFor(row.verification);
    if (!bucket) continue;
    const list = byBucket.get(bucket) ?? [];
    list.push(row);
    byBucket.set(bucket, list);
  }
  if (byBucket.size === 0) {
    return [
      {
        id: 'materialized',
        label: `All ${evidence.checkedRows.length} approved build request(s) checked materialized downstream — no verification gap this run`,
        value: { kind: 'materialized', rowIds: evidence.checkedRows.map((r) => r.id) },
        isReversible: true,
      },
    ];
  }
  const options: DecisionOption<DownstreamVerificationDecision>[] = [];
  for (const [bucket, rows] of byBucket) {
    options.push({
      id: bucket,
      label: `${rows.length} row(s) [${bucket}]: ${rows.map((r) => `${r.id} (${r.verification})`).join(', ')}`,
      value: { kind: bucket, rowIds: rows.map((r) => r.id) },
      isReversible: true,
    });
  }
  return options;
}

function targetRowIdsForVerification(evidence: DownstreamVerificationEvidence): string[] {
  if (evidence.scope === 'spot-check' && evidence.spotCheckId) return [evidence.spotCheckId];
  return evidence.problemRows.length > 0 ? evidence.problemRows.map((r) => r.id) : evidence.checkedRows.map((r) => r.id);
}

export const downstreamVerificationGap: InvestigationDefinition<DownstreamVerificationEvidence, DownstreamVerificationDecision> = {
  type: 'downstream-verification-gap',
  label: 'Downstream Verification Gap',
  owner: 'shared',
  triggerDescription:
    'A decision was made or approved, and the question is whether the real-world action it authorized actually happened. (MSN-0353 §1.5; journey #9 - build_request_inbox row ca83a08b, approved, proposing creation of "USS-TJR-MSN-0066" with no corresponding row in missions.) Owner is shared per MSN-0353: engineering owns the systemic audit over every approved row (trigger.originRef unset); a Captain spot-checking "did MY specific approval land" is a legitimate individual instance too (trigger.originRef = the build_request_inbox row id).',
  requiredEvidence: [
    'every build_request_inbox row with status=\'approved\' (systemic scope), or the single row named by trigger.originRef (spot-check scope)',
    'the real missions table (mission_id, title, status), to check create_mission-shaped approvals - both governed (action_type set, MSN-0352) and legacy (pre-MSN-0352, text-classified) - against',
    'the real commander_decisions table (id, decision_title, decision_summary), to check log_decision-shaped governed approvals against',
  ],
  evidenceSources: [
    'lcars-portal/src/lib/investigations/coverageGaps.ts verifyRequest()/verifyGovernedAction()/verifyLegacyCreateMission()/classifyLegacyShape() - a direct TypeScript port of core/coordination/build_request_verifier.py (MSN-0356), same table columns, same regex thresholds, same verdict vocabulary',
    'Supabase build_request_inbox, missions, commander_decisions (project cjvrpjwewsrumnbdydgg), read via lib/supabase-service-role.ts\'s service-role client',
  ],
  validationRules: [
    'the build_request_inbox/missions/commander_decisions reads must actually succeed - a fetch failure blocks the run (fetchError set) rather than silently reading as an empty, all-clear result',
    'in spot-check mode, trigger.originRef must name a real build_request_inbox row that is actually in status=\'approved\' - there is nothing to verify against an unapproved or nonexistent row',
  ],
  possibleDecisionKinds: ['materialized', 'not-found-downstream', 'mismatch'],
  completionCriteria:
    'A decision has been recorded covering every problem row this run found (or the single "materialized" acknowledgment when none were found) - using the exact verdict vocabulary build_request_verifier.py already reports, so a resolution here can never silently diverge from what the Python systemic audit would say about the same row. Per MSN-0353 §1.5 this completion marker did not exist before MSN-0356; this definition is that marker made runnable.',
  auditOutputs: [
    'the scope of this run (systemic full-inbox audit, or a single spot-checked build_request_inbox row id)',
    'every checked row\'s id, path (governed vs legacy), verification verdict, and evidence string',
    'the subset of rows in a PROBLEM_STATUSES verdict (mismatch / failed / not_found_downstream / not_attempted / unknown_action_type)',
    'the chosen decision kind and which row(s) it covers',
    'for a decided run: the execute-stage re-check verdict and the verify-stage two-consecutive-checks stability result',
  ],

  assembleEvidence: assembleDownstreamEvidence,
  validateEvidence: (evidence) => {
    const problems: string[] = [];
    if (evidence.fetchError) {
      problems.push(`could not read build_request_inbox/missions/commander_decisions: ${evidence.fetchError}`);
    } else if (evidence.scope === 'spot-check' && evidence.checkedRows.length === 0) {
      problems.push(`no approved build_request_inbox row found for id '${evidence.spotCheckId}' — nothing to verify`);
    }
    return { ok: problems.length === 0, problems };
  },
  decisionOptions: decisionOptionsFor,

  // Unlike Upstream Coverage Gap / Integrity Audit / Redundancy
  // Reconciliation (all of which correctly omit execute/verify because their
  // real fix is out-of-band engineering work), the Downstream Verification
  // Gap spot-check genuinely has something safe and useful to execute on
  // demand: re-running the SAME read-only check against the SAME real
  // tables, right now, is exactly the "did my approval land [yet]" question
  // a Captain spot-check exists to answer - a row that read
  // not_found_downstream a minute ago may read verified now if the mission
  // was created moments later. `execute` performs no write of its own (this
  // stays read-only, same as build_request_verifier.py's own module
  // docstring: "Read-only. Makes no writes to any table."); `verify`
  // confirms the re-checked verdict is stable by running the same read-only
  // check a second time and comparing, guarding against a one-off
  // replication-lag or race read being mistaken for a settled answer.
  execute: async (decision) => {
    const { rows, error } = await recheckRows(decision.rowIds);
    if (error || rows === null) {
      return { attempted: true, success: false, detail: `re-check query failed: ${error}` };
    }
    if (rows.length === 0) {
      return {
        attempted: true,
        success: false,
        detail: `none of row(s) ${decision.rowIds.join(', ')} are still an approved build_request_inbox row to re-check`,
      };
    }
    const matchesDecision = rows.every((r) => bucketFor(r.verification) === decision.kind);
    return {
      attempted: true,
      success: matchesDecision,
      detail: `re-ran the downstream check just now: ${rows.map((r) => `${r.id}=${r.verification}`).join(', ')}${
        matchesDecision ? ' — matches the recorded decision' : ' — verdict has changed since the decision was recorded'
      }`,
    };
  },
  verify: async (execution, evidence) => {
    if (!execution.attempted) return { status: 'not_attempted', detail: 'no execution to verify' };
    const rowIds = targetRowIdsForVerification(evidence);
    const first = await recheckRows(rowIds);
    const second = await recheckRows(rowIds);
    if (first.error || second.error || first.rows === null || second.rows === null) {
      return { status: 'failed', detail: `could not confirm stability: ${first.error ?? second.error}` };
    }
    if (first.rows.length === 0) {
      return { status: 'not_applicable', detail: 'row(s) no longer approved — nothing left to confirm as stable' };
    }
    const describe = (rows: VerifiedBuildRequest[]) => rows.map((r) => `${r.id}=${r.verification}`).sort().join(',');
    const firstVerdicts = describe(first.rows);
    const secondVerdicts = describe(second.rows);
    if (firstVerdicts !== secondVerdicts) {
      return { status: 'mismatch', detail: `verdict changed between two consecutive checks: [${firstVerdicts}] vs [${secondVerdicts}] — not stable, treat as unresolved` };
    }
    return { status: 'verified', detail: `verdict is stable across two consecutive checks: ${secondVerdicts}` };
  },

  isComplete: (state) => {
    const evidence = state.evidence;
    if (!evidence) return { complete: false, reason: 'no evidence assembled' };
    if (state.chosenDecision !== undefined) {
      return { complete: true, reason: `resolved as "${state.chosenDecision.kind}" for row(s) ${state.chosenDecision.rowIds.join(', ')}` };
    }
    if (state.decisionOptions && state.decisionOptions.length === 0) {
      const reason =
        evidence.scope === 'spot-check'
          ? `row ${evidence.spotCheckId} is out of this checker's scope (verification='${evidence.checkedRows[0]?.verification ?? 'unknown'}') — nothing to decide`
          : 'no approved rows were checked this run — nothing to decide';
      return { complete: true, reason };
    }
    return { complete: false, reason: 'awaiting a decision on the verification result' };
  },
  learn: (state) => {
    if (!state.chosenDecision || state.chosenDecision.kind === 'materialized') {
      return { insight: null, category: 'none' };
    }
    return {
      insight: `Downstream Verification Gap found approved build_request_inbox row(s) whose approval did not verifiably materialize downstream: ${state.chosenDecision.rowIds.join(', ')} (${state.chosenDecision.kind}). Same failure shape as journey #9 / row ca83a08b (MSN-0353 §1.5; MSN-0356).`,
      category: 'process-gap',
    };
  },
};
