'use client';

// Brief view — summary, the raw Interrupt-Now bucket, warnings, priorities,
// recommendations, next actions, and insights. Ports the LCARS page's primary
// panels and additionally renders interrupt_now (MSN-0339) and insights
// (MSN-0329) — real content the old UI carried in the document but never showed
// (Captain decision 2026-07-12: render them).

import { Card } from './Shell';
import { WarningBanner, RecCard } from './cards';
import { ItemRow } from './ItemRow';
import type { CaptainBriefDocument, CaptainBriefItem, Insight, Recommendation } from './types';
import { warningsLevel } from './types';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card title={title} className="mb-4">
      {children}
    </Card>
  );
}

function ItemGrid({ items }: { items: CaptainBriefItem[] }) {
  return (
    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {items.map((item, i) => (
        <ItemRow key={item.event_id ?? i} item={item} />
      ))}
    </ul>
  );
}

function priorityToRec(item: CaptainBriefItem) {
  return {
    action: item.recommendation?.description ?? item.reason,
    why: item.priority_explanation ?? undefined,
    source: item.domain,
    confidence: item.recommendation?.confidence != null ? `${item.recommendation.confidence}%` : 'Unscored',
    evidence: item.recommendation?.evidence,
  };
}

function recToRec(rec: Recommendation) {
  return {
    action: rec.description,
    why: rec.supporting_context ?? undefined,
    source: rec.action_type ?? 'Recommendation',
    confidence: rec.confidence != null ? `${rec.confidence}%` : 'Unscored',
    evidence: rec.evidence,
  };
}

function InsightCard({ insight }: { insight: Insight }) {
  return (
    <div className="rounded-md border border-wb-line bg-wb-surface p-3">
      {insight.observation && <p className="text-[13px] font-medium text-wb-ink">{insight.observation}</p>}
      {insight.why_it_matters && <p className="mt-1 text-[12px] text-wb-ink2">{insight.why_it_matters}</p>}
      {insight.potential_impact && (
        <p className="mt-1 text-[11px] text-wb-ink2/90">Impact: {insight.potential_impact}</p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] uppercase tracking-[0.14em] text-wb-sage-deep">
        {insight.source_kind && <span>{insight.source_kind}</span>}
        {insight.source_domains && insight.source_domains.length > 0 && (
          <span className="normal-case tracking-normal text-wb-ink2">{insight.source_domains.join(', ')}</span>
        )}
        {insight.confidence != null && <span className="text-wb-ink2">{insight.confidence}% confidence</span>}
      </div>
      {insight.evidence_chain && insight.evidence_chain.length > 0 && (
        <ul className="mt-1.5 list-disc pl-4 text-[11px] text-wb-ink2/90">
          {insight.evidence_chain.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function BriefView({
  doc,
  refs,
}: {
  doc: CaptainBriefDocument;
  refs: {
    warnings: React.RefObject<HTMLDivElement>;
    priorities: React.RefObject<HTMLDivElement>;
    next_actions: React.RefObject<HTMLDivElement>;
  };
}) {
  const empty = doc.priorities.length === 0 && doc.warnings.length === 0 && doc.interrupt_now.length === 0;

  return (
    <>
      <Section title="Summary">
        <p className="text-sm leading-relaxed text-wb-ink/90">{doc.summary}</p>
      </Section>

      {doc.interrupt_now.length > 0 && (
        <Section title="Interrupt Now">
          <p className="mb-2 text-[11px] text-wb-ink2">
            The raw Attention Engine interrupt-now bucket — items judged to warrant immediate attention.
          </p>
          <ItemGrid items={doc.interrupt_now} />
        </Section>
      )}

      {doc.warnings.length > 0 && (
        <div ref={refs.warnings}>
          <Section title="Warnings">
            <div className="flex flex-col gap-2">
              <WarningBanner
                level={warningsLevel(doc.warnings)}
                message={`${doc.warnings.length} high-risk item(s) — review before proceeding.`}
              />
              <ItemGrid items={doc.warnings} />
            </div>
          </Section>
        </div>
      )}

      {doc.priorities.length > 0 && (
        <div ref={refs.priorities}>
          <Section title="Priorities">
            <div className="flex flex-col gap-2">
              {doc.priorities.map((item, i) => (
                <RecCard key={item.event_id ?? i} {...priorityToRec(item)} />
              ))}
            </div>
          </Section>
        </div>
      )}

      {doc.recommendations.length > 0 && (
        <Section title="Recommendations">
          <div className="flex flex-col gap-2">
            {doc.recommendations.map((rec, i) => (
              <RecCard key={i} {...recToRec(rec)} />
            ))}
          </div>
        </Section>
      )}

      {doc.next_actions.length > 0 && (
        <div ref={refs.next_actions}>
          <Section title="Next Actions">
            <ol className="flex flex-col gap-1.5">
              {doc.next_actions.map((a, i) => (
                <li key={i} className="flex gap-2 text-sm text-wb-ink/90">
                  <span className="shrink-0 font-serif text-wb-sage-deep">{i + 1}.</span>
                  {a}
                </li>
              ))}
            </ol>
          </Section>
        </div>
      )}

      {doc.insights.length > 0 && (
        <Section title="Insights">
          <div className="flex flex-col gap-2">
            {doc.insights.map((ins, i) => (
              <InsightCard key={i} insight={ins} />
            ))}
          </div>
        </Section>
      )}

      {empty && (
        // MSN-0351: an all-empty document is NOT proof that all is well — the
        // brief is assembled from poll_events(), which returns [] on any
        // Supabase error, so a data outage looks identical to a quiet period.
        // Report what is actually known, don't affirmatively reassure.
        <Section title="No New Signals">
          <p className="text-sm text-wb-ink2">No priorities, warnings, or interrupts in the latest brief.</p>
          <p className="mt-1 text-xs text-wb-ink2/80">
            This reflects the signals received — it can’t on its own confirm every source was reachable. If you
            expected activity, check source health before treating this as all-clear.
          </p>
        </Section>
      )}
    </>
  );
}
