'use client';

/**
 * CommandStrip — the Captain's Chair operating strip (CCP-001 WP1/WP2/WP3).
 *
 * Additive top-of-page band that answers, in one glance: what should I do next,
 * what is the ship's state, what changed, and what are officers doing. All data
 * is live from Command Memory via useCommandCentre (reuse-first); it degrades to
 * a quiet "awaiting data" state and leaves the existing panels untouched.
 */

import { useCommandCentre } from '@/lib/useCommandCentre';
import { toneClasses } from '@/lib/departments';
import { DataSourceIndicator } from './DataSourceIndicator';
import { ExecutiveSummary } from './ExecutiveSummary';

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lcars border border-edge bg-panel/60 p-3 ${className}`}>{children}</div>
  );
}

function Header({ title, live }: { title: string; live?: boolean }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.25em] text-lcars-muted">{title}</h2>
      {live !== undefined && <DataSourceIndicator live={live} variant="inline" />}
    </div>
  );
}

export function CommandStrip() {
  const { recommendedAction, shipStatus, whatChanged, activity, isLive, isLoading } = useCommandCentre();

  return (
    <section className="flex flex-col gap-4">
      {/* Recommended Action headline + Ship Status tiles (WP1) — MSN-0303's ratified "headline + supporting tiles" duplicate */}
      <ExecutiveSummary
        recommendation={recommendedAction}
        isLoading={isLoading}
        isLive={isLive}
        shipStatus={shipStatus}
      />

      {/* What Changed + Officer Activity (WP2/WP3) */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <Header title="Since Last Visit" />
          {whatChanged.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {whatChanged.map((c, i) => {
                const t = toneClasses(c.tone);
                return (
                  <li key={i} className="flex items-start gap-2">
                    <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${t.dot}`} />
                    <p className="text-[11px] text-lcars-text">
                      <span className={`font-semibold ${t.text}`}>{c.label}:</span> {c.detail}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-[11px] text-lcars-muted">
              {isLoading ? 'Checking for movement…' : 'No movement since your last visit.'}
            </p>
          )}
        </Panel>

        <Panel>
          <Header title="Officer Activity" live={activity.length > 0} />
          {activity.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {activity.map((e, i) => {
                const t = toneClasses(e.tone);
                return (
                  <li key={i} className="flex items-center gap-2">
                    <span className="w-10 shrink-0 font-mono text-[10px] text-lcars-muted">{e.time}</span>
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${t.dot}`} />
                    <span className="min-w-0 flex-1 truncate text-[11px] text-lcars-text">{e.label}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-[11px] text-lcars-muted">
              {isLoading ? 'Loading the command timeline…' : 'No recent officer activity.'}
            </p>
          )}
        </Panel>
      </div>
    </section>
  );
}
