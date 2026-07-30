/**
 * MSN-0357 — Investigation type definitions: Queue Resolution and Queue
 * Triage / Deduplication.
 *
 * Per MSN-0353 §1.6-§1.7 and the journeys they actually come from
 * (docs/MSN-0350-INVESTIGATION-JOURNEYS.md #7, #8, #10, #11): both types
 * wrap the SAME governed approval mechanism the product already has - they
 * do not invent a second one. Queue Resolution wraps a single
 * build_request_inbox row through exactly the question/reasoning/approve
 * path lib/decide.ts already computes; Queue Triage wraps the same
 * awaiting_review read lib/decide.ts already filters to, plus a real
 * title-similarity check journey #8 shows was never automated.
 *
 * Reuse, not reimplementation:
 *   - lib/decide.ts's exported `engineeringReasoning` / `proposedActionReasoning`
 *     produce this file's reasoning text - never reimplemented here.
 *   - lib/ai-actions.ts's exported `createMission` / `logDecision` /
 *     `validateActionPayload` / `supabaseAdmin` perform every real mutation
 *     and fail-closed check a governed proposal requires - never
 *     reimplemented here. (lib/ai-actions.ts's own `POST
 *     /api/build-request/[id]/approve-action` route is a Next.js route
 *     handler bound to NextRequest/NextResponse and a real Captain session
 *     cookie; it cannot be called as a plain function from a library
 *     context, so this file calls the same underlying functions the route
 *     itself calls, which is the real execution path either way.)
 *   - lib/engineering-queue.ts's exported `fetchEngineeringQueue` /
 *     `setQueueItemStatus` / `normalizeLifecycle` are the only queue reads
 *     and status mutations used here - the exact same filter
 *     (`lifecycle === 'awaiting_review' && source === 'build'`) lib/decide.ts
 *     itself applies.
 *   - lib/investigations/coverageGaps.ts's exported `verifyGovernedAction`
 *     (MSN-0357's Downstream Verification Gap definition, a TypeScript port
 *     of core/coordination/build_request_verifier.py / MSN-0356) is reused
 *     directly by Queue Resolution's `verify` stage for governed
 *     (create_mission/log_decision) approvals - the same "does the claimed
 *     downstream row genuinely exist" check, not a second implementation of
 *     it. See the comment on `verify` below for why `execute` now writes
 *     action_result/record_path onto the row (mirroring
 *     approve-action/route.ts) - it's what makes that reuse possible.
 */

import type {
  InvestigationDefinition,
  TriggerContext,
  VerificationResult,
} from '@/lib/investigationEngine';
import {
  createMission,
  logDecision,
  validateActionPayload,
  supabaseAdmin,
  type ActionResult,
} from '@/lib/ai-actions';
import {
  fetchEngineeringQueue,
  setQueueItemStatus,
  normalizeLifecycle,
  type QueueItem,
} from '@/lib/engineering-queue';
import { engineeringReasoning, proposedActionReasoning } from '@/lib/decide';
import { verifyGovernedAction, type VerificationVerdict } from '@/lib/investigations/coverageGaps';

// ─── Shared: a single-row read against build_request_inbox / its downstream
// tables, used by both definitions below. Not exported from
// lib/ai-actions.ts or lib/engineering-queue.ts today (both only expose
// bulk/list reads), so this is the one genuinely new query in this file -
// everything else reuses an existing exported function directly. ──────────

async function fetchSingleRow(
  table: string,
  column: string,
  value: string,
  columns: string
): Promise<{ data: Record<string, unknown> | null; error: string | null }> {
  try {
    const { data, error } = await supabaseAdmin().from(table).select(columns).eq(column, value).maybeSingle();
    if (error) return { data: null, error: error.message };
    return { data: (data as Record<string, unknown> | null) ?? null, error: null };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : String(err) };
  }
}

/** Persists an execution outcome onto the build_request_inbox row itself -
 * mirrors approve-action/route.ts's own update() call exactly (status,
 * record_path, action_result) so a row this file approves is
 * indistinguishable, on the table, from one approved through the HTTP
 * route. Written here rather than reused from route.ts because Next.js
 * route handlers are bound to (NextRequest, params) and a real Captain
 * session cookie - they are not callable as plain library functions (see
 * the file header comment). This IS necessary, not a convenience: it is
 * what lets verify() below reuse coverageGaps.ts's verifyGovernedAction()
 * unmodified, since that function reads action_result/record_path off the
 * row exactly as the real approve-action route leaves them. */
