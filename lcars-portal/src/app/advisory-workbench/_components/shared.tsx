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
import type { AdvisoryResult, CouncilAdvisor, EvidenceItem, OfficerPerspective, ReasoningGroup } from './types';

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
    <div className="flex items-center gap-1.5" aria-hidden="true">
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

// ── Reasoning-group lens (mission §8 "Pull apart the reasoning") ─────────────
/** Maps a returned officer/specialist name onto one of the small set of
 * user-facing reasoning groups. A relabelling of the existing COUNCIL
 * registry (plus stance), not a new taxonomy — 'Evidence' is deliberately
 * absent here since it is never officer-sourced (see EvidencePanel). */
export function groupForOfficer(op: Pick<OfficerPerspective, 'officer' | 'stance'>): ReasoningGroup {
  const advisor = COUNCIL.find((a) => a.label.toLowerCase() === op.officer?.toLowerCase() || a.id.toLowerCase() === op.officer?.toLowerCase());
  if (advisor?.dissent || op.stance === 'cautions' || op.stance === 'challenges') return 'Challenge';
  switch (advisor?.group) {
    case 'Wellness':
      return 'Human Systems';
    case 'Resilience':
      return 'Risk';
    default:
      return 'Strategy';
  }
}

const REASONING_GROUP_ORDER: ReasoningGroup[] = ['Strategy', 'Human Systems', 'Risk', 'Challenge'];

