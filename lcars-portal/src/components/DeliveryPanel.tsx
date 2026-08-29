'use client';

/**
 * EDO Delivery panel (MSN-EDO-002 QW1) — makes delivery state, bottlenecks, and
 * metrics visible at a glance. Self-contained; renders a graceful no-data state.
 */

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { Badge, toneToStatus } from '@/components/ui';
import { DataSourceIndicator } from '@/components/DataSourceIndicator';
import { deliverySeverityToTone } from '@/lib/departments';
import { loadDelivery, OPEN_STATES, STATE_TONE, type DeliveryData } from '@/lib/delivery';

export function DeliveryPanel() {
  const [data, setData] = useState<DeliveryData | null>(null);

  useEffect(() => {
    let active = true;
    loadDelivery().then((d) => active && setData(d));
    return () => {
      active = false;
    };
  }, []);

  if (!data) {
    return (
      <LCARSPanel title="Delivery" accent="engineering" eyebrow="Engineering & Delivery Officer">
        <p className="text-sm text-lcars-muted">Reading delivery state…</p>
      </LCARSPanel>
    );
  }

  const { rows, metrics, bottlenecks, tower, isLive } = data;
  const open = rows.filter((r) => OPEN_STATES.includes(r.delivery_state));
  const byState: Record<string, number> = {};
  open.forEach((r) => (byState[r.delivery_state] = (byState[r.delivery_state] ?? 0) + 1));

  return (
    <LCARSPanel
      title="Delivery"
      accent="engineering"
      eyebrow="Engineering & Delivery Officer"
      actions={<DataSourceIndicator live={isLive} />}
    >
      {/* Metrics strip */}
      {metrics && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            ['Open', metrics.open_count],
            ['Closed', metrics.closed_count],
            ['Avg cycle', metrics.avg_cycle_days != null ? `${metrics.avg_cycle_days}d` : 'n/a'],
            ['PR rate', metrics.total ? `${Math.round((metrics.with_pr / metrics.total) * 100)}%` : '—']
          ].map(([label, value]) => (
            <div key={label as string} className="rounded-lcars border border-edge bg-panel/40 px-3 py-2">
              <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">{label}</p>
              <p className="mt-0.5 text-sm font-semibold text-lcars-text">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Open by state */}
      <div className="mt-4 flex flex-wrap gap-2">
        {OPEN_STATES.filter((s) => byState[s]).map((s) => (
          <StatusBadge key={s} label={`${s.replace('_', ' ')} ${byState[s]}`} tone={STATE_TONE[s]} />
        ))}
        {open.length === 0 && <span className="text-xs text-lcars-muted">No open missions.</span>}
      </div>

      {/* Bottlenecks */}
      <div className="mt-4">
        <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Bottlenecks</p>
        {bottlenecks.length === 0 ? (
          <p className="mt-1 text-sm text-status">Delivery is flowing — nothing stuck beyond thresholds.</p>
        ) : (
          <ul className="mt-1 flex flex-col gap-1">
            {bottlenecks.slice(0, 6).map((b, i) => (
              <li key={i} className="flex items-center gap-2 text-xs text-lcars-text/85">
                <Badge status={toneToStatus(deliverySeverityToTone(b.severity))}>{b.severity}</Badge>
                <span className="font-semibold">{b.title}</span>
                <span className="text-lcars-text/60">— {b.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Control Tower (WP2): risk + constraint + capacity */}
      <div className="mt-4 rounded-lcars border border-engineering bg-engineering/10 p-3">
        <p className="text-[10px] uppercase tracking-[0.2em] text-engineering">Control Tower</p>
        <div className="mt-1 flex flex-wrap gap-2 text-xs">
          <StatusBadge label={`${tower.highRiskCount} high-risk`} tone={tower.highRiskCount ? 'operations' : 'status'} />
          {tower.constraint && (
            <StatusBadge label={`constraint: ${tower.constraint.replace('_', ' ')} ${tower.constraintCount}`} tone="command" />
          )}
          <StatusBadge label={`eng WIP ${tower.engWip}`} tone={tower.engWip > 3 ? 'operations' : 'medical'} />
        </div>
        {tower.topRisks.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1">
            {tower.topRisks.slice(0, 4).map((r, i) => (
              <li key={i} className="flex items-center gap-2 text-xs text-lcars-text/80">
                <StatusBadge label={String(r.score)} tone={r.level === 'high' ? 'operations' : r.level === 'medium' ? 'command' : 'neutral'} />
                <span>{r.title}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="mt-3 text-[11px] text-lcars-muted leading-relaxed">
        Instrumented delivery + control tower (EDO). Ask in Slack:{' '}
        <code>/delivery forecast</code>, <code>/delivery risk</code>,{' '}
        <code>/delivery execute &lt;id&gt;</code>.
      </p>
    </LCARSPanel>
  );
}
