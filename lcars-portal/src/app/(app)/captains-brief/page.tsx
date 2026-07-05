'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { ConfidenceIndicator } from '@/components/ConfidenceIndicator';
import { RecommendationCard } from '@/components/RecommendationCard';
import { EscalationBanner } from '@/components/EscalationBanner';

// ── Types — mirror core/platform/captain_brief_orchestrator.py's
// CaptainBriefDocument (MSN-0313) and captain_brief_contract.py's
// CaptainBriefItem/Recommendation. Kept local to this page since this is
// their first and only UI consumer. ─────────────────────────────────────────

interface Recommendation {
  description: string;
  action_type: string | null;
  confidence: number | null;
  evidence: string[];
  requires_approval: boolean;
  supporting_context: string | null;
}

interface CaptainBriefItem {
  event_id: string | null;
  domain: string;
  event_type: string;
  category: string;
  reason: string;
  priority_score: number | null;
  priority_explanation: string | null;
  recommendation: Recommendation | null;
  related_event_ids: string[];
  aggregation_key: string | null;
}

interface CaptainBriefDocument {
  version: string;
  generated_at: string;
  summary: string;
  priorities: CaptainBriefItem[];
  recommendations: Recommendation[];
  health: CaptainBriefItem[];
  operational_intelligence: CaptainBriefItem[];
  engineering: CaptainBriefItem[];
  learning: CaptainBriefItem[];
  opportunities: CaptainBriefItem[];
  warnings: CaptainBriefItem[];
  next_actions: string[];
  confidence: number | null;
}

const DOMAIN_SECTIONS: { key: 'health' | 'operational_intelligence' | 'engineering' | 'learning' | 'opportunities'; label: string }[] = [
  { key: 'health', label: 'Health' },
  { key: 'operational_intelligence', label: 'Operational Intelligence' },
  { key: 'engineering', label: 'Engineering' },
  { key: 'learning', label: 'Learning' },
  { key: 'opportunities', label: 'Opportunities' },
];

function ItemRow({ item }: { item: CaptainBriefItem }) {
  return (
    <li className="rounded-md border border-edge bg-panel-2/60 p-2">
      <p className="text-[10px] uppercase tracking-wide text-lcars-muted">
        {item.domain} · {item.event_type}
      </p>
      <p className="mt-0.5 text-xs text-lcars-text/90">{item.reason}</p>
    </li>
  );
}

export default function CaptainsBriefPage() {
  const [doc, setDoc] = useState<CaptainBriefDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/captain-brief')
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.error ?? 'Failed to load Captain Brief');
        setDoc(body);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Captain's Brief" accent="command" eyebrow="Continuous Captain Brief Orchestration · MSN-0313">
        {loading && <p className="text-sm text-lcars-muted animate-pulse">Assembling brief…</p>}
        {error && <p className="text-sm text-operations">{error}</p>}
        {doc && (
          <div className="flex flex-col gap-3">
            <ConfidenceIndicator score={doc.confidence} label="Document confidence" />
            <p className="text-sm text-lcars-text/90 leading-relaxed">{doc.summary}</p>
          </div>
        )}
      </LCARSPanel>

      {doc && doc.warnings.length > 0 && (
        <EscalationBanner level={3} message={`${doc.warnings.length} high-risk item(s) — review first.`} />
      )}

      {doc && doc.priorities.length > 0 && (
        <LCARSPanel title="Priorities" accent="command">
          <div className="flex flex-col gap-2">
            {doc.priorities.map((item, i) => (
              <RecommendationCard
                key={item.event_id ?? i}
                recommendation={{
                  action: item.recommendation?.description ?? item.reason,
                  why: item.priority_explanation ?? undefined,
                  sourceOfficer: item.domain,
                  confidence: item.recommendation?.confidence != null ? `${item.recommendation.confidence}%` : 'Unscored',
                }}
                compact
              />
            ))}
          </div>
        </LCARSPanel>
      )}

      {doc && doc.next_actions.length > 0 && (
        <LCARSPanel title="Next Actions" accent="command">
          <ol className="flex flex-col gap-1.5">
            {doc.next_actions.map((a, i) => (
              <li key={i} className="flex gap-2 text-sm text-lcars-text/90">
                <span className="font-lcars text-command shrink-0">{i + 1}.</span>
                {a}
              </li>
            ))}
          </ol>
        </LCARSPanel>
      )}

      {doc &&
        DOMAIN_SECTIONS.map(({ key, label }) => {
          const items = doc[key];
          if (!items.length) return null;
          return (
            <LCARSPanel key={key} title={label} accent="science">
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {items.map((item, i) => (
                  <ItemRow key={item.event_id ?? i} item={item} />
                ))}
              </ul>
            </LCARSPanel>
          );
        })}

      {doc && doc.priorities.length === 0 && doc.warnings.length === 0 && (
        <LCARSPanel title="All Clear" accent="status">
          <p className="text-sm text-lcars-muted">No new signals since the last brief.</p>
        </LCARSPanel>
      )}
    </div>
  );
}
