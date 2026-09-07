'use client';

import { ReactNode } from 'react';
import { Card, Badge, toneToStatus } from '@/components/ui';
import { lifecycleStateToTone, valueToTone, opportunityRiskToTone, outcomeResultToTone } from '@/lib/departments';
import { CHANGE_CLASS_LABEL, MISSION_ONLY_CLASSES, type Opportunity } from './types';

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">{label}</h3>
      <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-sm text-wb-ink">{children}</div>
    </section>
  );
}

function capitalizeWords(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const OUTCOME_RESULT_LABEL: Record<string, string> = {
  improved: 'IMPROVED',
  no_material_change: 'NO MATERIAL CHANGE',
  regressed: 'REGRESSED',
  inconclusive: 'INCONCLUSIVE',
  not_yet_ready: 'STILL OBSERVING',
};

const IMPLEMENTATION_SOURCE_LABEL: Record<string, string> = {
  remediation: 'via remediation',
  mission: 'via mission',
  manual: 'manually confirmed',
};

function observationWindowText(window: { type: string; count: number } | undefined | null): string | null {
  if (!window) return null;
  switch (window.type) {
    case 'immediate': return 'Immediate verification';
    case 'cycles': return `${window.count} completed HQ Evolution cycles`;
    case 'events': return `${window.count} events`;
    case 'days': return `${window.count} days`;
    default: return null;
  }
}

/** Section 22: investigation / evaluation detail, progressively disclosed
 * (raw provenance behind a <details>, section 22/47). Section 26: a
 * Mission-only banner for capability/product_improvement/architecture. */
export function OpportunityDetail({
  opportunity, actions, missionStatus, missionDispatch,
}: {
  opportunity: Opportunity;
  actions?: ReactNode;
  /** Live status of the Mission this opportunity was handed off to, when
   * known — e.g. "Approved for Engineering", "Awaiting XO Approval". The
   * Mission system's own staged-approval ladder, surfaced here rather than
   * requiring the Captain to go look it up elsewhere. */
  missionStatus?: string | null;
  /** core/engineering/mission_dispatch.py's own outcome for this Mission,
   * when it has actually dispatched one — mission_dispatch.py never writes
   * back to Supabase, so missionStatus above can keep reading e.g.
   * "Approved for Engineering" long after a draft PR was already opened;
   * this is how that gets told apart from "not yet dispatched" at all. */
  missionDispatch?: { success: boolean; message: string; pr_url: string | null } | null;
}) {
  const inv = opportunity.investigation || {};
  const isMissionOnly = MISSION_ONLY_CLASSES.includes(opportunity.change_class);
  const contract = opportunity.outcome_contract && 'expected_benefit' in opportunity.outcome_contract
    ? opportunity.outcome_contract
    : null;
  const outcome = opportunity.outcome;
  const hasV2Outcome = outcome?.outcome_result !== undefined && outcome?.outcome_result !== null;
  const hasV1Outcome = outcome?.implementation_success !== undefined && outcome?.implementation_success !== null;

  return (
    <Card title={opportunity.title}>
      <div className="flex gap-2 flex-wrap mb-4">
        <span className="text-xs bg-wb-line text-wb-ink2 px-2 py-1 rounded">
          {CHANGE_CLASS_LABEL[opportunity.change_class] ?? opportunity.change_class}
        </span>
        <Badge status={toneToStatus(lifecycleStateToTone(opportunity.lifecycle_state))}>
          {opportunity.lifecycle_state.replace('_', ' ')}
        </Badge>
        {opportunity.mission_id && (
          <Badge status="info">Mission {opportunity.mission_id}: {missionStatus ?? 'loading…'}</Badge>
        )}
        {opportunity.value && <Badge status={toneToStatus(valueToTone(opportunity.value))}>Value: {opportunity.value}</Badge>}
        {opportunity.risk_level && (
          <Badge status={toneToStatus(opportunityRiskToTone(opportunity.risk_level))}>Risk: {opportunity.risk_level}</Badge>
        )}
        <span className="text-xs text-wb-ink2 px-2 py-1">{opportunity.discovery_source === 'external' ? 'External discovery' : 'Internal discovery'}</span>
      </div>

      {opportunity.summary && <Field label="What HQ found">{opportunity.summary}</Field>}

      {opportunity.why_relevant && (
        <Field label="Why HQ is looking at this">{inv.why_hq_is_looking_at_this || opportunity.why_relevant}</Field>
      )}

      <div className="grid grid-cols-2 gap-4 mb-5 sm:grid-cols-4">
        <div>
          <div className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-1">Fit with HQ</div>
          <div className="text-sm text-wb-ink capitalize">{inv.fit_with_hq || opportunity.fit || 'Not yet assessed'}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-1">Cost impact</div>
          <div className="text-sm text-wb-ink capitalize">{inv.cost_impact || opportunity.cost_impact || 'Unknown'}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-1">Implementation effort</div>
          <div className="text-sm text-wb-ink capitalize">{inv.implementation_effort || opportunity.complexity || 'Not yet assessed'}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-1">Confidence</div>
          <div className="text-sm text-wb-ink">{Math.round((inv.confidence ?? opportunity.confidence ?? 0) * 100)}%</div>
        </div>
      </div>

      {!!inv.potential_benefits?.length && (
        <Field label="Potential benefits">
          <ul className="list-disc pl-4 space-y-1">
            {inv.potential_benefits.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </Field>
      )}

      {!!inv.risks?.length && (
        <Field label="Risks">
          <ul className="list-disc pl-4 space-y-1">
            {inv.risks.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </Field>
      )}

      {!!inv.alternatives?.length && (
        <Field label="Alternatives considered">
          <ul className="list-disc pl-4 space-y-1">
            {inv.alternatives.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </Field>
      )}

      {inv.recommendation && (
        <Field label="HQ's assessment (advisory only — not a decision)">
          <div className="font-semibold capitalize">{inv.recommendation.replace(/_/g, ' ')}</div>
          {inv.recommendation_rationale && <div className="mt-1 text-wb-ink2">{inv.recommendation_rationale}</div>}
        </Field>
      )}

      {!!opportunity.missing_evidence?.length && (
        <Field label="Evidence still needed">
          <ul className="list-disc pl-4 space-y-1">
            {opportunity.missing_evidence.map((m, i) => <li key={i}>{m}</li>)}
          </ul>
        </Field>
      )}

      {contract && (
        <Field label="What HQ committed to measure">
          <div><strong>Expected benefit:</strong> {contract.expected_benefit}</div>
          <div className="mt-1"><strong>Measurement type:</strong> {capitalizeWords(contract.measurement_type)}</div>
          <div className="mt-1">
            <strong>Baseline:</strong>{' '}
            {contract.baseline.available
              ? contract.baseline.description
              : `No baseline available — ${contract.baseline.reason}`}
          </div>
          <div className="mt-1"><strong>Success would look like:</strong> {contract.success_signal}</div>
          <div className="mt-1"><strong>Regression would look like:</strong> {contract.regression_signal}</div>
          {observationWindowText(contract.observation_window) && (
            <div className="mt-1"><strong>Observation window:</strong> {observationWindowText(contract.observation_window)}</div>
          )}
          <div className="mt-1"><strong>Evaluation status:</strong> {capitalizeWords(contract.evaluation_status)}</div>
        </Field>
      )}

      {opportunity.lifecycle_state === 'resolved_before_research' && (
        <Field label="Why HQ didn't research this further">
          <div>HQ checked its current state before spending external research effort, and the hypothesised gap no longer holds.</div>
          {!!opportunity.validation_evidence?.length && (
            <ul className="list-disc pl-4 mt-2 space-y-1 text-xs text-wb-ink2">
              {opportunity.validation_evidence.map((e, i) => <li key={i} className="break-all">{e}</li>)}
            </ul>
          )}
          {opportunity.validated_at && (
            <div className="mt-1 text-xs text-wb-ink2">Checked {new Date(opportunity.validated_at).toLocaleDateString()}</div>
          )}
        </Field>
      )}

      {opportunity.rejection_reason && <Field label="Why this was rejected">{opportunity.rejection_reason}</Field>}
      {opportunity.watch_reason && <Field label="Why HQ is watching, not acting">{opportunity.watch_reason}</Field>}

      {hasV2Outcome && outcome && (
        <Field label="Outcome">
          <div className="flex flex-wrap items-center gap-3">
            <div>
              Implementation: <strong>{outcome.implementation_success ? 'Succeeded' : 'Failed'}</strong>
              {outcome.implementation_source && IMPLEMENTATION_SOURCE_LABEL[outcome.implementation_source] && (
                <span className="text-wb-ink2"> ({IMPLEMENTATION_SOURCE_LABEL[outcome.implementation_source]})</span>
              )}
            </div>
            <Badge status={toneToStatus(outcomeResultToTone(outcome.outcome_result))} className="text-[12px] px-3 py-1">
              {OUTCOME_RESULT_LABEL[outcome.outcome_result as string] ?? outcome.outcome_result}
            </Badge>
          </div>

          {(outcome.evidence_summary || outcome.what_worked || outcome.what_did_not || outcome.unexpected_effects?.length || outcome.future_implication || outcome.confidence) && (
            <div className="mt-3 space-y-1">
              {outcome.evidence_summary && <div>{outcome.evidence_summary}</div>}
              {outcome.what_worked && <div><strong>What worked:</strong> {outcome.what_worked}</div>}
              {outcome.what_did_not && <div><strong>What didn&apos;t:</strong> {outcome.what_did_not}</div>}
              {!!outcome.unexpected_effects?.length && (
                <div>
                  <strong>Unexpected effects:</strong>
                  <ul className="list-disc pl-4 mt-1 space-y-1">
                    {outcome.unexpected_effects.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}
              {outcome.future_implication && (
                <div className="mt-2 font-semibold">{outcome.future_implication}</div>
              )}
              {outcome.confidence && (
                <div className="text-wb-ink2">Confidence: {capitalizeWords(outcome.confidence)}</div>
              )}
            </div>
          )}

          {outcome.attribution_risk && (
            <div className="mt-2 text-xs text-wb-warn-on bg-wb-warn/10 border border-wb-warn/40 rounded px-2 py-1">
              Note: {outcome.attribution_risk}
            </div>
          )}

          {outcome.method === 'template_fallback' && (
            <div className="mt-2 text-xs text-wb-ink2 italic">
              Deeper assessment was unavailable — deterministic evidence only.
            </div>
          )}

          {!!outcome.evaluation_history?.length && outcome.evaluation_history.length > 1 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs uppercase text-wb-ink2 tracking-wider font-semibold">
                Prior evaluations ({outcome.evaluation_history.length})
              </summary>
              <div className="mt-2 space-y-2">
                {[...outcome.evaluation_history]
                  .sort((a, b) => new Date(a.evaluated_at).getTime() - new Date(b.evaluated_at).getTime())
                  .map((h, i) => (
                  <div key={i} className="bg-wb-bg p-2 rounded border-l-4 border-wb-line text-xs text-wb-ink2">
                    <div>
                      <strong className="text-wb-ink">{OUTCOME_RESULT_LABEL[h.outcome_result] ?? h.outcome_result}</strong>
                      {h.evaluated_at ? ` · ${new Date(h.evaluated_at).toLocaleDateString()}` : ''}
                    </div>
                    {h.evidence_summary && <div className="mt-1">{h.evidence_summary}</div>}
                  </div>
                ))}
              </div>
            </details>
          )}
        </Field>
      )}

      {!hasV2Outcome && hasV1Outcome && outcome && (
        <Field label="Outcome">
          <div>Implementation: <strong>{outcome.implementation_success ? 'Succeeded' : 'Failed'}</strong></div>
          <div>
            Improvement:{' '}
            <strong>
              {outcome.improvement_success === true && 'Confirmed'}
              {outcome.improvement_success === false && 'Did not improve'}
              {(outcome.improvement_success === null || outcome.improvement_success === undefined) && 'Not yet measured'}
            </strong>
          </div>
          {outcome.improvement_success_note && (
            <div className="mt-1 text-xs text-wb-ink2">{outcome.improvement_success_note}</div>
          )}
        </Field>
      )}

      {opportunity.remediation_status && (
        <Field label="Auto-remediation">
          {/* 2026-09-07: HandoffPRStrategy reports success=true even when NO
              PR was opened (an existing-file edit deferred to manual review,
              or no_files_written) — success only ever meant "the coding
              attempt didn't error," never "a PR exists". Must gate on the
              real pr_url, not remediation_status alone, or this falsely
              tells the Captain a PR is waiting to merge when there is none —
              confirmed live on several real opportunities. */}
          {opportunity.remediation_status === 'succeeded' ? (
            opportunity.remediation_pr_url ? (
              <div>
                Draft PR opened for review:{' '}
                <a href={opportunity.remediation_pr_url} target="_blank" rel="noreferrer" className="underline break-all">
                  {opportunity.remediation_pr_url}
                </a>
                . Review and merge it like any other PR — HQ never merges this itself.
              </div>
            ) : (
              <div>{opportunity.remediation_message}</div>
            )
          ) : (
            <div className="text-wb-crit-on">Attempt failed: {opportunity.remediation_message}</div>
          )}
          {opportunity.remediation_at && (
            <div className="mt-1 text-xs text-wb-ink2">{new Date(opportunity.remediation_at).toLocaleString()}</div>
          )}
        </Field>
      )}

      {opportunity.mission_id && missionDispatch && (
        <Field label="Engineering dispatch">
          {missionDispatch.success ? (
            <div>
              Auto-dispatched to engineering
              {missionDispatch.pr_url && (
                <>
                  :{' '}
                  <a href={missionDispatch.pr_url} target="_blank" rel="noreferrer" className="underline break-all">
                    {missionDispatch.pr_url}
                  </a>
                </>
              )}
              . This may not yet be reflected in the Mission status above — review and merge like any other PR.
            </div>
          ) : (
            <div className="text-wb-crit-on">Dispatch attempt failed: {missionDispatch.message}</div>
          )}
        </Field>
      )}

      {isMissionOnly && (
        <p className="mb-5 rounded-lg border border-wb-warn/40 bg-wb-warn/10 p-3 text-xs text-wb-ink">
          {CHANGE_CLASS_LABEL[opportunity.change_class]} changes are Mission-only — HQ Evolution never applies these
          directly, however high its confidence. A Mission hands this off for controlled implementation; it does not
          modify production by itself.
        </p>
      )}

      {!!opportunity.provenance?.length && (
        <details className="mb-5">
          <summary className="cursor-pointer text-xs uppercase text-wb-ink2 tracking-wider font-semibold">
            Evidence &amp; provenance ({opportunity.provenance.length})
          </summary>
          <div className="mt-2 space-y-2">
            {opportunity.provenance.map((p, i) => (
              <div key={i} className="bg-wb-bg p-3 rounded border-l-4 border-wb-line text-xs text-wb-ink2">
                <div><strong className="text-wb-ink">{p.source}</strong>{p.retrieved_at ? ` · retrieved ${new Date(p.retrieved_at).toLocaleDateString()}` : ''}</div>
                {p.location && <div className="mt-1 break-all">{p.location}</div>}
                {p.detail && <div className="mt-1 font-mono break-all">{p.detail}</div>}
              </div>
            ))}
          </div>
        </details>
      )}

      {actions}
    </Card>
  );
}
