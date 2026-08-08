'use client';

// Shared presentation primitives for the Advisory Workbench views. All logic
// (fetches, endpoints, governance) is reused from the legacy Advisory Council;
// only the skin is re-expressed in the wb- design system.

import { ReactNode, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Card } from '@/components/ui';
import type { ActionResult } from '@/lib/ai-actions';
import { describeProposalOutcome } from '@/lib/actionProposalCopy';
import type { RecommendationPackage } from '@/lib/recommendations';
import type { InvestigationRunResult } from '@/lib/investigate';
import type { AdvisoryResult, CouncilAdvisor } from './types';

// ── Panel — wb- equivalent of LCARSPanel (title + optional actions header) ────
export function Panel({
  title,
  actions,
  children,
  className = '',
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <div className="mb-4 flex items-center justify-between gap-3 border-b border-wb-line pb-3">
        <h2 className="font-serif text-lg text-wb-ink">{title}</h2>
        {actions}
      </div>
      {children}
    </Card>
  );
}

// ── Elapsed-seconds hook (ported verbatim) ────────────────────────────────────
export function useElapsed(active: boolean) {
  const [elapsed, setElapsed] = useState(0);
  const ref = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (active) {
      setElapsed(0);
      ref.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } else if (ref.current) {
      clearInterval(ref.current);
    }
    return () => {
      if (ref.current) clearInterval(ref.current);
    };
  }, [active]);
  return elapsed;
}

