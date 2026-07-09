/**
 * MSN-0351 Objective 3 — Interrupt Coverage Contract.
 *
 * Every Workbench capability that touches operationally significant data
 * declares, here, whether it can ever justify interrupting the Captain, and
 * exactly how. This is the registry MSN-0350 Phase A recommended: a single
 * place where a gap in coverage is a visible, declared fact — never a silent
 * assumption. `validateCoverage()` below is the enforcement mechanism: it
 * fails loudly if a capability is missing, or if its declared state is
 * internally inconsistent (e.g. claims a server evaluator with none named).
 *
 * Honesty note on scope: this registry DECLARES current evaluation state -
 * it does not, by itself, add new server-side schedulers for every
 * capability. Where `evaluationMethod` is 'client-render-only' or 'none',
 * that is a real, disclosed gap (per MSN-0350 Phase A: today almost every
 * capability only evaluates its condition when a human happens to open that
 * page). Closing every one of those gaps with real scheduled infrastructure
 * is future work - MSN-0351 makes the gaps visible and stops the silent
 * failure modes around them; it does not yet build a scheduler for each.
 * The one exception is the Captain's Brief, which already has a real
 * scheduler-independent evaluator (recomputed per request by a Python
 * pipeline with a genuine risk threshold) - see its entry below.
 */

export type EvaluationMethod = 'server-scheduled' | 'server-on-demand' | 'client-render-only' | 'none';

export interface InterruptContractEntry {
  /** Stable id, matches the Workbench capability this entry covers. */
  capability: string;
  /** Human-readable capability name, matches docs/MSN-0350-* naming. */
  label: string;
  canInterrupt: 'yes' | 'no' | 'conditional';
  /** Under what real, observable condition would this justify an interrupt. */
  conditions: string;
  /** Where the evidence for a nomination comes from (real table/field names). */
  evidenceSource: string;
  evaluationMethod: EvaluationMethod;
  /** What stops this from crying wolf. */
  falsePositiveGuard: string;
  /** What happens, today, if the underlying data source is unreachable. */
  degradationBehaviour: string;
  /**
   * True only if MSN-0351 confirmed this capability's degradation path is
   * now honest (a genuine failure is visibly distinct from "checked, clear").
   * False means the false-calm gap is still open for this capability.
   */
  degradationIsHonest: boolean;
  /** Non-null only when evaluationMethod is not 'none' and canInterrupt is not 'no'. */
  knownGap: string | null;
}

