/**
 * MSN-0357 — Investigation Coverage Matrix.
 *
 * Maps all 22 journeys reconstructed in docs/MSN-0350-INVESTIGATION-JOURNEYS.md
 * to the investigation type MSN-0353 §1 assigned them, and actually runs
 * each one through the real, shared engine (lib/investigationEngine.ts) —
 * this is the evidence for MSN-0357's success criterion, not an assertion of
 * it. Every `run()` below calls the SAME two functions
 * (`openInvestigation`/`resolveInvestigation`) regardless of type; nothing
 * here branches on investigation type either — the per-journey difference is
 * entirely in which real `InvestigationDefinition` and `TriggerContext` are
 * passed in.
 *
 * Correction found while building this matrix, disclosed rather than
 * silently fixed: journey #6 ("Mission Detail's ungoverned status editor")
 * was never assigned a type in docs/MSN-0353-INVESTIGATION-ARCHITECTURE.md
 * §1's own table (an omission — the table lists 21 journey numbers, not 22).
 * It is structurally an Integrity Audit — diagnose case (comparing what a
 * server route enforces against what the client actually exposed), the same
 * shape as journeys #1/#2/#4/#13/#14, and is classified as such here.
 *
 * Safety note: several types' `execute` performs a real mutation
 * (queueResolution can create a mission; queueTriage can archive a queue
 * row). Every journey below that reaches a decision uses only the
 * non-mutating branch of that type's decision space (hold / no-duplicates-
 * found / a read-only re-check) — this file never writes to production data
 * on the Captain's behalf. Where live current data doesn't allow the
 * "happy path" (e.g. the queue is currently empty), that is disclosed in
 * the entry's `limitations` field rather than faked.
 */

import {
  openInvestigation,
  resolveInvestigation,
  type InvestigationDefinition,
  type InvestigationRunState,
  type TriggerContext,
} from '@/lib/investigationEngine';
import {
  integrityAuditDiagnose,
  integrityAuditVerify,
  redundancyReconciliation,
  upstreamCoverageGap,
  downstreamVerificationGap,
  queueResolution,
  queueTriage,
  trendScan,
  noiseTriage,
  decisionTraceback,
} from './registry';

export interface JourneyCoverageEntry {
  journey: number;
  title: string;
  typeId: string;
  typeLabel: string;
  configUsed: string;
  limitations: string | null;
  definition: InvestigationDefinition<any, any>;
  trigger: TriggerContext;
  /** Which decision (if any) to resolve with — chosen for safety (never a real mutation) per the file header note above. */
  pickDecision: (options: { id: string; value: unknown }[]) => unknown;
}

const now = '2026-07-09T20:00:00.000Z';

function firstOption(options: { id: string; value: unknown }[]): unknown {
  return options[0]?.value;
}