// ── Loading dots ──────────────────────────────────────────────────────────────
export function Dots({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const dot = size === 'sm' ? 'h-1.5 w-1.5' : 'h-2 w-2';
  return (
    <div className="flex items-center gap-1.5">
      {[0, 1, 2].map((i) => (
        <span key={i} className={`${dot} animate-pulse rounded-full bg-wb-sage-deep`} style={{ animationDelay: `${i * 150}ms` }} />
      ))}
    </div>
  );
}

// ── Advisor registry (MSN-0205 — extended council) ────────────────────────────
export const COUNCIL: CouncilAdvisor[] = [
  // Command
  { id: 'xo', label: 'XO', subtitle: 'Executive Officer', group: 'Command', useXoEndpoint: true },
  { id: 'chief_engineer', label: 'Chief Engineer', subtitle: 'Architecture & Engineering', group: 'Command' },
  { id: 'research_officer', label: 'Research Officer', subtitle: 'Intelligence & Analysis', group: 'Command' },
  // Operations
  { id: 'number_one', label: 'Number One', subtitle: 'Priorities & Sequencing', group: 'Operations' },
  // Wellness
  { id: 'medical_officer', label: 'Medical Officer', subtitle: 'Capacity & Health', group: 'Wellness' },
  { id: 'recovery_officer', label: 'Recovery Officer', subtitle: 'Directive 055 Compliance', group: 'Wellness' },
  { id: 'wellness_advisor', label: 'Wellness Advisor', subtitle: 'Whole-Person Wellbeing', group: 'Wellness' },
  { id: 'recovery_coach', label: 'Recovery Coach', subtitle: 'Protocol Optimisation', group: 'Wellness' },
  { id: 'performance_coach', label: 'Perf. Coach', subtitle: 'Capacity Windows', group: 'Wellness' },
  // Operational Resilience
  { id: 'or_advisor', label: 'OR Advisor', subtitle: 'Operational Resilience', group: 'Resilience' },
  { id: 'bc_advisor', label: 'BC Advisor', subtitle: 'Business Continuity', group: 'Resilience' },
  { id: 'crisis_advisor', label: 'Crisis Advisor', subtitle: 'Crisis Management', group: 'Resilience' },
  { id: 'executive_risk_advisor', label: 'Risk Advisor', subtitle: 'Executive Risk', group: 'Resilience' },
  // Advisory Board — Independent Strategic Council
  { id: 'strategist', label: 'Strategist', subtitle: 'Long-Range Strategy', group: 'Advisory Board' },
  { id: 'challenger', label: 'Challenger', subtitle: "Devil's Advocate", group: 'Advisory Board', dissent: true },
  { id: 'operator', label: 'Operator', subtitle: 'Execution Reality', group: 'Advisory Board' },
  { id: 'external_lens', label: 'Ext. Lens', subtitle: 'Market & World View', group: 'Advisory Board' },
  { id: 'commercial_realist', label: 'Commercial', subtitle: 'Commercial Viability', group: 'Advisory Board' },
  { id: 'human_systems_advisor', label: 'Human Systems', subtitle: 'People & Culture', group: 'Advisory Board' },
];

// ── MSN-0352 proposal block ───────────────────────────────────────────────────
/** The one place this UI states whether an action was queued or failed. Text
 * comes from describeProposalOutcome() (lib/actionProposalCopy.ts) — a plain,
 * unit-tested function — so "never claims completion for a mere proposal" is a
 * verified property, not a convention. Ported verbatim from the LCARS page. */
export function ProposalBlock({ proposals }: { proposals: ActionResult[] }) {
  if (!proposals.length) return null;
  return (
    <div className="mt-2 flex flex-col gap-1.5 border-l-2 border-wb-sage-deep/40 pl-3">
      {proposals.map((p, i) => (
        <div key={i} className={`text-xs ${p.success ? 'text-wb-ink2' : 'text-wb-crit-on'}`}>
          <span className="font-semibold">{describeProposalOutcome(p)}</span>
          {p.success && (
            <>
              {' '}
              <Link href="/decisions" className="font-normal underline hover:text-wb-sage-deep">Open Decide →</Link>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Evidence panel (EOS Phase 2 Priority 4) ───────────────────────────────────
export function EvidencePanel({
  recommendations,
  investigation,
}: {
  recommendations: RecommendationPackage | null;
  investigation: InvestigationRunResult | null;
}) {
  const hasRecommendations = !!recommendations?.recommendations.length;
  if (!hasRecommendations && !investigation) return null;
  return (
    <div className="space-y-3 rounded-md border border-wb-line bg-wb-bg p-3">
      <p className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">
        Evidence — sourced directly from the canonical engines, not an officer&apos;s interpretation
      </p>
      {hasRecommendations && (
        <div>
          <p className="mb-1 text-[10px] uppercase tracking-widest text-wb-sage-deep">Recommendation Engine</p>
          <ul className="space-y-1">
            {recommendations!.recommendations.slice(0, 3).map((r) => (
              <li key={r.mission_id} className="text-xs text-wb-ink/80">
                <span className="text-wb-ink">{r.title}</span>{' '}
                <span className="text-wb-ink2">({r.mission_id})</span> — {r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {investigation && (
        <div>
          <p className="mb-1 text-[10px] uppercase tracking-widest text-wb-sage-deep">
            Investigation Engine — {investigation.label}
          </p>
          <p className="text-xs text-wb-ink/80">{investigation.triggerDescription}</p>
          {investigation.decisionOptions.length > 0 && (
            <ul className="mt-1 space-y-1">
              {investigation.decisionOptions.map((opt) => (
                <li key={opt.id} className="text-xs text-wb-ink/70">{opt.label}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ── Advisory block (summary / recommendation / risks / confidence) ────────────
export function AdvisoryBlock({ data }: { data: AdvisoryResult }) {
  const conf = typeof data.confidence === 'object' && data.confidence ? data.confidence : null;
  return (
    <div className="space-y-3 text-sm">
      {(data.executive_summary || data.bottom_line) && (
        <div className="rounded-md border border-wb-sage-deep/30 bg-wb-sage-deep/10 px-3 py-2">
          <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-wb-sage-deep">Summary</p>
          <p className="leading-relaxed text-wb-ink">{String(data.executive_summary ?? data.bottom_line ?? '')}</p>
        </div>
      )}
      {data.recommendation && (
        <div className="rounded-md border border-wb-sage-deep/30 bg-wb-sage-deep/10 px-3 py-2">
          <p className="mb-1 text-[10px] uppercase tracking-[0.15em] text-wb-sage-deep">Recommendation</p>
          <p className="leading-relaxed text-wb-ink">{String(data.recommendation)}</p>
        </div>
      )}
      {Array.isArray(data.risks_and_challenges) && data.risks_and_challenges.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.15em] text-wb-sage-deep">Risks</p>
          <ul className="space-y-1">
            {data.risks_and_challenges.map((r, i) => (
              <li key={i} className="flex gap-2 text-wb-ink/80">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-wb-sage-deep" />
                {String(r)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {conf && (
        <p className="text-[10px] text-wb-ink2">
          Confidence: {conf.band ?? ''} ({conf.value ?? ''})
          {conf.basis ? ` — ${conf.basis}` : ''}
        </p>
      )}
    </div>
  );
}
