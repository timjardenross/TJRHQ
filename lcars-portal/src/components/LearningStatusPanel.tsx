'use client';

// USS-TJR-MSN-0080 — Learning Intelligence Visibility (Captain's Chair widget).
// Concise LEARNING STATUS block. Mirrors WellnessInsightPanel: fetch a read-only
// summary from /api/learning and render glanceable counts + a health band.
// Surface signals, not noise. Human interpretation stays central.

import { useEffect, useState } from 'react';
import { LCARSPanel } from './LCARSPanel';
import { StatusBadge } from './StatusBadge';

interface LearningData {
  outcomes: number;
  pending: number;
  overdue: number;
  lessons: number;
  reusable: number;
  content: number;
  sensitive: number;
  velocity7d: number;
  oldestUncapturedDays: number | null;
  health: string;
}

const HEALTH_TONE: Record<string, 'status' | 'command' | 'operations' | 'neutral'> = {
  GREEN: 'status',
  AMBER: 'command',
  RED: 'operations',
  UNKNOWN: 'neutral',
};

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-edge bg-space/40 p-2 text-center">
      <p className="text-[9px] uppercase tracking-wider text-lcars-muted">{label}</p>
      <p className="text-sm text-lcars-text/90 mt-0.5 font-mono">{value}</p>
    </div>
  );
}

export function LearningStatusPanel() {
  const [data, setData] = useState<LearningData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/learning')
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  const hasData = !loading && data !== null;
  const health = data?.health ?? 'UNKNOWN';

  return (
    <LCARSPanel
      title="Learning Status"
      accent="command"
      eyebrow="Outcome & Learning Loop · Knowledge Officer"
      actions={
        loading ? (
          <span className="text-[10px] uppercase tracking-wider text-lcars-muted animate-pulse">Loading…</span>
        ) : hasData ? (
          <StatusBadge label={health} tone={HEALTH_TONE[health] ?? 'neutral'} />
        ) : (
          <StatusBadge label="No data" tone="neutral" />
        )
      }
    >
      {loading && (
        <p className="text-xs text-lcars-muted animate-pulse">Fetching learning status…</p>
      )}

      {!loading && !hasData && (
        <p className="text-xs text-lcars-muted">
          No learning data yet. Capture outcomes with <code>record_outcome.py</code> to populate this.
        </p>
      )}

      {hasData && data && (
        <>
          <div className="grid gap-2 grid-cols-3 sm:grid-cols-5">
            <Stat label="Outcomes" value={data.outcomes} />
            <Stat label="Pending" value={data.pending} />
            <Stat label="Lessons" value={data.lessons} />
            <Stat label="Reusable" value={data.reusable} />
            <Stat label="Content" value={data.content} />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-lcars-muted">
            {data.overdue > 0 && (
              <span className="rounded-full border border-operations/60 bg-operations/10 text-operations px-2 py-0.5 uppercase tracking-wide">
                {data.overdue} overdue
              </span>
            )}
            {data.sensitive > 0 && (
              <span className="rounded-full border border-command/60 bg-command/10 text-command px-2 py-0.5 uppercase tracking-wide">
                {data.sensitive} sensitive pending approval
              </span>
            )}
            {data.oldestUncapturedDays != null && (
              <span>Oldest uncaptured: {data.oldestUncapturedDays}d</span>
            )}
            <span>· Velocity (7d): {data.velocity7d}</span>
          </div>

          {/* MSN-0087 WP8: narrative — significance + attention (derived from counts). */}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">This week</p>
              <ul className="text-[11px] text-lcars-text/80 space-y-0.5">
                <li>• {data.velocity7d} outcome(s) captured (7d)</li>
                <li>• {data.reusable} reusable insight(s)</li>
                <li>• {data.content} content candidate(s)</li>
              </ul>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">Attention</p>
              <ul className="text-[11px] text-lcars-text/80 space-y-0.5">
                {data.overdue > 0 && <li>• {data.overdue} overdue outcome(s)</li>}
                {data.sensitive > 0 && <li>• {data.sensitive} sensitive draft(s) pending approval</li>}
                {data.pending > 0 && <li>• {data.pending} item(s) awaiting capture</li>}
                {data.overdue === 0 && data.sensitive === 0 && data.pending === 0 && (
                  <li className="text-status">• Nothing outstanding</li>
                )}
              </ul>
            </div>
          </div>

          <p className="mt-3 text-[10px] text-lcars-muted">
            Learning Health: <span className="uppercase tracking-wide">{health}</span> — visibility only;
            capture remains human, nothing is published.
          </p>
        </>
      )}
    </LCARSPanel>
  );
}
