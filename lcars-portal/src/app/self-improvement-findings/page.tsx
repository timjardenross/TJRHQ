'use client';

import { useEffect, useMemo, useState } from 'react';
import { WorkbenchShell, Card, Badge, Tabs, STATUS_CLASSES, toneToStatus } from '@/components/ui';
import { severityToTone, decisionToTone, lifecycleStateToTone } from '@/lib/departments';
import { OpportunityCard } from './_components/OpportunityCard';
import { OpportunityDetail } from './_components/OpportunityDetail';
import {
  CHANGE_CLASS_LABEL,
  MISSION_ONLY_CLASSES,
  type ChangeClass,
  type EvolutionSummary,
  type Investigation,
  type LegacyFinding,
  type Opportunity,
  type OpportunityDecisionType,
} from './_components/types';

// HQ Evolution (retitled from Self-Improvement Findings — see
// docs/self-improvement/HQ-EVOLUTION.md). The existing evidence/policy/
// remediation engine (EvidenceCollector -> model analysis -> PolicyEngine
// -> Finding -> human decision -> auto-remediation) is preserved
// unmodified and now lives inside the "Improve" tab's bounded-remediation
// section; everything else here is additive (Discover/Investigate/Learned,
// the opportunity model, internal+external discovery).
//
// Section 36: polling relaxed from every 5s to a much lower cadence — this
// is an overnight-cycle-fed surface, not a live terminal — with the same
// hidden-tab pause behaviour, plus a manual refresh action.

type TabKey = 'discover' | 'investigate' | 'improve' | 'learned';

const REFRESH_MS = 60_000;