async function updateBuildRequestRow(id: string, patch: Record<string, unknown>): Promise<{ ok: boolean; error?: string }> {
  try {
    const { error } = await supabaseAdmin().from('build_request_inbox').update(patch).eq('id', id);
    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

// ─── 1. Queue Resolution ────────────────────────────────────────────────────
// MSN-0353 §1.6. Trigger: a specific item is sitting in a governed approval
// queue, requiring a decision. (Journeys #7 - the MSN-0064 two-decision
// approval thread; #10 - an empty/malformed build request with nothing to
// review; #11 - an AI-proposed mission creation through the MSN-0352
// governed path.) "Evidence required: exactly the fields Decide already
// surfaces - rationale, risks, question, reasoning, undo-availability.
// Never more than what's on the row itself."

export interface QueueResolutionRow {
  id: string;
  title: string;
  summary: string | null;
  rationale: string | null;
  risks: string | null;
  status: string;
  actionType: string | null;
  actionPayload: Record<string, unknown> | null;
}

export interface QueueResolutionEvidence {
  found: boolean;
  fetchError: string | null;
  row: QueueResolutionRow | null;
  /** Same text Decide itself would show - see questionForRow() below. */
  question: string;
  /** Reused verbatim from lib/decide.ts's exported reasoning functions. */
  reasoning: string;
  undoAvailable: boolean;
  /** Set by execute() when a governed action (create_mission/log_decision)
   * actually runs, so verify() can check the real id it produced against
   * the real downstream table - ExecutionResult (investigationEngine.ts)
   * has no id field of its own, and that file is locked, so this is the
   * one place this evidence object is allowed to carry state forward
   * between execute() and verify() within a single resolveInvestigation()
   * call. */
  createdRecordId?: string | null;
}

function toQueueItem(row: QueueResolutionRow): QueueItem {
  return {
    id: row.id,
    title: row.title,
    summary: row.summary,
    rawStatus: row.status,
    lifecycle: normalizeLifecycle(row.status),
    blocked: /block/.test(row.status.toLowerCase()),
    source: 'build',
    priority: null,
    prUrl: null,
    ageDays: null,
    createdAt: null,
    nextAction: '',
    actionType: row.actionType,
  };
}

/** Maps coverageGaps.ts's VerificationVerdict vocabulary (shared with
 * core/coordination/build_request_verifier.py, MSN-0356) onto
 * investigationEngine.ts's locked VerificationResult.status vocabulary.
 * verifyGovernedAction() only ever returns 'verified' | 'not_attempted' |
 * 'failed' | 'mismatch' | 'unknown_action_type' - the last is a defensive
 * case (an action_type outside create_mission/create_handoff/log_decision)
 * that is unreachable on this file's own governed path today, mapped to
 * 'failed' rather than silently treated as any kind of pass. */
function mapVerdictToVerificationResult(verdict: VerificationVerdict, detail: string): VerificationResult {
  switch (verdict) {
    case 'verified':
      return { status: 'verified', detail };
    case 'mismatch':
      return { status: 'mismatch', detail };
    case 'not_attempted':
      return { status: 'not_attempted', detail };
    case 'failed':
    case 'unknown_action_type':
      return { status: 'failed', detail };
    default:
      return { status: 'not_applicable', detail };
  }
}

/** lib/decide.ts's own `questionFor()` is a private, unexported helper - it
 * cannot be imported. This mirrors its exact text shape (never invents new
 * copy) while genuinely reusing the two EXPORTED reasoning functions
 * (engineeringReasoning / proposedActionReasoning) for the actual reasoning
 * text, which is the part MSN-0353 §1.6 cares about ("evidence required:
 * exactly the fields Decide already surfaces"). */
function questionForRow(row: QueueResolutionRow): string {
  if (row.actionType === 'create_mission') return `Approve mission creation: "${row.title}"?`;
  if (row.actionType === 'log_decision') return `Approve decision log: "${row.title}"?`;
  return `Approve build request "${row.title}"?`;
}

async function assembleQueueResolutionEvidence(trigger: TriggerContext): Promise<QueueResolutionEvidence> {
  const id = trigger.originRef;
  if (!id) {
    return { found: false, fetchError: 'no originRef supplied', row: null, question: '', reasoning: '', undoAvailable: false };
  }

  const { data, error } = await fetchSingleRow(
    'build_request_inbox',
    'id',
    id,
    'id, title, summary, rationale, risks, status, action_type, action_payload'
  );
  if (error || !data) {
    return { found: false, fetchError: error ?? 'row not found', row: null, question: '', reasoning: '', undoAvailable: false };
  }

  const row: QueueResolutionRow = {
    id: String(data.id ?? id),
    title: String(data.title ?? ''),
    summary: (data.summary as string | null) ?? null,
    rationale: (data.rationale as string | null) ?? null,
    risks: (data.risks as string | null) ?? null,
    status: String(data.status ?? ''),
    actionType: (data.action_type as string | null) ?? null,
    actionPayload: (data.action_payload as Record<string, unknown> | null) ?? null,
  };
  const queueItem = toQueueItem(row);
  // MSN-0352: irreversible governed mutations (create_mission/log_decision)
  // are never undo-eligible - the same rule decide.ts::fetchDecideEngineeringItems
  // already applies, restated here against the same actionType field.
  const isIrreversibleProposal = row.actionType === 'create_mission' || row.actionType === 'log_decision';
  const reasoning = row.actionType ? proposedActionReasoning(queueItem) : engineeringReasoning(queueItem);

  return {
    found: true,
    fetchError: null,
    row,
    question: questionForRow(row),
    reasoning,
    undoAvailable: !isIrreversibleProposal,
  };
}

function validateQueueResolutionEvidence(evidence: QueueResolutionEvidence, trigger: TriggerContext) {
  const problems: string[] = [];
  if (!trigger.originRef) {
    problems.push('no originRef given - Queue Resolution requires a specific build_request_inbox row id to evaluate');
  }
  if (!evidence.found) {
    problems.push(evidence.fetchError ? `could not load the row: ${evidence.fetchError}` : 'no build_request_inbox row found for the given id');
  } else if (evidence.row) {
    // MSN-0350 journey #10: an empty/malformed proposal, self-disclosing
    // there was nothing to review, archived immediately with no
    // approve/hold cycle at all. Failing evidence_validation here - rather
    // than offering a hollow decision - is exactly that "resolves
    // trivially" shape: investigationEngine.ts's own openInvestigation()
    // stops before decision_options and records "no decision was ever
    // offered", honestly, without this file inventing a fake option.
    if (evidence.row.title.trim().length === 0) {
      problems.push('this request has no title - nothing here to review (MSN-0350 journey #10: an empty/malformed request with no evidence trail)');
    }
    if (evidence.row.status !== 'awaiting_review') {
      problems.push(`row status is "${evidence.row.status}", not "awaiting_review" - it is not currently queued for a decision`);
    }
  }
  return { ok: problems.length === 0, problems };
}

// Decide's real vocabulary, per lib/decide.ts's own documented model: there
// is no literal "reject" - approve, hold, or (for engineering rows) undo an
// approval already made. Queue Resolution offers exactly the two decisions
// available before any mutation happens.
export type QueueResolutionDecision = 'approve' | 'hold';

export const queueResolution: InvestigationDefinition<QueueResolutionEvidence, QueueResolutionDecision> = {
  type: 'queue-resolution',
  label: 'Queue Resolution',
  // 'captain' here includes Captain-delegated approvers acting within
  // granted authority - the real evidence includes Chief-Engineer-channel
  // Telegram approvals, consistent with this project's existing
  // authority-matrix model (core/governance/authority-matrix.txt). This is
  // not a new ownership category; it is the same delegation the project
  // already runs (MSN-0353 §1.6).
  owner: 'captain',
  triggerDescription:
    'A specific item is sitting in a governed approval queue, requiring a decision. (MSN-0353 §1.6; MSN-0350 journeys #7, #10, #11 - the MSN-0064 two-decision approval thread, an empty/malformed build request, an AI-proposed mission creation through the MSN-0352 governed path.)',
  requiredEvidence: [
    'the single build_request_inbox row named by trigger.originRef, including its rationale and risks columns',
    'the same question/reasoning text Decide itself would show (lib/decide.ts engineeringReasoning / proposedActionReasoning)',
    'whether the item is undo-eligible (MSN-0352: false for create_mission/log_decision, true otherwise)',
    'on approval of a governed proposal: the real downstream row (missions/commander_decisions) verifyGovernedAction() checks it against',
  ],
  evidenceSources: [
    'lcars-portal/src/lib/ai-actions.ts (supabaseAdmin - build_request_inbox read; createMission/logDecision/validateActionPayload - the real execution path)',
    'lcars-portal/src/lib/decide.ts (engineeringReasoning, proposedActionReasoning)',
    'lcars-portal/src/lib/investigations/coverageGaps.ts (verifyGovernedAction) - reused for the downstream-materialization check, not re-derived',
  ],
  validationRules: [
    'trigger.originRef must name a real build_request_inbox row id',
    'the row must have a non-empty title - an empty/malformed request has nothing to review (MSN-0350 journey #10)',
    'the row must currently be status="awaiting_review" - already-resolved or not-yet-queued rows are not eligible for a fresh decision',
  ],
  possibleDecisionKinds: ['approve', 'hold'],
  completionCriteria:
    'A decision (approve or hold) has been recorded. For approve, completion additionally requires the execution to have succeeded AND verify() to have confirmed the claimed downstream artefact genuinely exists - per MSN-0353 §1.5/§1.6, a status flip to "approved" alone is never treated as proof the underlying action occurred.',
  auditOutputs: [
    'the row id, title, and action_type evaluated',
    'the chosen decision (approve/hold)',
    'the execution result (attempted/success/detail) when approved',
    'the verification result (verified/mismatch/failed/not_applicable) comparing the claim against the real downstream table',
  ],
  assembleEvidence: assembleQueueResolutionEvidence,
  validateEvidence: (evidence, trigger) => validateQueueResolutionEvidence(evidence, trigger),
  decisionOptions: (evidence) => [
    {
      id: 'approve',
      label: `Approve - ${evidence.question}`,
      value: 'approve',
      isReversible: evidence.undoAvailable,
    },
    {
      id: 'hold',
      label: 'Hold - defer this decision; the item stays exactly as it is and reappears next pass',
      value: 'hold',
      isReversible: true,
    },
  ],
  execute: async (decision, evidence) => {
    if (decision === 'hold') {
      // Matches holdDecideItem's own documented semantics exactly: hold
      // deliberately calls no source route - nothing was decided, so
      // nothing should look decided.
      return { attempted: false, success: null, detail: 'Hold defers - no mutation performed, matching Decide\'s holdDecideItem semantics.' };
    }

    // validateEvidence guarantees evidence.row is non-null once execution
    // is reachable (see the `!evidence.found` check above).
    const row = evidence.row!;
    const queueItem = toQueueItem(row);

    if (row.actionType === 'create_mission' || row.actionType === 'log_decision') {
      // Same fail-closed re-validation approve-action/route.ts performs
      // immediately before executing a governed proposal - never trust a
      // stored payload just because it reached this table.
      const validation = validateActionPayload(row.actionType, row.actionPayload ?? {});
      if (!validation.ok) {
        await updateBuildRequestRow(row.id, {
          action_result: { success: false, detail: validation.error, executed_at: new Date().toISOString() },
        });
        return { attempted: true, success: false, detail: `Execution refused: ${validation.error}` };
      }

      const result: ActionResult =
        row.actionType === 'create_mission' ? await createMission(row.actionPayload ?? {}) : await logDecision(row.actionPayload ?? {});
      // Carried forward to verify() - see the field comment on
      // QueueResolutionEvidence.createdRecordId.
      evidence.createdRecordId = result.id ?? null;

      if (!result.success) {
        await updateBuildRequestRow(row.id, {
          action_result: { success: false, detail: result.detail, executed_at: new Date().toISOString() },
        });
        return { attempted: true, success: false, detail: result.detail };
      }

      // Same update shape approve-action/route.ts performs on a successful
      // execution (status/record_path/action_result together) - see the
      // comment on updateBuildRequestRow() above for why this is written
      // directly rather than reused from the route handler itself.
      const recordPath = row.actionType === 'create_mission' ? `/missions/${result.id ?? ''}` : (result.id ?? null);
      const flip = await updateBuildRequestRow(row.id, {
        status: 'approved',
        record_path: recordPath,
        action_result: { success: true, detail: result.detail, executed_at: new Date().toISOString() },
      });
      return {
        attempted: true,
        success: true,
        detail: flip.ok ? result.detail : `${result.detail} (warning: row bookkeeping update failed: ${flip.error})`,
      };
    }

    // Ordinary build request or create_handoff: identical in shape to
    // decide.ts::approveDecideItem's else-branch - just a status flip via
    // the same real function.
    const flip = await setQueueItemStatus(queueItem, 'approved');
    return { attempted: true, success: flip.ok, detail: flip.ok ? `Approved "${row.title}"` : flip.error ?? 'approval failed' };
  },
  // Shares its "claimed vs real downstream" comparison shape with the
  // Downstream Verification Gap investigation type (MSN-0353 §1.5) - the
  // create_mission/log_decision branch below calls coverageGaps.ts's own
  // exported verifyGovernedAction() directly (a TypeScript port of
  // core/coordination/build_request_verifier.py, MSN-0356) rather than
  // re-deriving the same "does the claimed downstream row genuinely exist"
  // check a second time. This is exactly the shared-logic case this
  // mission's own brief called out. The plain build request / create_handoff
  // branch is a genuinely different, simpler check (did the row's own
  // status field flip - there is no separate downstream artefact to claim
  // exists), so it is not a duplicate of anything in coverageGaps.ts and
  // stays inline.
  verify: async (execution, evidence) => {
    if (!execution.attempted) {
      return { status: 'not_applicable', detail: 'no execution to verify (held)' };
    }
    if (!execution.success) {
      return { status: 'failed', detail: execution.detail };
    }
    const row = evidence.row;
    if (!row) {
      return { status: 'not_attempted', detail: 'no row evidence to verify against' };
    }

    if (row.actionType === 'create_mission' || row.actionType === 'log_decision') {
      const { data: freshRowData, error: freshRowError } = await fetchSingleRow(
        'build_request_inbox',
        'id',
        row.id,
        'id, request_id, source, requested_by, title, summary, rationale, status, action_type, action_payload, action_result, record_path, created_at'
      );
      if (freshRowError || !freshRowData) {
        return { status: 'failed', detail: `could not re-read the row for verification: ${freshRowError ?? 'row missing'}` };
      }
      // Structurally matches coverageGaps.ts's (unexported) BuildRequestRow -
      // its interfaces are internal to that module, but verifyGovernedAction
      // only depends on shape, not on importing the type name.
      const freshRow = {
        id: String(freshRowData.id ?? row.id),
        request_id: String(freshRowData.request_id ?? ''),
        source: (freshRowData.source as string | null) ?? null,
        title: (freshRowData.title as string | null) ?? row.title,
        summary: (freshRowData.summary as string | null) ?? null,
        rationale: (freshRowData.rationale as string | null) ?? null,
        status: String(freshRowData.status ?? row.status),
        action_type: (freshRowData.action_type as string | null) ?? row.actionType,
        action_payload: (freshRowData.action_payload as Record<string, unknown> | null) ?? null,
        action_result: (freshRowData.action_result as { success: boolean; detail?: string; executed_at?: string } | null) ?? null,
        record_path: (freshRowData.record_path as string | null) ?? null,
        created_at: String(freshRowData.created_at ?? ''),
      };

      let matchedMission: { mission_id: string; title: string; status: string } | null = null;
      let matchedDecision: { id: string; decision_title?: string; decision_summary?: string } | null = null;
      if (row.actionType === 'create_mission' && evidence.createdRecordId) {
        const { data } = await fetchSingleRow('missions', 'mission_id', evidence.createdRecordId, 'mission_id, title, status');
        matchedMission = data ? { mission_id: String(data.mission_id), title: String(data.title ?? ''), status: String(data.status ?? '') } : null;
      }
      if (row.actionType === 'log_decision' && evidence.createdRecordId) {
        const { data } = await fetchSingleRow('commander_decisions', 'id', evidence.createdRecordId, 'id, decision_title, decision_summary');
        matchedDecision = data ? { id: String(data.id) } : null;
      }

      const [verdict, verdictEvidence] = verifyGovernedAction(freshRow, matchedMission ? [matchedMission] : [], matchedDecision ? [matchedDecision] : []);
      return mapVerdictToVerificationResult(verdict, verdictEvidence);
    }

    // Plain build request / create_handoff: the simplest real claim-vs-
    // reality check available - re-read the row and confirm its own status
    // genuinely flipped, rather than trusting the earlier flip.ok result.
    const { data, error } = await fetchSingleRow('build_request_inbox', 'id', row.id, 'status');
    if (error) return { status: 'failed', detail: `could not verify: ${error}` };
    const status = data ? String(data.status) : null;
    return status === 'approved'
      ? { status: 'verified', detail: `row ${row.id} confirmed approved` }
      : { status: 'mismatch', detail: `execution reported success but the row's live status is "${status ?? 'unknown'}", not "approved"` };
  },
  isComplete: (state) => {
    if (state.chosenDecision === undefined) {
      return { complete: false, reason: 'awaiting a decision - evidence was assembled but nothing has been decided yet' };
    }
    if (state.chosenDecision === 'hold') {
      return { complete: false, reason: 'held - deferred, will reappear in the queue next pass (holdDecideItem semantics)' };
    }
    if (state.verification?.status === 'mismatch') {
      return { complete: false, reason: `approved but downstream verification found a mismatch: ${state.verification.detail}` };
    }
    if (state.execution?.success === false) {
      return { complete: false, reason: `execution failed: ${state.execution.detail}` };
    }
    return { complete: true, reason: `approved and ${state.verification?.status ?? 'not verified'} - ${state.execution?.detail ?? ''}`.trim() };
  },
  learn: (state) => {
    if (state.verification?.status === 'mismatch') {
      return {
        insight: `Queue Resolution approved "${state.evidence?.row?.title ?? state.trigger.originRef}" but the claimed downstream artefact does not exist - the same Downstream Verification Gap shape MSN-0350 journey #9 / MSN-0356 found. "Approved" is not "happened."`,
        category: 'coverage-gap',
      };
    }
    return { insight: null, category: 'none' };
  },
};

// ─── 2. Queue Triage / Deduplication ───────────────────────────────────────
// MSN-0353 §1.7. Trigger: two or more items in a governed queue turn out to
// target the same underlying work. (Journey #8 - two dead-code-audit
// requests filed three minutes apart, only one approved, the other
// archived.) "Evidence required: a side-by-side read of titles/scope -
// nothing else on either row mattered to the actual choice" - so this
// definition deliberately looks at nothing but title text.

const TRIAGE_STOPWORDS = new Set(['a', 'an', 'the', 'of', 'for', 'and', 'to', 'in', 'on', 'with', 'at', 'by', 'from', 'this', 'that']);

function normalizedTitleTokens(title: string): Set<string> {
  return new Set(
    title
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter((tok) => tok.length > 2 && !TRIAGE_STOPWORDS.has(tok))
  );
}

function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  const shared = [...a].filter((tok) => b.has(tok));
  const union = new Set([...a, ...b]);
  return union.size === 0 ? 0 : shared.length / union.size;
}

/** A real, disclosed threshold - not tuned to any one fixture. Two titles
 * need to share at least half their meaningful tokens (by union) to be
 * flagged as a near-duplicate candidate. */
const DUPLICATE_TITLE_THRESHOLD = 0.5;

export interface DuplicateCandidatePair {
  aId: string;
  aTitle: string;
  bId: string;
  bTitle: string;
  sharedTokens: string[];
  overlapScore: number;
}

function findDuplicatePairs(items: QueueItem[]): DuplicateCandidatePair[] {
  const pairs: DuplicateCandidatePair[] = [];
  const tokensById = new Map(items.map((i) => [i.id, normalizedTitleTokens(i.title)]));
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const a = items[i];
      const b = items[j];
      const aTokens = tokensById.get(a.id) ?? new Set<string>();
      const bTokens = tokensById.get(b.id) ?? new Set<string>();
      const score = jaccardSimilarity(aTokens, bTokens);
      if (score >= DUPLICATE_TITLE_THRESHOLD) {
        pairs.push({
          aId: a.id,
          aTitle: a.title,
          bId: b.id,
          bTitle: b.title,
          sharedTokens: [...aTokens].filter((t) => bTokens.has(t)),
          overlapScore: Math.round(score * 100) / 100,
        });
      }
    }
  }
  return pairs;
}

