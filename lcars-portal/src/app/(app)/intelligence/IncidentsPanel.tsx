'use client';

import { useEffect, useState } from 'react';
import { lifecycleSummary, type IncidentRow } from '@/lib/incidents';

// Clustered, tiered incident view (INCIDENT_VIEW_V1, default OFF: the API answers enabled:false and this renders nothing).
// Read-only. Each entry is one incident (id = incident_key, the key the Telegram alert, Home and Decisions share) with its lifecycle:
// NEW / SUBSEQUENT / RESTORATION_UPDATE / RELATED, and its delivery tier.
const TIER_LABEL: Record<string, string> = {
  IMMEDIATE_ALERT: 'Alert-level',
  SCHEDULED_BRIEF: 'In today\'s brief',
  MONITOR: 'Monitoring',
  CONTEXT: 'Context',
  REFERENCE_RETAIN: 'Reference',
};
const REL_LABEL: Record<string, string> = {
  NEW: 'New',
  SUBSEQUENT: 'Subsequent',
  RESTORATION_UPDATE: 'Restoration',
  RELATED: 'Related',
  HISTORICAL_REFERENCE: 'Historical',
};

export function IncidentsPanel() {
  const [state, setState] = useState<{ enabled: boolean; available: boolean; incidents: IncidentRow[] } | null>(null);
  useEffect(() => {
    fetch('/api/intelligence-workbench/incidents')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setState(d))
      .catch(() => setState(null));
  }, []);
  if (!state?.enabled) return null;
  const shown = state.incidents.filter((i) => i.tier !== 'REFERENCE_RETAIN');
  return (
    <section className="mt-8" aria-labelledby="incidents-heading" data-testid="incidents-panel">
      <h2 id="incidents-heading" className="font-sans text-wb-label font-bold uppercase tracking-[0.25em] text-wb-sand-deep">
        Incidents (clustered, by tier)
      </h2>
      {!state.available ? (
        <p className="mt-2 text-wb-body text-wb-ink2">Incident data is unavailable right now. This is not an all-clear.</p>
      ) : shown.length === 0 ? (
        <p className="mt-2 text-wb-body text-wb-ink2">No incident above reference level in the last 72 hours.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {shown.map((i) => (
            <li key={i.incident_key} id={i.incident_key} className="rounded border border-wb-line bg-wb-surface p-3">
              <p className="text-wb-body font-medium text-wb-ink">{i.headline}</p>
              <p className="mt-0.5 text-wb-label text-wb-ink2">
                {TIER_LABEL[i.tier] ?? i.tier} · {i.restoration_status.replace(/_/g, ' ')} · {i.n_reports} reports · {lifecycleSummary(i)}
              </p>
              <p className="mt-1 text-wb-label text-wb-ink2">Why: {i.why}</p>
              <ul className="mt-2 space-y-1 text-wb-label text-wb-ink2">
                {i.reports
                  .filter((r) => r.relation !== 'RELATED' && r.relation !== 'HISTORICAL_REFERENCE')
                  .slice(0, 6)
                  .map((r) => (
                    <li key={r.event_id}>
                      <span className="font-semibold">{REL_LABEL[r.relation]}</span> {r.published_at ? new Date(r.published_at).toUTCString().slice(5, 22) : 'time unverified'}: {r.title}
                    </li>
                  ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