export const INTERRUPT_COVERAGE_REGISTRY: InterruptContractEntry[] = [
  {
    capability: 'human-systems-redflag',
    label: 'Human Systems / Medical — clinical red flag',
    canInterrupt: 'yes',
    conditions:
      'Free-text health notes match a red-flag pattern (suicidal ideation/self-harm, chest pain/breathing difficulty, new neuro symptoms, fever/infection) and the match is not negated.',
    evidenceSource: 'human_systems_daily.notes, recovery_pulses.notes',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard:
      'MSN-0351: negation-aware matching (isNegated()) — "no chest pain"/"denies suicidal ideation" no longer fire.',
    degradationBehaviour:
      'MSN-0351: an explicit escalationCheckFailed state renders a distinct "could not check" banner on both /human-systems and /medical, instead of silently returning null.',
    degradationIsHonest: true,
    knownGap:
      'Still evaluated only when a human opens /human-systems or /medical - no server-side scheduled evaluator exists yet. This is the single highest-priority follow-up given it is the highest-stakes interrupt candidate in the product.',
  },
  {
    capability: 'human-systems-recovery-debt',
    label: 'Human Systems — sustained recovery debt',
    canInterrupt: 'conditional',
    conditions: '3 consecutive days at overallBand limited/depleted AND mean sleep_hours < 6.',
    evidenceSource: 'human_systems_daily (sleep_hours, energy, nervous_system_state, mood, pain_score)',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'Real two-condition sustained-trend gate (recoveryDebt()) - not a single bad day.',
    degradationBehaviour: 'Degrades to a neutral "moderate/no data" snapshot on fetch failure - not yet distinguished from a genuine clear reading.',
    degradationIsHonest: false,
    knownGap: 'No dedicated failure-state was added for this specific signal in MSN-0351 (the red-flag failure state covers the same page load, but recoveryDebt itself does not separately declare failure vs. clear).',
  },
  {
    capability: 'medical-emotional-load',
    label: 'Medical — Emotional Load Flag',
    canInterrupt: 'conditional',
    conditions: 'Worst-of-day nervous-system state in {activated, dysregulated} on 3+ of any 7 recorded days.',
    evidenceSource:
      "MSN-0355: merged analytics_health_daily.nervous_system_state AND recovery_pulses (real nervous_system column, falling back to the stress-derived heuristic only when null) - analytics_health_daily's underlying source tables (captains_log_entries, health_daily_logs) stopped receiving rows after 2026-06-28 when the daily check-in habit moved to recovery_pulses; the view itself is not broken, so both sources are now merged per day rather than switching exclusively to one.",
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'Real 3-of-7 threshold over RECORDED days only (fetchEmotionalLoadFlag) - a day with no signal from either source is not counted as calm.',
    degradationBehaviour:
      'MSN-0355: an explicit noRecentData state (EmotionalLoadFlag.noRecentData) renders a distinct "No Data" badge on /medical, instead of the previous behaviour where an empty analytics_health_daily window silently computed activated=0/dysregulated=0 and read as "Clear" - the exact false-calm-by-omission pattern this registry exists to catch. Verified against live data: real dysregulated recovery_pulses on 2026-07-01 and 2026-07-03 (previously unread) now raise the flag.',
    degradationIsHonest: true,
    knownGap: 'Still client-render-only - no server-side scheduled evaluator exists yet, same as most of this registry (see human-systems-redflag).',
  },
  {
    capability: 'recovery-brief-posture',
    label: 'Recovery Brief — REST posture / low confidence',
    canInterrupt: 'conditional',
    conditions: "posture = 'REST', or recovery_confidence = 0 with pulses_completed = 0 after 14:00.",
    evidenceSource: 'get_recovery_posture RPC; recovery_confidence_today view',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'Confidence path has real time-of-day staging (09:00/14:00 gates); REST posture has no debounce.',
    degradationBehaviour:
      'MSN-0351: mock guidance/afternoon/load-summary/fleet blocks removed entirely rather than silently rendered as live - the page no longer mixes real posture with fabricated content under one "Live" badge.',
    degradationIsHonest: true,
    knownGap: 'REST posture still has no sustained-trend debounce, and no server-side evaluator exists.',
  },
  {
    capability: 'health-insights-risk-flags',
    label: 'Health Insights — risk flags (EOS interrupt only)',
    canInterrupt: 'yes',
    conditions: 'health_insights.risk_flags on the most recent weekly synthesis row is a real, non-empty array.',
    evidenceSource: 'health_insights.risk_flags, health_insights.generated_at',
    evaluationMethod: 'server-on-demand',
    falsePositiveGuard: 'Never fabricates a flag - nominates only when a real array with at least one element exists (healthRiskNominator, lib/interruptAssembly.ts).',
    degradationBehaviour: 'A query failure marks the Health domain unchecked in EOS (uncheckedDomains), which forces Home to Unsure rather than a silent pass - the same completeness rule every EOS nominator gets, not a page-local banner.',
    degradationIsHonest: true,
    knownGap:
      'MSN-0354 addition: this evidence source existed in interruptAssembly.ts since MSN-0349 (healthRiskNominator) but had no registry entry at all until this pass - a real reverse-direction mismatch this registry is meant to catch (a nominator with no declared coverage). risk_flags has been empty on every historical row observed to date (dormant, not yet exercised in production, same status as when MSN-0349 first wrote it) and is not rendered on any page outside EOS Home\'s primaryInterrupt slot.',
  },
  {
    capability: 'captains-brief',
    label: "Captain's Brief",
    canInterrupt: 'yes',
    conditions: 'warnings[] where risk_score >= 60 (importance x inverse-confidence).',
    evidenceSource: 'core_events via core/platform/event_bus.py, scored by priority_engine.py',
    evaluationMethod: 'server-on-demand',
    falsePositiveGuard: '_WARNING_RISK_THRESHOLD = 60.0 - requires high importance AND low confidence, not just high importance.',
    degradationBehaviour:
      'MSN-0351: "All Clear" copy replaced with "No New Signals" and an honest disclosure that an empty result cannot on its own confirm every source was reachable. The underlying cause (event_bus.py:136-138 swallows poll exceptions and returns []) is NOT fixed in this pass - documented as a required backend follow-up.',
    degradationIsHonest: false,
    knownGap:
      'Frontend copy is now honest about the limitation, but the backend still cannot distinguish a genuine outage from a quiet day. Closing this requires event_bus.py to propagate poll failures or the orchestrator to record a sources_failed/degraded flag in CaptainBriefDocument.metadata - out of scope for a Next.js-only pass.',
  },
  {
    capability: 'delivery-bottlenecks',
    label: 'Delivery / Engineering Queue — bottlenecks & mission risk',
    canInterrupt: 'yes',
    conditions:
      "delivery_state='blocked', or age thresholds (planned>3d/7d, in_review>1d, validated>1d), or deliveryRisk() >= 70.",
    evidenceSource: 'mission_delivery, mission_delivery_metrics',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'Real, reusable age thresholds in lib/delivery.ts detectBottlenecks()/deliveryRisk() - the best-defended logic in the audit. One gap: "blocked" fires with no age gate.',
    degradationBehaviour: 'Degrades gracefully to a real empty state, but still indistinguishable from "pipeline genuinely clear" - not addressed in this pass.',
    degradationIsHonest: false,
    knownGap: 'No scheduled evaluator; a real outage still reads as "nothing stuck."',
  },
  {
    capability: 'missions',
    label: 'Missions registry & detail',
    canInterrupt: 'yes',
    conditions:
      "MSN-0354: a P0 mission in a non-terminal status (see TERMINAL_STATUSES, lib/missionStatus.ts) older than 3 days, or a P1 mission older than 7 days, wired into EOS Interrupt Assembly as missionNominator (lib/interruptAssembly.ts). Page-level status='Blocked'/awaiting-approval display is unchanged and still has no separate evaluator.",
    evidenceSource: 'missions (priority, status, created_at)',
    evaluationMethod: 'server-on-demand',
    falsePositiveGuard: 'Real, disclosed priority-tiered age threshold (missionNominator) - not a naive "any non-terminal mission" rule; terminal statuses are excluded via the same TERMINAL_STATUSES list the hygiene checks use.',
    degradationBehaviour:
      'MSN-0351: explicit loadError state on the list page (distinct failure message instead of an all-zero summary); the mock-data fallback on the detail page was removed entirely and replaced with an explicit loading/found/notfound/error state so a fetch error can never render as a fabricated live record. MSN-0354: a missionNominator query failure marks the Missions domain unchecked in EOS (uncheckedDomains), which forces Home to Unsure rather than a silent pass - not yet distinguished as its own banner on the Missions page itself.',
    degradationIsHonest: true,
    knownGap: 'The interrupt threshold only covers P0/P1; P2/P3 missions and the page-level "Blocked"/awaiting-approval display still have no dedicated evaluator or staleness detector.',
  },
  {
    capability: 'engineering-rates',
    label: 'Engineering — real rates (post cognitive-load-score removal)',
    canInterrupt: 'conditional',
    conditions: 'A batch_jobs row with failed_requests > 0, or a build_request_inbox item stuck pending.',
    evidenceSource: 'build_request_inbox, agent_performance, batch_jobs',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'None - no code thresholds a failure rate today.',
    degradationBehaviour: 'MSN-0351: explicit loadError state renders a distinct failure panel instead of every sub-panel silently showing its empty state.',
    degradationIsHonest: true,
    knownGap: 'No evaluator exists to actually nominate on a failed batch or stuck request; the fabricated composite score was removed but nothing replaced it as an interrupt source.',
  },
  {
    capability: 'automation-centre',
    label: 'Automation Centre — mission execution events',
    canInterrupt: 'no',
    conditions: 'N/A - ALERT_THRESHOLDS is descriptive reference text; no code evaluates it (now explicitly labelled as such).',
    evidenceSource: 'mission_execution_events (the only live element on the page)',
    evaluationMethod: 'none',
    falsePositiveGuard: 'N/A',
    degradationBehaviour: 'MSN-0351: the events query now handles error and renders a distinct failure block instead of the "no recent events" quiet-period message.',
    degradationIsHonest: true,
    knownGap: null,
  },
  {
    capability: 'operations-friction',
    label: 'Operations — friction detection',
    canInterrupt: 'conditional',
    conditions: "captured_items.processing_status='failed', or review_status='unreviewed' AND importance='high'.",
    evidenceSource: 'captured_items, commander_events',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'unreviewedHigh requires both conditions; no age threshold exists.',
    degradationBehaviour:
      'MSN-0351: explicit loadError state + a distinct honest note, and the misleading "Live"/"No data" badge (which only meant "has rows") was renamed to reflect actual connection status.',
    degradationIsHonest: true,
    knownGap: 'No scheduled evaluator; friction is only detected over the last 10 rows fetched when a human opens the page.',
  },
  {
    capability: 'advisory-proactive',
    label: 'Advisory — proactive signals banner',
    canInterrupt: 'yes',
    conditions: 'triggers.py evaluate_triggers() classifies an escalation-rank condition (health deterioration, confidence decline, capacity overload, etc).',
    evidenceSource: 'Unified advisory timeline (signals.py, patterns.py) via core/advisory/proactive.py',
    evaluationMethod: 'server-on-demand',
    falsePositiveGuard: '_MIN_SERIES=4 history gate, trend-direction requirement, opportunities explicitly excluded from interrupt classification.',
    degradationBehaviour: 'Fails silent (.catch(() => {})) - banner simply never renders on failure. Not addressed in this pass (Advisory is Objective 5 territory - governance, not truth/degradation - and Objective 5 is document-only this mission).',
    degradationIsHonest: false,
    knownGap: 'Even when the backend genuinely computes an escalation-rank interrupt, notifications.py explicitly never sends it - the routing decision is real but the interrupt never actually reaches the Captain today. This is a product-capability gap, not just a degradation-honesty gap.',
  },
  {
    capability: 'intelligence-signals',
    label: 'Intelligence — Signals risk',
    canInterrupt: 'conditional',
    conditions:
      "overall_risk='RED' in intelligence_briefs, or an individual intelligence_events row with operational_relevance >= 0.9 - both already wired into EOS Interrupt Assembly (intelligenceEventNominator / intelligenceBriefNominator, lcars-portal/src/lib/interruptAssembly.ts). The page badge's customer_impact/banking_relevance='high' condition still has no evaluator of its own.",
    evidenceSource: 'intelligence_briefs, intelligence_events',
    evaluationMethod: 'server-on-demand',
    falsePositiveGuard: 'RED-brief path and the operational_relevance>=0.9 path (top ~5% of historical events) both have real disclosed thresholds; the page-level customer_impact/banking_relevance badge has none.',
    degradationBehaviour: 'MSN-0351: the risk badge is now disclosed as derived, not stored, with a visible "(derived)" tag; the HIGH filter bug (silently missing banking_relevance-only items) is fixed at the API layer.',
    degradationIsHonest: true,
    knownGap:
      'MSN-0354 correction: this entry previously claimed individual Signals had no interrupt evaluator. That was incorrect. intelligenceEventNominator has evaluated individual intelligence_events rows since MSN-0349 and was already wired into EOS before this registry entry was written. The remaining gap is narrower: the specific customer_impact/banking_relevance=\'high\' condition used by the page badge still has no evaluator of its own, distinct from the operational_relevance path that does.',
  },
  {
    capability: 'knowledge-library-review',
    label: 'Knowledge Library — review queue',
    canInterrupt: 'conditional',
    conditions: "status='awaiting_review' AND review_decision IS NULL AND sensitivity in (sensitive, restricted), aged past a threshold.",
    evidenceSource: 'processing_documents',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'None - a naive "queue non-empty" rule would fire against a confirmed ~795-document backlog.',
    degradationBehaviour: 'Stats fail silently by design (a "nice to have" catch); document-list failures are surfaced honestly via the existing auth/error banner.',
    degradationIsHonest: true,
    knownGap: 'No age/sensitivity-gated evaluator exists; not addressed in this pass (this capability was confirmed to already have decent error handling in MSN-0350 Phase A and was excluded from the remediation agents\' scope).',
  },
  {
    capability: 'captains-notebook-routing',
    label: "Captain's Notebook — routing queue",
    canInterrupt: 'conditional',
    conditions: "status='READY_FOR_ROUTING' AND recommended_route='captain'.",
    evidenceSource: 'intelligence_notes',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'None enforced - strategic_alignment_score/confidence_score exist but nothing gates on them.',
    degradationBehaviour: 'MSN-0351: explicit loadError state renders "Couldn\'t load notebook entries" instead of the misleading "No intelligence notes yet" empty state.',
    degradationIsHonest: true,
    knownGap: 'No evaluator exists to nominate a READY_FOR_ROUTING item as an interrupt; only surfaced when a human opens the page.',
  },
  {
    capability: 'knowledge-hub',
    label: 'Knowledge Hub (Decisions/Lessons/ADR Index)',
    canInterrupt: 'no',
    conditions: 'N/A - retrospective archive, no status/deadline/priority field in the current query.',
    evidenceSource: 'commander_decisions, lessons_learned',
    evaluationMethod: 'none',
    falsePositiveGuard: 'N/A',
    degradationBehaviour: 'MSN-0351: explicit loadError state, plus a .catch()/.finally() fix so the page can no longer be stuck permanently on "Loading..." on a full promise rejection.',
    degradationIsHonest: true,
    knownGap: null,
  },
  {
    capability: 'timeline',
    label: 'Unified Timeline',
    canInterrupt: 'no',
    conditions: 'N/A - passive chronological aggregation, no severity dimension in any source field.',
    evidenceSource: 'mission_state_transitions, recovery_pulses, captains_log_entries, mission_execution_events, captured_items',
    evaluationMethod: 'none',
    falsePositiveGuard: 'N/A',
    degradationBehaviour: 'MSN-0351: per-source failure tracking added; a quiet inline note now discloses which sources could not be checked, distinct from a genuine "no events" result.',
    degradationIsHonest: true,
    knownGap: null,
  },
  {
    capability: 'search',
    label: 'Universal Search',
    canInterrupt: 'no',
    conditions: 'N/A - user-initiated reactive query, no background evaluation.',
    evidenceSource: 'missions, captains_log_entries, captured_items, mission_execution_events',
    evaluationMethod: 'none',
    falsePositiveGuard: 'N/A',
    degradationBehaviour: 'MSN-0351: same per-source failure tracking as Timeline - a failed source is now disclosed, not silently absent from results.',
    degradationIsHonest: true,
    knownGap: null,
  },
  {
    capability: 'operating-model',
    label: 'Operating Model / Captain Profile',
    canInterrupt: 'no',
    conditions: 'N/A - ~85% static reference copy; live elements are lagging mirrors of data owned by other capabilities (Missions, Captain\'s Log, Recovery Pulse).',
    evidenceSource: 'missions (count), captains_log_entries, recovery_pulses',
    evaluationMethod: 'none',
    falsePositiveGuard: 'N/A - any real alerting should come from the owning capability, not this page.',
    degradationBehaviour: 'MSN-0351: fetchAll() now has real try/catch/finally (was previously unguarded, could leave tiles at "—" forever on a rejection); reference sections are now explicitly labelled "authored doctrine, not live data" vs. "live" sections.',
    degradationIsHonest: true,
    knownGap: null,
  },
  {
    capability: 'model-router',
    label: 'Model Router / Model Crew',
    canInterrupt: 'conditional',
    conditions: 'ollama_reachable === false (degrades every downstream LLM feature the Captain relies on).',
    evidenceSource: '/api/model/status -> core/model-router/app.py',
    evaluationMethod: 'client-render-only',
    falsePositiveGuard: 'ollama_reachable is a hard boolean; recent_avg_ms/recent_failed are computed over only the last 5 calls (would cry wolf on a single slow/failed call) - not used as an interrupt trigger today.',
    degradationBehaviour: 'Already explicit before this pass (502 banner). MSN-0351 additionally fixed the Routing Policy table to be derived from the real TASK_POLICY config instead of a hand-copied array that had drifted and was actively wrong.',
    degradationIsHonest: true,
    knownGap: 'No evaluator nominates ollama_reachable=false as a Captain-facing interrupt; it only shows as a page-local banner when someone opens /model-crew.',
  },
];