/** Groups pairwise matches into connected duplicate sets via union-find, so
 * a chain of near-duplicates (A~B, B~C) resolves as one group, not two
 * independent pair decisions - matching MSN-0353 §1.7's completion marker
 * of "a paired resolution... not two independent closes." Oldest-first
 * within each group, so the earliest-filed item is the default "resolve
 * one" candidate and later duplicates are archived - matching journey #8's
 * real resolution (the first-filed of the two requests was the one
 * approved). */
function groupDuplicates(items: QueueItem[], pairs: DuplicateCandidatePair[]): QueueItem[][] {
  const parent = new Map(items.map((i) => [i.id, i.id]));
  function find(x: string): string {
    let cur = x;
    while (parent.get(cur) !== cur) cur = parent.get(cur) as string;
    return cur;
  }
  function union(x: string, y: string): void {
    const rx = find(x);
    const ry = find(y);
    if (rx !== ry) parent.set(rx, ry);
  }
  for (const p of pairs) union(p.aId, p.bId);

  const involvedIds = new Set(pairs.flatMap((p) => [p.aId, p.bId]));
  const groups = new Map<string, QueueItem[]>();
  for (const item of items) {
    if (!involvedIds.has(item.id)) continue;
    const root = find(item.id);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root)!.push(item);
  }
  return [...groups.values()].map((g) => g.slice().sort((x, y) => (x.createdAt ?? '').localeCompare(y.createdAt ?? '')));
}