export const JOURNEY_COVERAGE: JourneyCoverageEntry[] = [
  // ── Missions & Engineering (Integrity Audit / Redundancy) ──────────────
  {
    journey: 1,
    title: 'The Notebook "Approve Route" that never created a mission',
    typeId: 'integrity-audit-diagnose',
    typeLabel: 'Integrity Audit — diagnose',
    configUsed: 'general registry-vs-nominator diagnose check, framed with this journey\'s own trigger reason',
    limitations: 'The built check is the real, generalizable claim-vs-reality comparison (registry vs. live NOMINATORS) — it does not re-derive the specific captains-notebook route-mapping bug journey #1 found by hand; that was a one-off historical diagnosis, not a standing evaluator.',
    definition: integrityAuditDiagnose,
    trigger: { investigationType: 'integrity-audit-diagnose', reason: 'MSN-0334 workflow audit: does the Notebook "Approve Route" button actually create what it claims to create?', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 2,
    title: 'Mission lifecycle transitions silently never written',
    typeId: 'integrity-audit-diagnose',
    typeLabel: 'Integrity Audit — diagnose',
    configUsed: 'general registry-vs-nominator diagnose check, framed with this journey\'s own trigger reason',
    limitations: 'Same as journey #1: represents the TYPE, not a re-derivation of the specific NOT-NULL constraint bug this journey originally found.',
    definition: integrityAuditDiagnose,
    trigger: { investigationType: 'integrity-audit-diagnose', reason: 'Schema-conformance review: do mission_state_transitions inserts actually satisfy the live table\'s NOT NULL constraints?', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 3,
    title: 'Two blocked-mission alert engines that disagreed',
    typeId: 'redundancy-reconciliation',
    typeLabel: 'Redundancy Reconciliation',
    configUsed: 'full-registry scope (trigger.originRef unset) — real pairwise evidenceSource comparison across every interrupt-capable registry entry',
    limitations: null,
    definition: redundancyReconciliation,
    trigger: { investigationType: 'redundancy-reconciliation', reason: 'Audit finding: two independently maintained urgent-alert engines with different thresholds, visible only depending which page you\'re on.', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 4,
    title: 'The mission detail page\'s fake fallback',
    typeId: 'integrity-audit-diagnose',
    typeLabel: 'Integrity Audit — diagnose',
    configUsed: 'general registry-vs-nominator diagnose check, framed with this journey\'s own trigger reason',
    limitations: 'Represents the TYPE (claimed vs. real behaviour), not the specific mock-fallback removal MSN-0351 already performed.',
    definition: integrityAuditDiagnose,
    trigger: { investigationType: 'integrity-audit-diagnose', reason: 'MSN-0350 Phase A Trust Audit: does /missions/[id] distinguish a genuine load failure from "no missions", or silently fall back to mock data?', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 5,
    title: 'One mission, four ID schemes',
    typeId: 'redundancy-reconciliation',
    typeLabel: 'Redundancy Reconciliation',
    configUsed: 'full-registry scope — real pairwise evidenceSource comparison',
    limitations: 'The built comparator reads INTERRUPT_COVERAGE_REGISTRY\'s evidenceSource tokens; the original journey compared four separate ID-minting CODE PATHS (portal/Slack-bot/Python registry/id-registry), a different real target within the same Redundancy Reconciliation type shape.',
    definition: redundancyReconciliation,
    trigger: { investigationType: 'redundancy-reconciliation', reason: 'MSN-0064 closure: four independent mission-ID minting code paths found across the portal, Slack bot, and Python mission registry.', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 6,
    title: 'Mission Detail\'s ungoverned status editor',
    typeId: 'integrity-audit-diagnose',
    typeLabel: 'Integrity Audit — diagnose',
    configUsed: 'general registry-vs-nominator diagnose check, framed with this journey\'s own trigger reason',
    limitations: 'CORRECTION: docs/MSN-0353-INVESTIGATION-ARCHITECTURE.md §1\'s table never assigned journey #6 a type — an omission found while building this matrix, not a pre-existing decision. Classified here as Integrity Audit — diagnose (comparing what the approve/reject routes enforce against what the client UI exposed), the same shape as #1/#2/#4/#13/#14.',
    definition: integrityAuditDiagnose,
    trigger: { investigationType: 'integrity-audit-diagnose', reason: 'MSN-0321 command-surface review: does /missions/[id]\'s free-form status editor bypass the eligibility gate the approve/reject routes already enforce?', originatedAt: now },
    pickDecision: firstOption,
  },

  // ── Decide / governance (Queue Resolution / Triage) ─────────────────────
  {
    journey: 7,
    title: 'The two-decision thread that closed the MSN-0064 identity fork',
    typeId: 'queue-resolution',
    typeLabel: 'Queue Resolution',
    configUsed: 'the real, historical build_request_inbox row 8b122836-c19a-4f7c-9abb-b889c925b473',
    limitations: 'This demonstration environment has no SUPABASE_SERVICE_ROLE_KEY configured, so the fetchSingleRow(supabaseAdmin()) call fails closed with a structured fetchError, blocking cleanly at evidence_validation — a real, honest fail-closed result, not the row\'s actual current status (which is separately confirmed live via SQL to be status=approved, i.e. already resolved and not awaiting_review either way). The approve/hold happy path for this type is independently verified against real data fixtures in lib/__tests__/queueGovernance.test.ts.',
    definition: queueResolution,
    trigger: { investigationType: 'queue-resolution', reason: 'Re-checking the real MSN-0064 ADR/staging-plan approval thread.', originatedAt: now, originRef: '8b122836-c19a-4f7c-9abb-b889c925b473' },
    pickDecision: () => 'hold',
  },
  // CORRECTED after first live run: journeys #7, #9, #10, #11 all use
  // supabaseAdmin()/createSupabaseServiceRoleClient(), which throws when
  // SUPABASE_SERVICE_ROLE_KEY is unset (lib/supabase-service-role.ts:22-26)
  // - confirmed by reading that file directly, not inferred. This local test
  // environment has no service-role credentials configured (a deliberate
  // choice - that key is full-admin/RLS-bypassing and isn't something to
  // source into a demonstration run). The block these four journeys show
  // below is a real, honest fail-closed result from a genuine fetch error,
  // not the "already resolved" explanation an earlier draft of this file
  // incorrectly assumed before checking. The positive finding this still
  // proves: assembleEvidence's try/catch converted the thrown credentials
  // error into a structured fetchError rather than crashing or silently
  // proceeding with empty data, and validateEvidence correctly blocked on
  // it - the engine's fail-closed discipline held under a real infra
  // failure. The "row found, decision offered" happy path for these two
  // types is independently verified against real data fixtures in
  // lib/__tests__/queueGovernance.test.ts (19 tests) and
  // lib/__tests__/coverageGaps.test.ts (25 tests).
  {
    journey: 8,
    title: 'Two near-duplicate dead-code audits, three minutes apart',
    typeId: 'queue-triage',
    typeLabel: 'Queue Triage / Deduplication',
    configUsed: 'real, current awaiting_review build_request_inbox rows (confirmed empty at demonstration time)',
    limitations: 'The live build_request_inbox queue is currently empty (0 awaiting_review rows) — this run demonstrates the honest "nothing to triage" validation-block path against real current data. The full detect→archive→verify lifecycle for an actual duplicate pair is separately regression-tested with real historical titles in lib/__tests__/queueGovernance.test.ts, since re-running it live here would require either fabricating queue rows or archiving real ones.',
    definition: queueTriage,
    trigger: { investigationType: 'queue-triage', reason: 'Routine queue triage pass.', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 9,
    title: 'An approval whose creation never materialized',
    typeId: 'downstream-verification-gap',
    typeLabel: 'Downstream Verification Gap',
    configUsed: 'spot-check on the real row ca83a08b-cab5-4adf-8e33-f68713e31aa5 (trigger.originRef) — execute/verify are read-only re-checks, safe to run for real',
    limitations: 'This demonstration environment has no SUPABASE_SERVICE_ROLE_KEY configured, so recheckRows()\'s createSupabaseServiceRoleClient() call fails closed with a structured fetchError, blocking cleanly at evidence_validation. The real not_found_downstream verdict for this exact row is independently confirmed live in docs/MSN-0356-DECIDE-OUTCOME-VERIFICATION-GAP.md and regression-tested with a frozen fixture of this row in lib/__tests__/coverageGaps.test.ts.',
    definition: downstreamVerificationGap,
    trigger: { investigationType: 'downstream-verification-gap', reason: 'Did the approved "Spawn XO and Chief Engineer Authority" proposal (working title USS-TJR-MSN-0066) actually create a mission?', originatedAt: now, originRef: 'ca83a08b-cab5-4adf-8e33-f68713e31aa5' },
    pickDecision: firstOption,
  },
  {
    journey: 10,
    title: 'A build request with nothing to decide',
    typeId: 'queue-resolution',
    typeLabel: 'Queue Resolution',
    configUsed: 'the real, historical build_request_inbox row 51283b2c-b580-4f04-8a05-716fbf91bcb5 (status=archived)',
    limitations: 'This demonstration environment has no SUPABASE_SERVICE_ROLE_KEY configured, so this also blocks on a structured fetchError rather than reaching decision_options — the row\'s real status (archived, never awaiting_review) would have blocked it for the same reason regardless, since journey #10\'s own point was that this request never had anything to decide.',
    definition: queueResolution,
    trigger: { investigationType: 'queue-resolution', reason: 'Re-checking the real empty/malformed build request from journey #10.', originatedAt: now, originRef: '51283b2c-b580-4f04-8a05-716fbf91bcb5' },
    pickDecision: () => 'hold',
  },
  {
    journey: 11,
    title: 'Approving an AI-proposed mission through the governed path',
    typeId: 'queue-resolution',
    typeLabel: 'Queue Resolution',
    configUsed: 'a nonexistent id, since no live governed (action_type-set) row currently exists to spot-check',
    limitations: 'Doubly fail-closed: this journey is (reconstructed) in docs/MSN-0350-INVESTIGATION-JOURNEYS.md itself (no real row of this shape exists yet, live or historical), and this environment also has no SUPABASE_SERVICE_ROLE_KEY configured. Either alone would block this run at evidence_validation; the execute/verify machinery for a real governed row is regression-tested with mocked fixtures in lib/__tests__/queueGovernance.test.ts.',
    definition: queueResolution,
    trigger: { investigationType: 'queue-resolution', reason: 'Approving a hypothetical AI-proposed create_mission action through the MSN-0352 governed path.', originatedAt: now, originRef: '00000000-0000-0000-0000-000000000000' },
    pickDecision: () => 'hold',
  },

  // ── Health & Readiness (Trend Scan, represented via its built instance) ─
  {
    journey: 12,
    title: 'The Bali travel-prep pain spike',
    typeId: 'trend-scan',
    typeLabel: 'Trend Scan',
    configUsed: 'the built trendScan instance (real intelligence_briefs window), not a health-domain instance',
    limitations: 'DISCLOSED GAP: this journey\'s original evidence was health-domain (captains_log_entries/health_events pain trajectory), but the Trend Scan definition built in this mission wires only the intelligence_briefs instance (journey #18\'s real shape). The engine\'s lifecycle is fully generic and would run a health-domain trendScan variant with zero changes to lib/investigationEngine.ts — but that variant was not built in this pass. Represents the TYPE, not this specific journey\'s original data source.',
    definition: trendScan,
    trigger: { investigationType: 'trend-scan', reason: 'End-of-week trend read (represented via the built intelligence_briefs instance, not the original health-domain evidence).', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 13,
    title: 'Fixing the escalation detector\'s negation blind spot',
    typeId: 'integrity-audit-diagnose',
    typeLabel: 'Integrity Audit — diagnose',
    configUsed: 'general registry-vs-nominator diagnose check, framed with this journey\'s own trigger reason',
    limitations: 'Represents the TYPE, not a re-derivation of the specific negation-regex bug MSN-0351 already fixed.',
    definition: integrityAuditDiagnose,
    trigger: { investigationType: 'integrity-audit-diagnose', reason: 'MSN-0351 audit: does scanEscalation() correctly handle negated red-flag phrases ("no chest pain") and honest fetch failures?', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 14,
    title: 'Removing fabricated Recovery Brief content',
    typeId: 'integrity-audit-diagnose',
    typeLabel: 'Integrity Audit — diagnose',
    configUsed: 'general registry-vs-nominator diagnose check, framed with this journey\'s own trigger reason',
    limitations: 'Represents the TYPE, not a re-derivation of the specific fabricated-field audit MSN-0351 already performed.',
    definition: integrityAuditDiagnose,
    trigger: { investigationType: 'integrity-audit-diagnose', reason: 'MSN-0351 audit: does /recovery-brief\'s "● Live" badge genuinely reflect every field it\'s displayed next to?', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 15,
    title: 'A recovery signal captured but never scored',
    typeId: 'upstream-coverage-gap',
    typeLabel: 'Upstream Coverage Gap',
    configUsed: 'general registry-vs-live-NOMINATORS check — the real mechanism now closed by MSN-0355',
    limitations: null,
    definition: upstreamCoverageGap,
    trigger: { investigationType: 'upstream-coverage-gap', reason: 'Re-confirming recovery_pulses.nervous_system now reaches an evaluator, per MSN-0355.', originatedAt: now },
    pickDecision: firstOption,
  },

  // ── Intelligence & Knowledge ─────────────────────────────────────────
  {
    journey: 16,
    title: 'Signal noise triage (banking_relevance classifier)',
    typeId: 'noise-triage',
    typeLabel: 'Noise Triage',
    configUsed: 'the real, live intelligence_events table, real deriveRisk() from lib/intelligenceRisk.ts',
    limitations: null,
    definition: noiseTriage,
    trigger: { investigationType: 'noise-triage', reason: 'Scanning recent intelligence_events for banking_relevance-only HIGH badges worth discounting.', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 17,
    title: 'Confirming a risk-filter fix actually landed',
    typeId: 'integrity-audit-verify',
    typeLabel: 'Integrity Audit — verify',
    configUsed: 'general registry-vs-nominator verify check, re-check framed via trigger.originRef',
    limitations: 'Represents the TYPE (re-confirmation of a specific prior fix), not a re-derivation of the intelligence risk-filter fix\'s own original SQL row-count check.',
    definition: integrityAuditVerify,
    trigger: { investigationType: 'integrity-audit-verify', reason: 'Re-confirming the intelligence risk-filter fix still holds.', originatedAt: now, originRef: 'intelligence-risk-filter-fix' },
    pickDecision: firstOption,
  },
  {
    journey: 18,
    title: 'Weekly ORI brief risk-trend scan',
    typeId: 'trend-scan',
    typeLabel: 'Trend Scan',
    configUsed: 'the real, live intelligence_briefs table, last 5 rows, chronological order — this journey\'s own real, cited data source',
    limitations: null,
    definition: trendScan,
    trigger: { investigationType: 'trend-scan', reason: 'End-of-week review: is operational-resilience risk trending up or down over the last month?', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 19,
    title: 'Retracing an architecture decision before repeating a pattern',
    typeId: 'decision-traceback',
    typeLabel: 'Decision Traceback',
    configUsed: 'the real, live architecture_records table, real search terms extracted from trigger.reason',
    limitations: null,
    definition: decisionTraceback,
    trigger: { investigationType: 'decision-traceback', reason: 'Checking whether a vector database decision already exists before repeating the debate for Command Memory storage.', originatedAt: now },
    pickDecision: firstOption,
  },

  // ── The Home boundary ────────────────────────────────────────────────
  {
    journey: 20,
    title: 'A RED brief spike with a working path to Home',
    typeId: 'noise-triage',
    typeLabel: 'Noise Triage',
    configUsed: 'the built noiseTriage instance (real intelligence_events banking_relevance pattern), not a Home-interrupt-specific instance',
    limitations: 'DISCLOSED GAP: this journey is about the Home boundary\'s RED-brief nomination specifically (interruptAssembly.ts\'s intelligenceBriefNominator), not the intelligence_events banking_relevance pattern journey #16 found. MSN-0353 §1.9 groups both under Noise Triage by trigger-shape ("scanning to discount"), but the Phase 2 build wired only the #16 instance. Represents the TYPE, not this journey\'s original evidence source.',
    definition: noiseTriage,
    trigger: { investigationType: 'noise-triage', reason: 'Checking a RED intelligence brief spike surfaced at Home (represented via the built intelligence_events instance).', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 21,
    title: 'Quiet Home, checked anyway',
    typeId: 'noise-triage',
    typeLabel: 'Noise Triage',
    configUsed: 'the built noiseTriage instance (real intelligence_events banking_relevance pattern), not a Home-interrupt-specific instance',
    limitations: 'Same disclosed gap as journey #20: represents the TYPE, not the original inferred-relevance-score evidence this journey actually cites.',
    definition: noiseTriage,
    trigger: { investigationType: 'noise-triage', reason: 'A quiet Home visit surfaced a non-operational item under "Worth knowing" — checking whether it\'s real (represented via the built intelligence_events instance).', originatedAt: now },
    pickDecision: firstOption,
  },
  {
    journey: 22,
    title: 'A confirmed interrupt-boundary gap (the invisible P0 mission)',
    typeId: 'upstream-coverage-gap',
    typeLabel: 'Upstream Coverage Gap',
    configUsed: 'general registry-vs-live-NOMINATORS check — the real mechanism now closed by MSN-0354\'s missionNominator',
    limitations: null,
    definition: upstreamCoverageGap,
    trigger: { investigationType: 'upstream-coverage-gap', reason: 'Re-confirming a stale, high-priority mission now reaches an Interrupt Assembly nominator, per MSN-0354.', originatedAt: now },
    pickDecision: firstOption,
  },
];

export interface JourneyMatrixRow {
  journey: number;
  title: string;
  typeLabel: string;
  engineExecuted: boolean;
  stagesReached: string[];
  noBranchingRequired: true;
  validationOk: boolean;
  completion: { complete: boolean; reason: string } | null;
  configUsed: string;
  limitations: string | null;
  error: string | null;
}

/** Runs every journey in JOURNEY_COVERAGE through the real, shared engine and
 * returns one matrix row per journey. `noBranchingRequired` is a structural
 * constant (true for every row) — proven once, for the whole engine, by
 * source inspection (lib/__tests__/investigationJourneyCoverage.test.ts
 * asserts investigationEngine.ts's source contains no `definition.type`
 * branch), not re-proven per journey — a single shared control-flow path
 * either branches on type or it doesn't; it cannot branch for some journeys
 * and not others. */
export async function buildCoverageMatrix(): Promise<JourneyMatrixRow[]> {
  const rows: JourneyMatrixRow[] = [];
  for (const entry of JOURNEY_COVERAGE) {
    try {
      const opened: InvestigationRunState<unknown, unknown> = await openInvestigation(entry.definition, entry.trigger);
      let final = opened;
      if (opened.validation?.ok && opened.decisionOptions) {
        const decision = entry.pickDecision(opened.decisionOptions as { id: string; value: unknown }[]);
        final = await resolveInvestigation(opened, decision);
      }
      rows.push({
        journey: entry.journey,
        title: entry.title,
        typeLabel: entry.typeLabel,
        engineExecuted: true,
        stagesReached: final.stagesReached,
        noBranchingRequired: true,
        validationOk: opened.validation?.ok ?? false,
        completion: final.completion ?? null,
        configUsed: entry.configUsed,
        limitations: entry.limitations,
        error: null,
      });
    } catch (err) {
      rows.push({
        journey: entry.journey,
        title: entry.title,
        typeLabel: entry.typeLabel,
        engineExecuted: false,
        stagesReached: [],
        noBranchingRequired: true,
        validationOk: false,
        completion: null,
        configUsed: entry.configUsed,
        limitations: entry.limitations,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }
  return rows;
}
