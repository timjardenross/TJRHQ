'use client';

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card, Badge, STATUS_CLASSES, type BadgeStatus } from '@/components/ui';

interface Finding {
  finding_id: string;
  category: string;
  title: string;
  description: string;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  risk_level: string;
  confidence: number;
  evidence: Array<{ type: string; observation: string; location?: string }>;
  proposed_action: { type: string; description: string };
  decision?: 'approved' | 'rejected' | 'more_evidence';
}

interface Decision {
  finding_id: string;
  decision: 'approved' | 'rejected' | 'more_evidence';
  reasoning: string;
  timestamp: string;
}

// This page's severity/decision vocabularies are its own (part of the
// tracked severity-vocab sprawl, docs/UI-Layer-Debt-Handoff-2026-08-29
// Finding 1) — riskClass/RiskPill only recognize RED/AMBER/GREEN/HIGH/
// MEDIUM/LOW and silently rendered everything else as neutral grey,
// flattening the one signal (severity/decision) this triage UI exists to
// show. Mapped onto Badge's own status vocabulary directly here rather
// than reusing riskClass/RiskPill, until the full taxonomy migration lands.
const SEVERITY_STATUS: Record<Finding['severity'], BadgeStatus> = {
  info: 'neutral',
  low: 'success',
  medium: 'warning',
  high: 'warning',
  critical: 'error',
};

const DECISION_STATUS: Record<Decision['decision'], BadgeStatus> = {
  approved: 'success',
  rejected: 'error',
  more_evidence: 'warning',
};