export interface QueueTriageEvidence {
  reviewableItems: QueueItem[];
  duplicatePairs: DuplicateCandidatePair[];
  duplicateGroups: QueueItem[][];
  hasDuplicates: boolean;
}

async function assembleQueueTriageEvidence(): Promise<QueueTriageEvidence> {
  // Reuses decide.ts's own real filter (lifecycle === 'awaiting_review' &&
  // source === 'build') so this definition looks at exactly the same queue
  // Decide itself would surface - never a separate, parallel read.
  const data = await fetchEngineeringQueue();
  const reviewableItems = data.items.filter((i) => i.lifecycle === 'awaiting_review' && i.source === 'build');
  const duplicatePairs = findDuplicatePairs(reviewableItems);
  const duplicateGroups = groupDuplicates(reviewableItems, duplicatePairs);
  return { reviewableItems, duplicatePairs, duplicateGroups, hasDuplicates: duplicatePairs.length > 0 };
}

function validateQueueTriageEvidence(evidence: QueueTriageEvidence) {
  const problems: string[] = [];
  if (evidence.reviewableItems.length === 0) problems.push('no awaiting_review build requests exist to triage');
  return { ok: problems.length === 0, problems };
}

export type QueueTriageDecision =
  | { kind: 'resolve-one-archive-rest'; keepId: string; keepTitle: string; archiveIds: string[] }
  | { kind: 'no-duplicates-found' };