function usePolling(load: () => void) {
  useEffect(() => {
    load();
    let interval: ReturnType<typeof setInterval> | null = null;
    function start() { if (!interval) interval = setInterval(load, REFRESH_MS); }
    function stop() { if (interval) { clearInterval(interval); interval = null; } }
    function onVisibilityChange() { if (document.hidden) stop(); else { load(); start(); } }
    if (!document.hidden) start();
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => { stop(); document.removeEventListener('visibilitychange', onVisibilityChange); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

export default function HqEvolutionPage() {
  const [tab, setTab] = useState<TabKey>('discover');
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [summary, setSummary] = useState<EvolutionSummary | null>(null);
  const [legacyFindings, setLegacyFindings] = useState<LegacyFinding[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reasoning, setReasoning] = useState('');

  async function loadAll() {
    try {
      const [oppRes, summaryRes, findingsRes] = await Promise.all([
        fetch('/api/self-improvement/opportunities'),
        fetch('/api/self-improvement/evolution-summary'),
        fetch('/api/self-improvement/findings'),
      ]);
      const oppBody = await oppRes.json();
      const summaryBody = await summaryRes.json();
      const findingsBody = await findingsRes.json();
      if (!oppRes.ok) throw new Error(typeof oppBody?.error === 'string' ? oppBody.error : 'Failed to load opportunities');

      setOpportunities(oppBody.opportunities || []);
      setSummary(summaryRes.ok ? summaryBody : null);
      setLegacyFindings(findingsBody.findings || []);
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('[HQ Evolution] load failed:', err);
      setError(err instanceof Error ? err.message : 'Failed to load HQ Evolution data');
      setLoading(false);
    }
  }

  usePolling(loadAll);

  async function decide(opportunityId: string, decisionType: OpportunityDecisionType, reasoningText?: string, missionId?: string) {
    try {
      const res = await fetch('/api/self-improvement/opportunities/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opportunity_id: opportunityId, decision_type: decisionType, reasoning: reasoningText, mission_id: missionId }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body?.error === 'string' ? body.error : 'Failed to save decision');
      setReasoning('');
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save decision');
    }
  }

  async function createMissionFor(opportunity: Opportunity) {
    try {
      const description = [
        opportunity.summary,
        opportunity.why_relevant ? `Why HQ is looking at this: ${opportunity.why_relevant}` : '',
        opportunity.investigation?.recommendation_rationale ? `HQ assessment: ${opportunity.investigation.recommendation_rationale}` : '',
      ].filter(Boolean).join('\n\n');

      const res = await fetch('/api/missions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: opportunity.title, description, status: 'Idea', created_by: 'hq-evolution' }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body?.error === 'string' ? body.error : 'Failed to create Mission');
      await decide(opportunity.opportunity_id, 'create_mission', 'Handed off to Mission for controlled implementation.', body.mission?.mission_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create Mission');
    }
  }

  async function makeLegacyDecision(decision: 'approved' | 'rejected' | 'more_evidence') {
    if (!selectedFindingId) return;
    try {
      const res = await fetch('/api/self-improvement/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ finding_id: selectedFindingId, decision, reasoning }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body?.error === 'string' ? body.error : 'Failed to save decision');
      setReasoning('');
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save decision');
    }
  }

  const proposed = useMemo(() => opportunities.filter((o) => o.lifecycle_state === 'proposed'), [opportunities]);
  const investigating = useMemo(() => opportunities.filter((o) => o.lifecycle_state === 'investigating'), [opportunities]);
  const watching = useMemo(() => opportunities.filter((o) => o.lifecycle_state === 'watching'), [opportunities]);
  const learned = useMemo(() => opportunities.filter((o) => o.lifecycle_state === 'learned'), [opportunities]);
  const historical = useMemo(
    () => opportunities.filter((o) => ['approved', 'implementing', 'verifying', 'rejected', 'resolved_before_research'].includes(o.lifecycle_state)),
    [opportunities],
  );
  const discoveredOnly = useMemo(() => opportunities.filter((o) => o.lifecycle_state === 'discovered'), [opportunities]);
  const radarCounts = useMemo(() => {
    const counts: Partial<Record<ChangeClass, number>> = {};
    for (const o of opportunities) {
      if (o.lifecycle_state === 'rejected') continue;
      counts[o.change_class] = (counts[o.change_class] ?? 0) + 1;
    }
    return counts;
  }, [opportunities]);

  const selected = opportunities.find((o) => o.opportunity_id === selectedId) || null;
  const selectedLegacyFinding = legacyFindings.find((f) => f.finding_id === selectedFindingId) || null;
  const pendingLegacyCount = legacyFindings.filter((f) => !f.decision).length;

  function reviewOpportunity(o: Opportunity) {
    setSelectedId(o.opportunity_id);
    if (o.lifecycle_state === 'proposed') setTab('improve');
    else if (o.lifecycle_state === 'investigating') setTab('investigate');
    else setTab('discover');
  }

  if (loading) {
    return (
      <WorkbenchShell title="HQ Evolution" eyebrow="HQ works on HQ while you're away" tagline="USS TJR · HQ Evolution · Continuous discovery, investigation, and improvement">
        <div className="text-center py-8 text-wb-ink2">Checking overnight discoveries…</div>
      </WorkbenchShell>
    );
  }

  return (
    <WorkbenchShell
      title="HQ Evolution"
      eyebrow="HQ works on HQ while you're away"
      tagline="USS TJR · HQ Evolution · Discover, investigate, improve, learn — nothing changes production without your say"
      wide
      tabs={
        <Tabs
          ariaLabel="HQ Evolution sections"
          active={tab}
          onChange={setTab}
          tabs={[
            { key: 'discover', label: `Discover${proposed.length ? ` (${proposed.length})` : ''}` },
            { key: 'investigate', label: `Investigate${investigating.length ? ` (${investigating.length})` : ''}` },
            { key: 'improve', label: `Improve${proposed.length + pendingLegacyCount ? ` (${proposed.length + pendingLegacyCount})` : ''}` },
            { key: 'learned', label: 'Learned' },
          ]}
        />
      }
    >
      {error && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          {error}. Showing last known data, not current.
        </p>
      )}

      {tab === 'discover' && (
        <DiscoverTab
          summary={summary}
          proposed={proposed}
          discoveredOnly={discoveredOnly}
          radarCounts={radarCounts}
          onReview={reviewOpportunity}
        />
      )}

      {tab === 'investigate' && (
        <InvestigateTab
          investigating={investigating}
          watching={watching}
          selected={selected}
          onSelect={setSelectedId}
          onDecide={decide}
        />
      )}

      {tab === 'improve' && (
        <ImproveTab
          proposed={proposed}
          selected={selected}
          onSelect={setSelectedId}
          onDecide={decide}
          onCreateMission={createMissionFor}
          legacyFindings={legacyFindings}
          selectedLegacyFinding={selectedLegacyFinding}
          onSelectLegacyFinding={setSelectedFindingId}
          reasoning={reasoning}
          setReasoning={setReasoning}
          onLegacyDecision={makeLegacyDecision}
        />
      )}

      {tab === 'learned' && <LearnedTab learned={learned} historical={historical} onDecide={decide} />}

      <div className="text-center text-xs text-wb-ink2 mt-8">
        Refreshes automatically every minute while this tab is visible ·{' '}
        <button onClick={() => loadAll()} className="underline hover:no-underline">Refresh now</button>
      </div>
    </WorkbenchShell>
  );
}

// ── Discover ────────────────────────────────────────────────────────────

function DiscoverTab({
  summary, proposed, discoveredOnly, radarCounts, onReview,
}: {
  summary: EvolutionSummary | null;
  proposed: Opportunity[];
  discoveredOnly: Opportunity[];
  radarCounts: Partial<Record<ChangeClass, number>>;
  onReview: (o: Opportunity) => void;
}) {
  const grouped = useMemo(() => {
    const byClass = new Map<ChangeClass, Opportunity[]>();
    for (const o of proposed) {
      const list = byClass.get(o.change_class) ?? [];
      list.push(o);
      byClass.set(o.change_class, list);
    }
    return byClass;
  }, [proposed]);

  return (
    <div className="space-y-6">
      <Card>
        {!summary || !summary.has_run_yet ? (
          <p className="text-sm text-wb-ink2">HQ Evolution has not completed an overnight cycle yet — nothing to show.</p>
        ) : summary.nothing_worth_changing ? (
          <>
            <p className="text-lg font-serif text-wb-ink">Nothing worth changing today.</p>
            <p className="mt-1 text-sm text-wb-ink2">
              HQ investigated {summary.investigated_count} possibilit{summary.investigated_count === 1 ? 'y' : 'ies'} overnight —
              none cleared the value/relevance threshold.
            </p>
          </>
        ) : (
          <>
            <p className="text-lg font-serif text-wb-ink">
              HQ investigated {summary.investigated_count} possibilit{summary.investigated_count === 1 ? 'y' : 'ies'} overnight.
            </p>
            <p className="mt-1 text-sm text-wb-ink2">
              {summary.worth_considering_count} {summary.worth_considering_count === 1 ? 'is' : 'are'} worth considering.
            </p>
          </>
        )}
        {!!summary?.outcomes_completed_count && summary.outcomes_completed_count > 0 && (
          <p className="mt-1 text-xs text-wb-ink2">
            {summary.outcomes_completed_count} previous improvement{summary.outcomes_completed_count === 1 ? '' : 's'} verified overnight.
          </p>
        )}
      </Card>

      {[...grouped.entries()].map(([changeClass, items]) => (
        <div key={changeClass}>
          <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">
            {CHANGE_CLASS_LABEL[changeClass]}
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {items.map((o) => (
              <Card key={o.opportunity_id}>
                <div className="font-semibold text-sm text-wb-ink mb-1">{o.title}</div>
                {o.value && <div className="text-xs text-wb-ink2 mb-1">Potential value: <span className="capitalize">{o.value}</span></div>}
                {o.cost_impact && <div className="text-xs text-wb-ink2 mb-1">Cost impact: <span className="capitalize">{o.cost_impact}</span></div>}
                {o.complexity && <div className="text-xs text-wb-ink2 mb-2">Complexity: <span className="capitalize">{o.complexity}</span></div>}
                {o.why_relevant && <p className="text-xs text-wb-ink2 mb-3">{o.why_relevant}</p>}
                <button
                  onClick={() => onReview(o)}
                  className="text-xs font-semibold text-wb-sage-deep hover:underline"
                >
                  Review →
                </button>
              </Card>
            ))}
          </div>
        </div>
      ))}

      {discoveredOnly.length > 0 && (
        <p className="text-xs text-wb-ink2">
          {discoveredOnly.length} other candidate{discoveredOnly.length === 1 ? '' : 's'} cleared the relevance gate but
          didn&apos;t reach deep investigation this cycle — HQ will reconsider {discoveredOnly.length === 1 ? 'it' : 'them'}
          {' '}alongside new evidence in a future cycle.
        </p>
      )}

      {Object.keys(radarCounts).length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs uppercase text-wb-ink2 tracking-wider font-semibold">HQ Radar</summary>
          <div className="mt-3 flex flex-wrap gap-2">
            {(Object.entries(radarCounts) as [ChangeClass, number][]).map(([changeClass, count]) => (
              <span key={changeClass} className="text-xs bg-wb-line text-wb-ink2 px-2 py-1 rounded">
                {CHANGE_CLASS_LABEL[changeClass]}: {count}
              </span>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

const RELATIONSHIP_LABEL: Record<string, string> = {
  learned: 'Learned',
  rejected: 'Rejected',
  watching: 'Watching',
  resolved_before_research: 'Already checked',
};

/** Secondary, subordinate context — HQ's memory of similar past work — shown
 * beneath an investigation's own evidence, never competing with it. */
function RelatedExperienceBlock({ investigation }: { investigation?: Investigation }) {
  const items = investigation?.related_experience ?? [];
  const summaryText = investigation?.related_experience_summary;
  if (!summaryText && items.length === 0) return null;

  return (
    <div className="mb-4 text-xs text-wb-ink2">
      <h4 className="uppercase tracking-wider font-semibold mb-1">Related HQ experience</h4>
      {summaryText ? (
        <p>{summaryText}</p>
      ) : (
        <ul className="list-disc pl-4 space-y-1">
          {items.map((item) => {
            const detail = item.outcome_summary || item.rejection_reason || item.watch_reason || item.resolution_note || item.future_implication;
            return (
              <li key={item.opportunity_id}>
                <span className="font-semibold text-wb-ink2">{item.title}</span>
                {' — '}
                {RELATIONSHIP_LABEL[item.relationship] ?? item.relationship}
                {detail ? `: ${detail}` : ''}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ── Investigate ─────────────────────────────────────────────────────────

function InvestigateTab({
  investigating, watching, selected, onSelect, onDecide,
}: {
  investigating: Opportunity[];
  watching: Opportunity[];
  selected: Opportunity | null;
  onSelect: (id: string) => void;
  onDecide: (id: string, type: OpportunityDecisionType, reasoning?: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
      <div className="col-span-1 space-y-4">
        <Card title="Active investigations">
          {investigating.length === 0 ? (
            <p className="text-sm text-wb-ink2">Nothing currently being investigated.</p>
          ) : (
            <div className="space-y-2">
              {investigating.map((o) => (
                <OpportunityCard key={o.opportunity_id} opportunity={o} selected={selected?.opportunity_id === o.opportunity_id} onSelect={() => onSelect(o.opportunity_id)} />
              ))}
            </div>
          )}
        </Card>

        {watching.length > 0 && (
          <details>
            <summary className="cursor-pointer text-xs uppercase text-wb-ink2 tracking-wider font-semibold px-1">
              Watching ({watching.length})
            </summary>
            <div className="mt-2 space-y-2">
              {watching.map((o) => (
                <OpportunityCard key={o.opportunity_id} opportunity={o} selected={selected?.opportunity_id === o.opportunity_id} onSelect={() => onSelect(o.opportunity_id)} />
              ))}
            </div>
          </details>
        )}
      </div>

      <div className="col-span-2">
        {selected ? (
          <OpportunityDetail
            opportunity={selected}
            actions={
              <div className="pt-2">
                <RelatedExperienceBlock investigation={selected.investigation} />
                <div className="flex gap-2 flex-wrap">
                  <button onClick={() => onDecide(selected.opportunity_id, 'turn_into_improvement')} className="px-4 py-2 rounded bg-wb-ok text-wb-ok-on font-semibold text-sm hover:opacity-90">
                    Turn into improvement
                  </button>
                  <button onClick={() => onDecide(selected.opportunity_id, 'keep_watching', 'Promising but premature')} className="px-4 py-2 rounded bg-wb-warn text-wb-warn-on font-semibold text-sm hover:opacity-90">
                    Keep watching
                  </button>
                  <button onClick={() => onDecide(selected.opportunity_id, 'not_useful', 'Not useful')} className="px-4 py-2 rounded bg-wb-crit text-wb-crit-on font-semibold text-sm hover:opacity-90">
                    Not useful
                  </button>
                </div>
              </div>
            }
          />
        ) : (
          <Card title="Investigation"><div className="text-center py-12 text-wb-ink2">Select an item to review its investigation record.</div></Card>
        )}
      </div>
    </div>
  );
}

// Mirrors the Python-side outcome_contract builder — display-only preview of
// what approval will commit HQ to measuring; the real contract is created
// server-side on approval and rendered from OpportunityDetail's "What HQ
// committed to measure" field once it exists.
const MEASUREMENT_TYPE_BY_CLASS: Record<string, string> = {
  maintenance: 'deterministic', configuration: 'deterministic',
  reliability: 'quantitative', cost_optimisation: 'quantitative',
  capability: 'mixed', product_improvement: 'mixed', architecture: 'mixed',
};
const OBSERVATION_WINDOW_BY_CLASS: Record<string, string> = {
  maintenance: 'Immediate verification', configuration: 'Immediate verification',
  reliability: '5 completed HQ Evolution cycles', cost_optimisation: '7 completed HQ Evolution cycles',
  capability: '7 completed HQ Evolution cycles', product_improvement: '7 completed HQ Evolution cycles',
  architecture: '14 completed HQ Evolution cycles',
};

function ApprovalPreview({ opportunity }: { opportunity: Opportunity }) {
  const measurementType = MEASUREMENT_TYPE_BY_CLASS[opportunity.change_class] ?? 'unknown';
  const observationWindow = OBSERVATION_WINDOW_BY_CLASS[opportunity.change_class] ?? 'an observation period';
  const expected = opportunity.investigation?.why_hq_is_looking_at_this || opportunity.why_relevant;

  return (
    <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-xs text-wb-ink space-y-1">
      <h4 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-1">If you approve this</h4>
      {expected && <div>Expected: {expected}</div>}
      <div>HQ will verify: implementation succeeds, then observe for {observationWindow}.</div>
      <div>Measurement type: {measurementType}.</div>
      <div>Then: HQ will report whether the improvement was observed.</div>
    </div>
  );
}

// ── Improve ─────────────────────────────────────────────────────────────

function ImproveTab({
  proposed, selected, onSelect, onDecide, onCreateMission,
  legacyFindings, selectedLegacyFinding, onSelectLegacyFinding, reasoning, setReasoning, onLegacyDecision,
}: {
  proposed: Opportunity[];
  selected: Opportunity | null;
  onSelect: (id: string) => void;
  onDecide: (id: string, type: OpportunityDecisionType, reasoning?: string) => void;
  onCreateMission: (o: Opportunity) => void;
  legacyFindings: LegacyFinding[];
  selectedLegacyFinding: LegacyFinding | null;
  onSelectLegacyFinding: (id: string) => void;
  reasoning: string;
  setReasoning: (v: string) => void;
  onLegacyDecision: (decision: 'approved' | 'rejected' | 'more_evidence') => void;
}) {
  const isMissionOnly = selected ? MISSION_ONLY_CLASSES.includes(selected.change_class) : false;

  return (
    <div className="space-y-10">
      <div>
        <h2 className="text-sm font-semibold text-wb-ink mb-3">Needs your decision — HQ Evolution opportunities</h2>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="col-span-1">
            <Card title="Proposed">
              {proposed.length === 0 ? (
                <p className="text-sm text-wb-ink2">Nothing awaiting a decision right now.</p>
              ) : (
                <div className="space-y-2">
                  {proposed.map((o) => (
                    <OpportunityCard key={o.opportunity_id} opportunity={o} selected={selected?.opportunity_id === o.opportunity_id} onSelect={() => onSelect(o.opportunity_id)} />
                  ))}
                </div>
              )}
            </Card>
          </div>
          <div className="col-span-2">
            {selected && proposed.some((o) => o.opportunity_id === selected.opportunity_id) ? (
              <OpportunityDetail
                opportunity={selected}
                actions={
                  <div className="space-y-3 pt-2">
                    {!isMissionOnly && (
                      <>
                        <ApprovalPreview opportunity={selected} />
                        <p className="text-xs text-wb-ink2">
                          Approving authorises HQ to apply the bounded remediation described above, run verification, and
                          roll back on verification failure. No broader changes are authorised.
                        </p>
                      </>
                    )}
                    <div className="flex gap-2 flex-wrap">
                      {!isMissionOnly && (
                        <button onClick={() => onDecide(selected.opportunity_id, 'approve_improvement', 'Approved')} className="px-4 py-2 rounded bg-wb-ok text-wb-ok-on font-semibold text-sm hover:opacity-90">
                          Approve improvement
                        </button>
                      )}
                      <button onClick={() => onCreateMission(selected)} className="px-4 py-2 rounded bg-wb-sage-deep text-white font-semibold text-sm hover:opacity-90">
                        Create Mission
                      </button>
                      <button onClick={() => onDecide(selected.opportunity_id, 'more_evidence', 'Needs more evidence before a decision')} className="px-4 py-2 rounded bg-wb-warn text-wb-warn-on font-semibold text-sm hover:opacity-90">
                        Get more evidence
                      </button>
                      <button onClick={() => onDecide(selected.opportunity_id, 'reject', 'Rejected')} className="px-4 py-2 rounded bg-wb-crit text-wb-crit-on font-semibold text-sm hover:opacity-90">
                        Reject
                      </button>
                    </div>
                  </div>
                }
              />
            ) : (
              <Card title="Proposed improvement"><div className="text-center py-12 text-wb-ink2">Select a proposed opportunity to decide.</div></Card>
            )}
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-wb-ink mb-1">Bounded remediation queue</h2>
        <p className="text-xs text-wb-ink2 mb-3">
          The existing evidence/PolicyEngine/remediation pipeline — unchanged. Approving here authorises real, tested,
          rollback-guarded changes for low-risk findings only; nothing here is new HQ Evolution behaviour.
        </p>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="col-span-1">
            <Card title="Findings">
              {legacyFindings.length === 0 ? (
                <p className="text-sm text-wb-ink2">No findings from the latest cycle.</p>
              ) : (
                <div className="space-y-2">
                  {legacyFindings.map((f) => (
                    <button
                      key={f.finding_id}
                      onClick={() => onSelectLegacyFinding(f.finding_id)}
                      className={`w-full text-left p-3 rounded border transition-colors ${
                        selectedLegacyFinding?.finding_id === f.finding_id ? 'bg-wb-surface border-wb-sage-deep' : 'bg-wb-bg border-wb-line hover:border-wb-sage-deep'
                      }`}
                    >
                      <div className="font-semibold text-sm text-wb-ink">{f.title}</div>
                      <div className="flex gap-2 mt-2 flex-wrap">
                        <span className="text-xs bg-wb-line text-wb-ink2 px-2 py-1 rounded">{f.category}</span>
                        <Badge status={toneToStatus(severityToTone(f.severity))}>{f.severity}</Badge>
                        {f.decision && <Badge status={toneToStatus(decisionToTone(f.decision))}>{f.decision.replace('_', ' ')}</Badge>}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </Card>
          </div>
          <div className="col-span-2">
            {selectedLegacyFinding ? (
              <Card title="Finding details">
                <h3 className="text-lg font-serif text-wb-ink mb-4">{selectedLegacyFinding.title}</h3>
                <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-sm text-wb-ink mb-4">
                  <div>Category: <strong>{selectedLegacyFinding.category}</strong></div>
                  <div>Severity: <strong>{selectedLegacyFinding.severity}</strong></div>
                  <div>Risk: <strong>{selectedLegacyFinding.risk_level || 'N/A'}</strong></div>
                  <div>Confidence: <strong>{(selectedLegacyFinding.confidence * 100).toFixed(0)}%</strong></div>
                </div>
                <p className="text-sm text-wb-ink mb-4">{selectedLegacyFinding.description}</p>
                <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-sm text-wb-ink mb-4">
                  <strong>{selectedLegacyFinding.proposed_action.type}:</strong> {selectedLegacyFinding.proposed_action.description}
                </div>
                {!selectedLegacyFinding.decision ? (
                  <>
                    <textarea
                      value={reasoning}
                      onChange={(e) => setReasoning(e.target.value)}
                      placeholder="Add reasoning (optional)..."
                      className="w-full p-2 rounded border border-wb-line bg-wb-bg text-wb-ink text-sm mb-3 font-mono"
                      rows={3}
                    />
                    <div className="flex gap-2">
                      <button onClick={() => onLegacyDecision('approved')} className="flex-1 px-4 py-2 rounded bg-wb-ok text-wb-ok-on font-semibold text-sm hover:opacity-90">Approve</button>
                      <button onClick={() => onLegacyDecision('more_evidence')} className="flex-1 px-4 py-2 rounded bg-wb-warn text-wb-warn-on font-semibold text-sm hover:opacity-90">More Evidence</button>
                      <button onClick={() => onLegacyDecision('rejected')} className="flex-1 px-4 py-2 rounded bg-wb-crit text-wb-crit-on font-semibold text-sm hover:opacity-90">Reject</button>
                    </div>
                  </>
                ) : (
                  <div className={`p-3 rounded ${STATUS_CLASSES[toneToStatus(decisionToTone(selectedLegacyFinding.decision))]} text-sm font-semibold`}>
                    Decision: {selectedLegacyFinding.decision.replace('_', ' ').toUpperCase()}
                  </div>
                )}
              </Card>
            ) : (
              <Card title="Finding details"><div className="text-center py-12 text-wb-ink2">Select a finding to review</div></Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Learned ─────────────────────────────────────────────────────────────

const LEARNED_FILTERS: { key: string; label: string; result: string | null }[] = [
  { key: 'all', label: 'All', result: null },
  { key: 'improved', label: 'Improved', result: 'improved' },
  { key: 'no_material_change', label: 'No material change', result: 'no_material_change' },
  { key: 'regressed', label: 'Regressed', result: 'regressed' },
  { key: 'inconclusive', label: 'Inconclusive', result: 'inconclusive' },
];

function LearnedTab({
  learned, historical, onDecide,
}: {
  learned: Opportunity[];
  historical: Opportunity[];
  onDecide: (id: string, type: OpportunityDecisionType, reasoning?: string) => void;
}) {
  const [filter, setFilter] = useState('all');
  const activeFilter = LEARNED_FILTERS.find((f) => f.key === filter) ?? LEARNED_FILTERS[0];
  const filteredLearned = useMemo(
    () => (activeFilter.result ? learned.filter((o) => o.outcome?.outcome_result === activeFilter.result) : learned),
    [learned, activeFilter],
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-wb-ink mb-3">Recent improvements</h2>
        <div className="flex gap-2 flex-wrap mb-4">
          {LEARNED_FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded border px-3 py-1.5 text-xs transition-colors ${
                filter === f.key
                  ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep'
                  : 'border-wb-line text-wb-ink2 hover:text-wb-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {filteredLearned.length === 0 ? (
          <Card>
            <p className="text-sm text-wb-ink2">
              {filter === 'all'
                ? 'No improvements have completed their observation period yet.'
                : `No opportunities with outcome '${activeFilter.label}' yet.`}
            </p>
          </Card>
        ) : (
          <div className="space-y-4">
            {filteredLearned.map((o) => <OpportunityDetail key={o.opportunity_id} opportunity={o} />)}
          </div>
        )}
      </div>

      {historical.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs uppercase text-wb-ink2 tracking-wider font-semibold">
            Historical decisions / changes ({historical.length})
          </summary>
          <div className="mt-3 space-y-2">
            {historical.map((o) => {
              const canMarkImplemented = ['approved', 'implementing'].includes(o.lifecycle_state)
                && !!o.outcome_contract && 'expected_benefit' in o.outcome_contract;
              return (
                <div key={o.opportunity_id} className="p-3 rounded border border-wb-line bg-wb-bg text-sm text-wb-ink flex items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold">{o.title}</div>
                    <div className="text-xs text-wb-ink2">{CHANGE_CLASS_LABEL[o.change_class]} · updated {new Date(o.updated_at).toLocaleDateString()}</div>
                    {canMarkImplemented && (
                      <p className="text-xs text-wb-ink2 mt-1">
                        Not yet auto-remediated (needs a human to apply this directly). Once you&apos;ve made the change
                        yourself, confirm it below so HQ can start observing whether it actually helped.
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {canMarkImplemented && (
                      <button
                        onClick={() => onDecide(o.opportunity_id, 'mark_implemented', 'Manually implemented by the Captain')}
                        className="px-3 py-1.5 rounded bg-wb-sage-deep text-white text-xs font-semibold hover:opacity-90"
                      >
                        Mark implemented
                      </button>
                    )}
                    <Badge status={toneToStatus(lifecycleStateToTone(o.lifecycle_state))}>{o.lifecycle_state.replace('_', ' ')}</Badge>
                  </div>
                </div>
              );
            })}
          </div>
        </details>
      )}
    </div>
  );
}