export default function SelfImprovementFindings() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [decisions, setDecisions] = useState<Map<string, Decision>>(new Map());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reasoning, setReasoning] = useState('');

  useEffect(() => {
    loadFindings();
    // Visibility-gated: an unreachable backend previously meant one failed
    // fetch every 5s forever, tab visible or not (WORKBENCH-REVIEW.md H10,
    // 2026-07-18). Pause while hidden, refresh immediately on return rather
    // than waiting up to 5s for the next tick.
    let interval: ReturnType<typeof setInterval> | null = null;
    function start() {
      if (interval) return;
      interval = setInterval(loadFindings, 5000);
    }
    function stop() {
      if (interval) { clearInterval(interval); interval = null; }
    }
    function onVisibilityChange() {
      if (document.hidden) { stop(); } else { loadFindings(); start(); }
    }
    if (!document.hidden) start();
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  async function loadFindings() {
    try {
      const res = await fetch('/api/self-improvement/findings');
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data?.error === 'string' ? data.error : 'Failed to load findings');

      setFindings(data.findings || []);
      setError(null);

      const decisionMap = new Map<string, Decision>();
      for (const f of data.findings || []) {
        if (f.decision) {
          decisionMap.set(f.finding_id, {
            finding_id: f.finding_id,
            decision: f.decision,
            reasoning: f.decision_reasoning || '',
            timestamp: new Date().toISOString(),
          });
        }
      }
      setDecisions(decisionMap);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load findings:', err);
      setError(err instanceof Error ? err.message : 'Failed to load findings');
      setLoading(false);
    }
  }

  async function makeDecision(decision: 'approved' | 'rejected' | 'more_evidence') {
    if (!selectedId) return;
    try {
      const res = await fetch('/api/self-improvement/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          finding_id: selectedId,
          decision,
          reasoning,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body?.error === 'string' ? body.error : 'Failed to save decision');
      setReasoning('');
      await loadFindings();
    } catch (err) {
      console.error('Failed to save decision:', err);
      setError(err instanceof Error ? err.message : 'Failed to save decision');
    }
  }

  const selectedFinding = findings.find((f) => f.finding_id === selectedId);
  const pendingCount = findings.filter((f) => !f.decision).length;

  if (loading) {
    return (
      <WorkbenchShell title="Self-Improvement Findings" eyebrow="Automated Discovery" tagline="USS TJR · Self-Improvement · Findings, decisions, and audit trail">
        <div className="text-center py-8 text-wb-ink2">Loading findings...</div>
      </WorkbenchShell>
    );
  }

  return (
    <WorkbenchShell title="Self-Improvement Findings" eyebrow="Automated Discovery" tagline="USS TJR · Self-Improvement · Findings, decisions, and audit trail">
      {error && (
        <p className="mb-4 rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">
          {error}. Showing last known data, not current.
        </p>
      )}
      <div className="grid grid-cols-2 gap-4 mb-8 sm:grid-cols-4">
        <Card>
          <div className="text-3xl font-semibold text-wb-ink">{findings.length}</div>
          <div className="text-sm text-wb-ink2 mt-1">Total Findings</div>
        </Card>
        <Card>
          <div className="text-3xl font-semibold text-wb-ok">{findings.filter((f) => f.decision === 'approved').length}</div>
          <div className="text-sm text-wb-ink2 mt-1">Approved</div>
        </Card>
        <Card>
          <div className="text-3xl font-semibold text-wb-crit">{findings.filter((f) => f.decision === 'rejected').length}</div>
          <div className="text-sm text-wb-ink2 mt-1">Rejected</div>
        </Card>
        <Card>
          <div className="text-3xl font-semibold text-wb-warn">{pendingCount}</div>
          <div className="text-sm text-wb-ink2 mt-1">Pending Review</div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {/* Findings List */}
        <div className="col-span-1">
          <Card title="Findings">
            <div className="space-y-2">
              {findings.map((f) => (
                <button
                  key={f.finding_id}
                  onClick={() => setSelectedId(f.finding_id)}
                  className={`w-full text-left p-3 rounded border transition-colors ${
                    selectedId === f.finding_id
                      ? 'bg-wb-surface border-wb-sage-deep'
                      : 'bg-wb-bg border-wb-line hover:border-wb-sage-deep'
                  }`}
                >
                  <div className="font-semibold text-sm text-wb-ink">{f.title}</div>
                  <div className="flex gap-2 mt-2 flex-wrap">
                    <span className="text-xs bg-wb-line text-wb-ink2 px-2 py-1 rounded">{f.category}</span>
                    <Badge status={SEVERITY_STATUS[f.severity]}>{f.severity}</Badge>
                    {f.decision && (
                      <Badge status={DECISION_STATUS[f.decision]}>{f.decision.replace('_', ' ')}</Badge>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </Card>
        </div>

        {/* Finding Details */}
        <div className="col-span-2">
          {selectedFinding ? (
            <Card title="Finding Details">
              <h2 className="text-2xl font-serif text-wb-ink mb-6">{selectedFinding.title}</h2>

              <section className="mb-6">
                <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">Category</h3>
                <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-wb-ink">
                  {selectedFinding.category}
                </div>
              </section>

              <section className="mb-6">
                <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">Severity & Confidence</h3>
                <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-sm text-wb-ink">
                  <div>Severity: <strong>{selectedFinding.severity}</strong></div>
                  <div>Risk: <strong>{selectedFinding.risk_level || 'N/A'}</strong></div>
                  <div>Confidence: <strong>{(selectedFinding.confidence * 100).toFixed(0)}%</strong></div>
                </div>
              </section>

              <section className="mb-6">
                <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">Description</h3>
                <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-sm text-wb-ink">
                  {selectedFinding.description}
                </div>
              </section>

              <section className="mb-6">
                <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">Evidence</h3>
                <div className="space-y-2">
                  {selectedFinding.evidence.map((e, i) => (
                    <div key={i} className="bg-wb-bg p-3 rounded border-l-4 border-wb-line text-sm text-wb-ink">
                      <strong className="text-wb-sage-deep">{e.type}:</strong> {e.observation}
                      {e.location && <div className="text-xs text-wb-ink2 mt-1">{e.location}</div>}
                    </div>
                  ))}
                </div>
              </section>

              <section className="mb-6">
                <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-2">Proposed Action</h3>
                <div className="bg-wb-bg p-3 rounded border-l-4 border-wb-sage-deep text-sm text-wb-ink">
                  <strong>{selectedFinding.proposed_action.type}:</strong> {selectedFinding.proposed_action.description}
                </div>
              </section>

              {!selectedFinding.decision && (
                <section>
                  <h3 className="text-xs uppercase text-wb-ink2 tracking-wider font-semibold mb-3">Your Decision</h3>
                  <textarea
                    value={reasoning}
                    onChange={(e) => setReasoning(e.target.value)}
                    placeholder="Add reasoning (optional)..."
                    className="w-full p-2 rounded border border-wb-line bg-wb-bg text-wb-ink text-sm mb-3 font-mono"
                    rows={3}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => makeDecision('approved')}
                      className="flex-1 px-4 py-2 rounded bg-wb-ok text-wb-ok-on font-semibold text-sm hover:opacity-90"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => makeDecision('more_evidence')}
                      className="flex-1 px-4 py-2 rounded bg-wb-warn text-wb-warn-on font-semibold text-sm hover:opacity-90"
                    >
                      More Evidence
                    </button>
                    <button
                      onClick={() => makeDecision('rejected')}
                      className="flex-1 px-4 py-2 rounded bg-wb-crit text-wb-crit-on font-semibold text-sm hover:opacity-90"
                    >
                      Reject
                    </button>
                  </div>
                </section>
              )}

              {selectedFinding.decision && (
                <div className={`p-3 rounded ${STATUS_CLASSES[DECISION_STATUS[selectedFinding.decision]]} text-sm font-semibold`}>
                  Decision: {selectedFinding.decision.replace('_', ' ').toUpperCase()}
                </div>
              )}
            </Card>
          ) : (
            <Card title="Finding Details">
              <div className="text-center py-12 text-wb-ink2">Select a finding to review</div>
            </Card>
          )}
        </div>
      </div>

      <div className="text-center text-xs text-wb-ink2 mt-8">
        Findings auto-refresh every 5 seconds · Decisions saved to decisions.jsonl
      </div>
    </WorkbenchShell>
  );
}