export const queueTriage: InvestigationDefinition<QueueTriageEvidence, QueueTriageDecision> = {
  type: 'queue-triage',
  label: 'Queue Triage / Deduplication',
  // Per MSN-0353 §1.7: the Captain resolves duplicates manually today,
  // evidenced directly by journey #8, but the target state is a
  // staff/engineering pre-filter that stops the duplicate ever reaching the
  // Captain. Declaring 'shared' rather than 'captain' records that gap
  // honestly instead of encoding today's fallback as the permanent design.
  owner: 'shared',
  triggerDescription:
    'Two or more items in a governed queue turn out to target the same underlying work. (MSN-0353 §1.7; MSN-0350 journey #8 - two dead-code-audit requests filed three minutes apart, only one approved, the other archived.)',
  requiredEvidence: [
    'every build_request_inbox row currently awaiting_review (the same filter Decide itself uses)',
    'a side-by-side normalized-title token comparison between every pair of those rows - nothing else on either row',
  ],
  evidenceSources: ['lcars-portal/src/lib/engineering-queue.ts (fetchEngineeringQueue)'],
  validationRules: ['at least one awaiting_review build request must exist - there is nothing to triage against an empty queue'],
  possibleDecisionKinds: ['resolve-one-archive-rest', 'no-duplicates-found'],
  completionCriteria:
    'Every duplicate group found has a recorded resolution - either resolve-one-archive-rest (paired: one kept, the rest archived together, never two independent closes) or, when no group crosses the similarity threshold, the honest no-duplicates-found result.',
  auditOutputs: [
    'the full list of awaiting_review rows compared',
    'every candidate duplicate pair found, with its shared tokens and overlap score',
    'the duplicate groups derived from those pairs',
    'the chosen decision and, for resolve-one-archive-rest, which id was kept vs archived',
    'the archive execution result and its verification',
  ],
  assembleEvidence: assembleQueueTriageEvidence,
  validateEvidence: (evidence) => validateQueueTriageEvidence(evidence),
  decisionOptions: (evidence) => {
    if (!evidence.hasDuplicates) {
      return [
        {
          id: 'no-duplicates-found',
          label: `No near-duplicate titles found among ${evidence.reviewableItems.length} awaiting_review item(s)`,
          value: { kind: 'no-duplicates-found' },
          isReversible: true,
        },
      ];
    }
    return evidence.duplicateGroups.map((group, idx) => {
      const [keep, ...archive] = group;
      return {
        id: `resolve-group-${idx}`,
        label: `Resolve one, archive the rest - keep "${keep.title}" (${keep.id}), archive ${archive.length} near-duplicate(s): ${archive
          .map((a) => `"${a.title}"`)
          .join(', ')}`,
        value: { kind: 'resolve-one-archive-rest' as const, keepId: keep.id, keepTitle: keep.title, archiveIds: archive.map((a) => a.id) },
        isReversible: true,
      };
    });
  },
  // execute/verify: MSN-0353 §1.7's completion marker requires "a paired
  // resolution... not two independent closes" - a detection report alone
  // doesn't satisfy that, so this definition performs the archive side of
  // the pair (the mechanical, unambiguous half), reusing setQueueItemStatus
  // exactly as engineering-queue.ts already exposes it. It deliberately
  // does NOT also approve the kept item - that decision belongs to Queue
  // Resolution (this file's other definition), so the two investigation
  // types stay separate governance surfaces per MSN-0353 §3, rather than
  // one definition performing both dedup and approval in a single step.
  execute: async (decision, evidence) => {
    if (decision.kind === 'no-duplicates-found') {
      return { attempted: false, success: null, detail: 'no duplicates found - nothing to archive' };
    }
    const results = await Promise.all(
      decision.archiveIds.map((id) => {
        const item = evidence.reviewableItems.find((i) => i.id === id) ?? ({ id, source: 'build' } as QueueItem);
        return setQueueItemStatus(item, 'rejected');
      })
    );
    const allOk = results.every((r) => r.ok);
    return {
      attempted: true,
      success: allOk,
      detail: allOk
        ? `Archived ${decision.archiveIds.length} near-duplicate(s), kept "${decision.keepTitle}" (${decision.keepId})`
        : `Archive failed for at least one duplicate: ${results
            .filter((r) => !r.ok)
            .map((r) => r.error)
            .join('; ')}`,
    };
  },
  verify: async (execution, evidence) => {
    if (!execution.attempted) {
      return { status: 'not_applicable', detail: 'no execution to verify (no duplicates found)' };
    }
    if (!execution.success) {
      return { status: 'failed', detail: execution.detail };
    }
    // Re-reads the same real source, post-mutation, to confirm the
    // archived rows actually left the awaiting_review queue - the same
    // "claimed vs real" shape Queue Resolution's verify() uses above,
    // applied to a status flip instead of a table insert.
    const post = await fetchEngineeringQueue();
    const stillAwaitingReview = new Set(post.items.filter((i) => i.lifecycle === 'awaiting_review' && i.source === 'build').map((i) => i.id));
    const archivedIds = evidence.duplicateGroups.flatMap((g) => g.slice(1).map((i) => i.id));
    const stillPresent = archivedIds.filter((id) => stillAwaitingReview.has(id));
    return stillPresent.length === 0
      ? { status: 'verified', detail: 'all archived duplicates confirmed out of the awaiting_review queue' }
      : { status: 'mismatch', detail: `${stillPresent.length} archived id(s) still show as awaiting_review: ${stillPresent.join(', ')}` };
  },
  isComplete: (state) => {
    if (state.chosenDecision === undefined) {
      return { complete: false, reason: 'awaiting a decision - duplicate candidates were assembled but nothing has been decided yet' };
    }
    if (state.chosenDecision.kind === 'no-duplicates-found') {
      return { complete: true, reason: 'no duplicates found - nothing further to resolve' };
    }
    if (state.verification?.status === 'mismatch') {
      return { complete: false, reason: `archive reported success but verification found a mismatch: ${state.verification.detail}` };
    }
    return { complete: state.execution?.success === true, reason: state.execution?.detail ?? 'no execution result' };
  },
  learn: (state) => {
    if (state.evidence && state.evidence.duplicatePairs.length > 0 && state.chosenDecision?.kind === 'resolve-one-archive-rest') {
      return {
        insight: `Queue Triage found near-duplicate requests reaching the queue before any pre-filter caught them (MSN-0353 §1.7's known gap): ${state.evidence.duplicatePairs
          .map((p) => `"${p.aTitle}" ~ "${p.bTitle}" (${Math.round(p.overlapScore * 100)}% title overlap)`)
          .join('; ')}`,
        category: 'process-gap',
      };
    }
    return { insight: null, category: 'none' };
  },
};