/**
 * Enforcement: every registered capability that can ever interrupt must
 * name a real evidence source and evaluation method (even if that method
 * is honestly 'client-render-only' or 'none' - the point is no capability
 * may be *missing* from this registry, and no entry may claim more than
 * it delivers).
 */
export function validateCoverage(): { ok: boolean; problems: string[] } {
  const problems: string[] = [];
  for (const entry of INTERRUPT_COVERAGE_REGISTRY) {
    if (entry.canInterrupt !== 'no' && !entry.evidenceSource.trim()) {
      problems.push(`${entry.capability}: canInterrupt=${entry.canInterrupt} but no evidenceSource declared`);
    }
    if (entry.canInterrupt === 'no' && entry.evaluationMethod !== 'none') {
      problems.push(`${entry.capability}: canInterrupt=no but evaluationMethod=${entry.evaluationMethod} (inconsistent)`);
    }
    if (entry.canInterrupt !== 'no' && entry.evaluationMethod === 'none' && !entry.knownGap) {
      problems.push(`${entry.capability}: can interrupt with no evaluator and no declared knownGap - this is exactly the silent gap this registry exists to prevent`);
    }
  }
  return { ok: problems.length === 0, problems };
}

/** Capabilities with a real, code-backed, thresholded evaluator today (not client-render-only-with-no-guard). */
export function capabilitiesWithRealEvaluator(): InterruptContractEntry[] {
  return INTERRUPT_COVERAGE_REGISTRY.filter(
    (e) => e.evaluationMethod === 'server-scheduled' || e.evaluationMethod === 'server-on-demand'
  );
}

/** Capabilities whose false-calm gap MSN-0351 did NOT close - the honest remaining punch list. */
export function openDegradationGaps(): InterruptContractEntry[] {
  return INTERRUPT_COVERAGE_REGISTRY.filter((e) => !e.degradationIsHonest);
}
