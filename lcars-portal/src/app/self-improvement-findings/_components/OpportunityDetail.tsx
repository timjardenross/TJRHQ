'use client';

import { ReactNode } from 'react';
import { Card, Badge, toneToStatus } from '@/components/ui';
import { lifecycleStateToTone, valueToTone, opportunityRiskToTone } from '@/lib/departments';
import { CHANGE_CLASS_LABEL, MISSION_ONLY_CLASSES, type Opportunity } from './types';

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">{label}</h3>
      <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-sm text-wb-ink">{children}</div>
    </section>
  );
}

/** Section 22: investigation / evaluation detail, progressively disclosed
 * (raw provenance behind a <details>, section 22/47). Section 26: a
 * Mission-only banner for capability/product_improvement/architecture. */
export function OpportunityDetail({ opportunity, actions }: { opportunity: Opportunity; actions?: ReactNode }) {
  const inv = opportunity.investigation || {};
  const isMissionOnly = MISSION_ONLY_CLASSES.includes(opportunity.change_class);

  return (
    <Card title={opportunity.title}>
      <div className="flex gap-2 flex-wrap mb-4">
        <span className="text-xs bg-wb-line text-wb-ink2 px-2 py-1 rounded">
          {CHANGE_CLASS_LABEL[opportunity.change_class] ?? opportunity.change_class}
        </span>
        <Badge status={toneToStatus(lifecycleStateToTone(opportunity.lifecycle_state))}>
          {opportunity.lifecycle_state.replace('_', ' ')}
        </Badge>
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

      {opportunity.rejection_reason && <Field label="Why this was rejected">{opportunity.rejection_reason}</Field>}
      {opportunity.watch_reason && <Field label="Why HQ is watching, not acting">{opportunity.watch_reason}</Field>}

      {(opportunity.outcome?.implementation_success !== undefined && opportunity.outcome?.implementation_success !== null) && (
        <Field label="Outcome">
          <div>Implementation: <strong>{opportunity.outcome.implementation_success ? 'Succeeded' : 'Failed'}</strong></div>
          <div>
            Improvement:{' '}
            <strong>
              {opportunity.outcome.improvement_success === true && 'Confirmed'}
              {opportunity.outcome.improvement_success === false && 'Did not improve'}
              {(opportunity.outcome.improvement_success === null || opportunity.outcome.improvement_success === undefined) && 'Not yet measured'}
            </strong>
          </div>
          {opportunity.outcome.improvement_success_note && (
            <div className="mt-1 text-xs text-wb-ink2">{opportunity.outcome.improvement_success_note}</div>
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
