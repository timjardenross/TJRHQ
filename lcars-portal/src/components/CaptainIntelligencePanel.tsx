'use client';

import { useEffect, useState, useCallback } from 'react';
import { WorkbenchPanel } from '@/components/WorkbenchPanel';
import { DataSourceIndicator } from '@/components/DataSourceIndicator';

// MSN-0329 Phase 5 — first production consumer of the Cognitive Core
// pipeline (assemble_evolved_captain_brief()). Read (fast) and generate
// (slow, real LLM synthesis, 50-260s) are deliberately separate actions —
// see the two API routes' own comments for why. This panel is additive:
// it never replaces or hides anything already on Captain's Chair, and an
// empty/error state here has zero effect on the rest of the page.

interface CaptainInsight {
  id: string;
  generated_at: string;
  observation: string;
  why_it_matters: string;
  potential_impact: string;
  insight_confidence: number | null;
  recommended_action: string | null;
  trade_offs: string | null;
  expected_outcome: string | null;
  recommendation_confidence: number | null;
  outcome: string;
  source_domains: string[];
}

export function CaptainIntelligencePanel() {
  const [insights, setInsights] = useState<CaptainInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/captain-intelligence/insights');
      const data = await res.json();
      setInsights(data.insights ?? []);
      setError(res.ok ? null : (data.error ?? 'Failed to load'));
    } catch {
      setError('Failed to load Captain Intelligence insights');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const generate = useCallback(async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch('/api/captain-intelligence/generate', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? 'Generation failed');
      } else {
        await load();
      }
    } catch {
      setError('Generation failed — request timed out or the model router is unreachable');
    } finally {
      setGenerating(false);
    }
  }, [load]);

  return (
    <WorkbenchPanel
      title="Captain Intelligence"
      eyebrow={
        loading
          ? 'MSN-0329 — Cognitive Core'
          : insights.length >= 20
            ? 'MSN-0329 — Cognitive Core'
            : `MSN-0329 — Cognitive Core (observation period, ${insights.length}/20 insights)`
      }
      actions={
        <div className="flex items-center gap-3">
          <DataSourceIndicator live={insights.length > 0} loading={loading} variant="inline" liveLabel="Real insights" mockLabel="None yet" />
          <button
            onClick={generate}
            disabled={generating}
            className="rounded-full border border-wb-border px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-wb-ink hover:bg-wb-bg disabled:opacity-50"
          >
            {generating ? 'Synthesising… (can take 1-4 min)' : 'Generate New Insights'}
          </button>
        </div>
      }
    >
      {error && (
        <p className="mb-3 text-sm text-state-warn">{error}</p>
      )}

      {!loading && insights.length === 0 && !error && (
        <p className="text-sm text-wb-ink2">
          No Captain Intelligence insights generated yet. This is an observation-period feature — real
          insights accumulate here as the pipeline runs against real operational data. Click
          &quot;Generate New Insights&quot; to run it now.
        </p>
      )}

      <div className="flex flex-col gap-3">
        {insights.map((insight) => (
          <div key={insight.id} className="rounded-lg border border-wb-border/60 bg-wb-bg/60 p-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-wb-ink2">
                {insight.source_domains?.join(', ')} · {new Date(insight.generated_at).toLocaleString()}
              </span>
              <span className="text-[10px] uppercase tracking-wider text-wb-ink2">
                confidence {insight.insight_confidence ?? '—'} · {insight.outcome}
              </span>
            </div>
            <p className="text-sm font-semibold text-wb-ink">{insight.observation}</p>
            <p className="mt-1 text-sm text-wb-ink2">{insight.why_it_matters}</p>
            {insight.recommended_action && (
              <div className="mt-2 border-t border-wb-border/40 pt-2">
                <p className="text-sm text-wb-ink">
                  <span className="font-semibold">Recommended: </span>
                  {insight.recommended_action}
                </p>
                {insight.trade_offs && (
                  <p className="mt-1 text-xs text-wb-ink2">Trade-off: {insight.trade_offs}</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </WorkbenchPanel>
  );
}
