'use client';

// Human Systems — Weight (Mission 7 deferred-register item 12, closed).
//
// Ports the real 30-day weight-trend view that used to live at
// (app)/medical/log-weight — same query against `weight_logs`, same stats
// (avg/range/30-day change) and mini history chart, re-shelled onto
// WorkbenchShell + wb-* tokens instead of the old LCARSPanel system.
// Manual entry stays retired (Captain directive, 2026-08-10 — Recovery
// Pulse via the Telegram XO bot is the platform's sole manual health-data
// capture path); this is a read-only history view, same as its predecessor.
//
// (app)/medical/log-weight is retired alongside this page landing here —
// see its own git history for the page this replaces.

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

interface WeightTrendRow {
  log_date: string;
  weight_kg: number;
}

export default function WeightPage() {
  const [trend, setTrend] = useState<WeightTrendRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const trendRes = await supabase
        .from('weight_logs')
        .select('log_date,weight_kg')
        .order('log_date', { ascending: false })
        .limit(30);
      if (alive && trendRes.data) setTrend(trendRes.data as WeightTrendRow[]);
      if (alive) setLoading(false);
    }
    load();
    return () => { alive = false; };
  }, []);

  const minW = trend.length ? Math.min(...trend.map((r) => r.weight_kg)) : null;
  const maxW = trend.length ? Math.max(...trend.map((r) => r.weight_kg)) : null;
  const avgW = trend.length ? trend.reduce((s, r) => s + r.weight_kg, 0) / trend.length : null;
  const change = trend.length >= 2 ? (trend[0].weight_kg - trend[trend.length - 1].weight_kg).toFixed(1) : null;

  return (
    <WorkbenchShell
      title="Human Systems — Weight"
      eyebrow="30-Day History"
      tagline="USS TJR · History only — manual entry retired in favour of Recovery Pulse"
      back={{ href: '/human-systems-workbench', label: 'Human Systems' }}
    >
      <div className="flex flex-col gap-4">
        <Card>
          <p className="text-[13px] leading-relaxed text-wb-ink2">
            Manual weight logging has been retired. Recovery Pulse (via the Telegram XO bot) is now the
            Captain&rsquo;s single manual health-data capture mechanism — this page shows history only.
          </p>
        </Card>

        {loading && <div className="py-10 text-center text-[13px] text-wb-ink2">Loading…</div>}

        {!loading && trend.length === 0 && (
          <Card>
            <p className="text-[13px] text-wb-ink2">No weight entries recorded yet.</p>
          </Card>
        )}

        {trend.length > 0 && (
          <Card title={`30-Day Trend · ${trend.length} entries`}>
            <div className="grid grid-cols-3 gap-3">
              {avgW !== null && (
                <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                  <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Avg</p>
                  <p className="mt-0.5 font-serif text-lg text-wb-ink">{avgW.toFixed(1)}</p>
                  <p className="text-[10px] text-wb-ink2">kg</p>
                </div>
              )}
              {minW !== null && maxW !== null && (
                <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                  <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Range</p>
                  <p className="mt-0.5 font-serif text-sm text-wb-ink">{minW}–{maxW}</p>
                  <p className="text-[10px] text-wb-ink2">kg</p>
                </div>
              )}
              {change !== null && (
                <div className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                  <p className="text-[10px] uppercase tracking-wider text-wb-ink2">Change</p>
                  <p className="mt-0.5 font-serif text-lg text-wb-ink">
                    {parseFloat(change) > 0 ? '+' : ''}{change}
                  </p>
                  <p className="text-[10px] text-wb-ink2">kg vs 30d ago</p>
                </div>
              )}
            </div>

            {minW !== null && maxW !== null && (
              <div className="mt-4 flex flex-col gap-1.5">
                {trend.slice(0, 14).reverse().map((r) => {
                  const span = maxW - minW || 1;
                  const pct = ((r.weight_kg - minW) / span) * 100;
                  return (
                    <div key={r.log_date} className="flex items-center gap-2">
                      <span className="w-14 shrink-0 font-mono text-[10px] text-wb-ink2">{r.log_date.slice(5)}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-wb-line/50">
                        <div className="h-full rounded-full bg-wb-sage-deep transition-all" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="w-12 text-right font-mono text-[10px] text-wb-ink2">{r.weight_kg}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        )}
      </div>
    </WorkbenchShell>
  );
}
