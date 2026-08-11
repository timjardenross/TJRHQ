'use client';

// Manual capture retirement (Captain directive, 2026-08-10 — see
// .claude/skills/bot-reviews/fixes-2026-08-09/manual-capture-retirement.md):
// Recovery Pulse (via the Telegram XO bot) is now the platform's only
// manual health-data capture mechanism. This page previously let the
// Captain manually log a weight entry directly to `weight_logs` — that
// input is retired below. History and the 30-day trend remain visible;
// only the ability to create new entries has been removed.

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

interface WeightTrendRow {
  log_date:  string;
  weight_kg: number;
}

export default function LogWeightPage() {
  const today  = new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' });

  const [trend, setTrend] = useState<WeightTrendRow[]>([]);

  useEffect(() => {
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const trendRes = await supabase
        .from('weight_logs')
        .select('log_date,weight_kg')
        .order('log_date', { ascending: false })
        .limit(30);

      if (trendRes.data?.length) setTrend(trendRes.data as WeightTrendRow[]);
    }
    load();
  }, []);

  // Simple trend stats
  const minW  = trend.length ? Math.min(...trend.map(r => r.weight_kg)) : null;
  const maxW  = trend.length ? Math.max(...trend.map(r => r.weight_kg)) : null;
  const avgW  = trend.length ? trend.reduce((s, r) => s + r.weight_kg, 0) / trend.length : null;
  const range = trend.length >= 2
    ? (trend[0].weight_kg - trend[trend.length - 1].weight_kg).toFixed(1)
    : null;

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Log Weight" accent="medical" eyebrow={today}>
        <p className="text-xs text-lcars-muted leading-relaxed">
          Manual weight logging has been retired. Recovery Pulse (via the Telegram XO bot) is now
          the Captain&rsquo;s single manual health-data capture mechanism — this page no longer
          accepts new entries. History below remains visible.
        </p>
      </LCARSPanel>

      {/* 30-day trend */}
      {trend.length > 0 && (
        <LCARSPanel title="30-Day Trend" accent="medical" eyebrow={`${trend.length} entries`}>
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            {avgW !== null && (
              <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Avg</p>
                <p className="font-lcars text-lg font-bold text-command-on mt-0.5">{avgW.toFixed(1)}</p>
                <p className="text-[10px] text-lcars-muted">kg</p>
              </div>
            )}
            {minW !== null && maxW !== null && (
              <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Range</p>
                <p className="font-lcars text-sm font-bold text-lcars-text mt-0.5">{minW}–{maxW}</p>
                <p className="text-[10px] text-lcars-muted">kg</p>
              </div>
            )}
            {range !== null && (
              <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Change</p>
                <p className={`font-lcars text-lg font-bold mt-0.5 ${parseFloat(range) < 0 ? 'text-status-on' : parseFloat(range) > 0 ? 'text-operations-on' : 'text-lcars-muted'}`}>
                  {parseFloat(range) > 0 ? '+' : ''}{range}
                </p>
                <p className="text-[10px] text-lcars-muted">kg vs 30d ago</p>
              </div>
            )}
          </div>

          {/* Mini chart */}
          {minW !== null && maxW !== null && (
            <div className="flex flex-col gap-1">
              {trend.slice(0, 14).reverse().map((r) => {
                const span = maxW - minW || 1;
                const pct  = ((r.weight_kg - minW) / span) * 100;
                return (
                  <div key={r.log_date} className="flex items-center gap-2">
                    <span className="w-14 shrink-0 text-[10px] font-mono text-lcars-muted">{r.log_date.slice(5)}</span>
                    <div className="flex-1 h-2 rounded-full bg-edge/30 overflow-hidden">
                      <div className="h-full rounded-full bg-command transition-all" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-12 text-right text-[10px] font-mono text-lcars-muted">{r.weight_kg}</span>
                  </div>
                );
              })}
            </div>
          )}
        </LCARSPanel>
      )}
    </div>
  );
}
