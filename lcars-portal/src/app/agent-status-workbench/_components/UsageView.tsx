'use client';

/**
 * Usage tab — LLM call volume, tokens, and spend by provider/model, plus a
 * daily trend across every provider. Reads /api/agent-status-workbench/usage
 * (migration 0197's views over llm_call_metrics, the existing cost-governance
 * audit trail from Issue 21 — no new scoring/logging logic here).
 *
 * Read-only, no polling — a look-back view like History/Pipeline Health,
 * not a live status board.
 */

import { useEffect, useState } from 'react';
import { Card } from '@/components/ui';

interface ModelUsageRow {
  provider: string;
  model_name: string | null;
  call_count: number;
  successful_calls: number;
  failed_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number | null;
  avg_latency_ms: number | null;
  last_call_at: string;
}

interface DailyTotalRow {
  day: string;
  call_count: number;
  successful_calls: number;
  failed_calls: number;
  total_cost_usd: number | null;
}

interface UsageData {
  byModel: ModelUsageRow[];
  dailyTotals: DailyTotalRow[];
  note: string;
}

const numberFmt = new Intl.NumberFormat('en-AU');
const costFmt = new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 });

function formatCost(v: number | null): string {
  return costFmt.format(v ?? 0);
}

function successRate(row: { call_count: number; successful_calls: number }): string {
  if (row.call_count === 0) return '—';
  return `${Math.round((row.successful_calls / row.call_count) * 100)}%`;
}

function ByModelTable({ rows }: { rows: ModelUsageRow[] }) {
  if (rows.length === 0) {
    return <p className="text-[12px] italic text-wb-ink2">No LLM calls logged in the last 30 days.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-wb-line">
            <th className="pb-2 pr-3 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Provider</th>
            <th className="pb-2 pr-3 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Model</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Calls</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Success</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Input tok</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Output tok</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Cost</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Avg latency</th>
            <th className="pb-2 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Last call</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.provider}-${r.model_name ?? ''}`} className="border-b border-wb-line last:border-0">
              <td className="py-2 pr-3 text-[12px] text-wb-ink">{r.provider}</td>
              <td className="py-2 pr-3 text-[12px] text-wb-ink2">{r.model_name ?? '—'}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{numberFmt.format(r.call_count)}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{successRate(r)}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{numberFmt.format(r.total_input_tokens)}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{numberFmt.format(r.total_output_tokens)}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink">{formatCost(r.total_cost_usd)}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{r.avg_latency_ms != null ? `${numberFmt.format(r.avg_latency_ms)}ms` : '—'}</td>
              <td className="py-2 text-right text-[12px] tabular-nums text-wb-ink2">{new Date(r.last_call_at).toLocaleString('en-AU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DailyTotalsTable({ rows }: { rows: DailyTotalRow[] }) {
  if (rows.length === 0) {
    return <p className="text-[12px] italic text-wb-ink2">No daily rows yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-wb-line">
            <th className="pb-2 pr-3 text-left text-[10px] uppercase tracking-wider text-wb-ink2">Day</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Calls</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Successful</th>
            <th className="pb-2 pr-3 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Failed</th>
            <th className="pb-2 text-right text-[10px] uppercase tracking-wider text-wb-ink2">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.day} className="border-b border-wb-line last:border-0">
              <td className="py-2 pr-3 text-[12px] text-wb-ink">{new Date(r.day).toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{numberFmt.format(r.call_count)}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{numberFmt.format(r.successful_calls)}</td>
              <td className="py-2 pr-3 text-right text-[12px] tabular-nums text-wb-ink2">{numberFmt.format(r.failed_calls)}</td>
              <td className="py-2 text-right text-[12px] tabular-nums text-wb-ink">{formatCost(r.total_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function UsageView() {
  const [data, setData] = useState<UsageData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/agent-status-workbench/usage', { cache: 'no-store' });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Failed to load usage');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) return <Card><p className="text-[13px] italic text-wb-ink2">Loading usage…</p></Card>;
  if (loadError || !data) {
    return (
      <Card>
        <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
          <p className="text-[13px] font-semibold text-wb-crit-on">Usage unavailable</p>
          <p className="mt-1 text-[12px] text-wb-ink2">{loadError ?? 'No data returned.'}</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="mb-2 font-serif text-lg text-wb-ink">By model — last 30 days</h2>
        <ByModelTable rows={data.byModel} />
      </Card>

      <Card>
        <h2 className="mb-2 font-serif text-lg text-wb-ink">Daily totals — last 14 days</h2>
        <DailyTotalsTable rows={data.dailyTotals} />
      </Card>

      <p className="text-[11px] text-wb-ink2">{data.note}</p>
    </div>
  );
}