function groupPerspectives(perspectives: OfficerPerspective[]): Map<ReasoningGroup, OfficerPerspective[]> {
  const map = new Map<ReasoningGroup, OfficerPerspective[]>();
  for (const op of perspectives) {
    const g = groupForOfficer(op);
    map.set(g, [...(map.get(g) ?? []), op]);
  }
  return map;
}

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
              <Link href="/captains-chair-workbench" className="font-normal underline hover:text-wb-sage-deep">Open Captain&apos;s Chair →</Link>
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
  historicalEvidence,
}: {
  recommendations: RecommendationPackage | null;
  investigation: InvestigationRunResult | null;
  historicalEvidence?: EvidenceItem[];
}) {
  const hasRecommendations = !!recommendations?.recommendations.length;
  const hasHistorical = (historicalEvidence?.length ?? 0) > 0;
  if (!hasRecommendations && !investigation && !hasHistorical) return null;
  return (
    <div className="space-y-3 rounded-md border border-wb-line bg-wb-bg p-3">
      <p className="text-[10px] uppercase tracking-[0.15em] text-wb-ink2">
        Evidence — sourced directly from the canonical engines, not an officer&apos;s interpretation
      </p>
      {hasHistorical && (
        <div>
          <p className="mb-1 text-[10px] uppercase tracking-widest text-wb-sage-deep">Historical Evidence</p>
          <ul className="space-y-1">
            {historicalEvidence!.map((e, i) => (
              <li key={i} className="text-xs text-wb-ink/80">
                <span className="text-wb-ink">{e.reference}</span>
                {typeof e.outcome_score === 'number' && <span className="text-wb-ink2"> ({Math.round(e.outcome_score * 100)}%)</span>}
                {' '}— {e.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
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

// ── Result section primitive (mission §7 result hierarchy) ───────────────────
function ResultSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`think-${label}`} className="rounded-md border border-wb-line bg-wb-surface px-4 py-3">
      <h3 id={`think-${label}`} className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-wb-sage-deep">{label}</h3>
      {children}
    </section>
  );
}

/** THE READ / WHY / WHAT I'D CHALLENGE / WHAT'S UNCERTAIN / RECOMMENDATION /
 * CONFIDENCE (mission §7) — never expose backend architecture before the
 * answer, never fabricate a section that has nothing real to say. */
export function ThinkResult({ data }: { data: AdvisoryResult }) {
  const conf = typeof data.confidence === 'object' && data.confidence ? data.confidence : null;
  const evidence = data.historical_evidence ?? [];
  const lessons = data.related_lessons ?? [];
  const risks = data.risks_and_challenges ?? [];

  const uncertainties: string[] = [];
  if (conf && conf.band !== 'High' && conf.basis) uncertainties.push(conf.basis);
  if (data.escalation_required) uncertainties.push('This crossed an escalation threshold — treat the recommendation as provisional and revisit before relying on it.');
  if (evidence.length === 0 && lessons.length === 0) uncertainties.push('No directly comparable history was found for this question.');

  return (
    <div className="space-y-3 text-sm">
      {data.degraded && (
        <div className="flex items-start gap-2 rounded-md border border-wb-warn/50 bg-wb-warn/10 px-3 py-2.5">
          <span aria-hidden className="mt-0.5 text-xs font-bold text-wb-warn-on">▲</span>
          <div>
            <p className="text-xs font-semibold text-wb-warn-on">Limited advisory</p>
            <p className="mt-0.5 text-xs text-wb-warn-on/90">
              Live specialist reasoning was unavailable. This response is based on available historical evidence only.
            </p>
          </div>
        </div>
      )}

      {(data.executive_summary || data.bottom_line) && (
        <ResultSection label="The Read">
          <p className="leading-relaxed text-wb-ink">{String(data.executive_summary ?? data.bottom_line ?? '')}</p>
        </ResultSection>
      )}

      {(evidence.length > 0 || lessons.length > 0) && (
        <ResultSection label="Why">
          <ul className="space-y-1.5">
            {evidence.slice(0, 3).map((e, i) => (
              <li key={`e-${i}`} className="flex gap-2 text-wb-ink/85">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-wb-sage-deep" />
                <span>{e.detail}{typeof e.outcome_score === 'number' ? ` (${Math.round(e.outcome_score * 100)}% historical outcome)` : ''}</span>
              </li>
            ))}
            {lessons.slice(0, 2).map((l, i) => (
              <li key={`l-${i}`} className="flex gap-2 text-wb-ink/85">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-wb-sage-deep" />
                <span><span className="text-wb-ink">{l.title}</span>{l.guidance ? ` — ${l.guidance}` : ''}</span>
              </li>
            ))}
          </ul>
        </ResultSection>
      )}

      {(risks.length > 0 || data.disagreement) && (
        <ResultSection label="What I'd Challenge">
          <ul className="space-y-1.5">
            {data.disagreement && (
              <li className="flex gap-2 text-wb-ink/85">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-wb-crit" />
                <span>{data.disagreement}</span>
              </li>
            )}
            {risks.map((r, i) => (
              <li key={i} className="flex gap-2 text-wb-ink/85">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-wb-sage-deep" />
                {String(r)}
              </li>
            ))}
          </ul>
        </ResultSection>
      )}

      {uncertainties.length > 0 && (
        <ResultSection label="What's Uncertain">
          <ul className="space-y-1.5">
            {uncertainties.map((u, i) => (
              <li key={i} className="flex gap-2 text-wb-ink/85">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-wb-warn" />
                {u}
              </li>
            ))}
          </ul>
        </ResultSection>
      )}

      {data.recommendation && (
        <ResultSection label="Recommendation">
          <p className="leading-relaxed text-wb-ink">{String(data.recommendation)}</p>
        </ResultSection>
      )}

      {conf && (
        <p className="text-[10px] text-wb-ink2">
          Confidence: {conf.band ?? ''} ({Math.round((conf.value ?? 0) * 100)}%)
          {conf.basis ? ` — ${conf.basis}` : ''}
          {data.learning_note ? ` · ${data.learning_note}` : ''}
        </p>
      )}

      <p className="text-[10px] italic text-wb-ink2">Advisory only. You decide what happens next.</p>
    </div>
  );
}

/** "Pull apart the reasoning" (mission §8) — the same specialist perspectives
 * grouped into a small, honest set of user-facing lenses. Evidence is kept
 * in its own tab, sourced from the canonical engines, never attributed to a
 * specialist. */
export function PullApartReasoning({
  data,
  openGroup,
  onOpenGroup,
  recommendations,
  investigation,
}: {
  data: AdvisoryResult;
  openGroup: ReasoningGroup | null;
  onOpenGroup: (g: ReasoningGroup | null) => void;
  recommendations: RecommendationPackage | null;
  investigation: InvestigationRunResult | null;
}) {
  const perspectives = data.officer_perspectives ?? [];
  const grouped = groupPerspectives(perspectives);
  const hasEvidence = !!recommendations?.recommendations.length || !!investigation || (data.historical_evidence?.length ?? 0) > 0;
  const tabs: ReasoningGroup[] = [...REASONING_GROUP_ORDER.filter((g) => (grouped.get(g)?.length ?? 0) > 0), ...(hasEvidence ? (['Evidence'] as ReasoningGroup[]) : [])];

  if (tabs.length === 0) {
    return <p className="text-xs text-wb-ink2">No specialist perspectives were retrieved for this question.</p>;
  }

  const active = openGroup && tabs.includes(openGroup) ? openGroup : tabs[0];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Reasoning groups">
        {tabs.map((g) => (
          <button key={g} role="tab" aria-selected={active === g} onClick={() => onOpenGroup(g)}
            className={`rounded-md border px-3 py-1 text-[10px] uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-wb-sage-deep ${active === g ? 'border-wb-sage-deep bg-wb-sage-deep/15 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:border-wb-sage-deep/40 hover:text-wb-ink'}`}>
            {g}
          </button>
        ))}
      </div>

      {active === 'Evidence' ? (
        <EvidencePanel recommendations={recommendations} investigation={investigation} historicalEvidence={data.historical_evidence} />
      ) : (
        <div className="space-y-2">
          {(grouped.get(active) ?? []).map((op, i) => {
            const advisor = COUNCIL.find((a) => a.label.toLowerCase() === op.officer?.toLowerCase());
            const accentClass = advisor?.dissent ? 'text-wb-crit-on' : 'text-wb-sage-deep';
            const stance = op.stance ?? '';
            const stanceColor = stance === 'supports' ? 'text-wb-ok-on' : stance === 'cautions' || stance === 'challenges' ? 'text-wb-warn-on' : 'text-wb-ink2';
            return (
              <div key={i} className="space-y-1.5 rounded-md border border-wb-line bg-wb-bg px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <p className={`text-[11px] font-semibold uppercase tracking-wider ${accentClass}`}>{op.officer}</p>
                  {stance && <span className={`text-[9px] uppercase tracking-widest ${stanceColor}`}>{stance}</span>}
                </div>
                <p className="text-sm leading-relaxed text-wb-ink/85">{op.recommendation}</p>
                {op.confidence !== undefined && <p className="text-[9px] text-wb-ink2">Confidence: {op.confidence}%</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
