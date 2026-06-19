'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { StatusTone } from '@/lib/types';

// ── Types ─────────────────────────────────────────────────────────────────────

interface IntelBriefRow {
  id: string;
  generated_at: string;
  period_label: string | null;
  risk_level: string | null;
  executive_snapshot: string | null;
  bottom_line: string | null;
  sources_checked: number | null;
  sources_available: number | null;
  sources_failed: number | null;
  sources_stale: number | null;
  events_evaluated: number | null;
  events_included: number | null;
  confidence_score: number | null;
  model_used: string | null;
  emerging_themes: unknown;
  forward_watch: unknown;
  top_events: unknown;
}

interface BriefArchiveRow {
  id: string;
  generated_at: string;
  period_label: string | null;
  risk_level: string | null;
  confidence_score: number | null;
  sources_checked: number | null;
  sources_failed: number | null;
}

interface ThemeItem    { theme?: string; label?: string; description?: string; detail?: string; significance?: string }
interface WatchItem    { item?: string; label?: string; description?: string; detail?: string }
interface TopEventItem { title?: string; summary?: string; description?: string; risk?: string; risk_level?: string; geography?: string; event_type?: string }

// ── Helpers ───────────────────────────────────────────────────────────────────

function toArray<T>(v: unknown): T[] {
  if (Array.isArray(v)) return v as T[];
  return [];
}

function fmtDate(ts: string | null | undefined): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
}

function fmtDateTime(ts: string | null | undefined): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

function getFreshness(ts: string): { label: string; tone: StatusTone } {
  const ageH = (Date.now() - new Date(ts).getTime()) / 3_600_000;
  if (ageH < 2)  return { label: 'LIVE',   tone: 'status' };
  if (ageH < 24) return { label: 'CACHED', tone: 'command' };
  return { label: 'STALE', tone: 'operations' };
}

function riskToTone(risk: string | null | undefined): StatusTone {
  switch (risk?.toUpperCase()) {
    case 'LOW':      return 'status';
    case 'MODERATE': return 'command';
    case 'HIGH':
    case 'CRITICAL': return 'operations';
    default:         return 'neutral';
  }
}

// ── Stat cell ─────────────────────────────────────────────────────────────────

function StatCell({ label, value, tone = 'neutral' }: { label: string; value: string | number; tone?: StatusTone }) {
  const textColor: Record<StatusTone, string> = {
    status: 'text-status', command: 'text-command', operations: 'text-operations',
    medical: 'text-medical', science: 'text-science', engineering: 'text-engineering', neutral: 'text-lcars-text',
  };
  return (
    <div className="rounded-lcars border border-edge bg-space/40 p-3 text-center">
      <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{label}</p>
      <p className={`font-lcars text-xl font-bold mt-0.5 ${textColor[tone]}`}>{value}</p>
    </div>
  );
}

// ── Themes panel ──────────────────────────────────────────────────────────────

function ThemesPanel({ themes }: { themes: ThemeItem[] }) {
  if (!themes.length) return null;
  return (
    <LCARSPanel title="Emerging Themes" accent="science" eyebrow="Pattern recognition — work context">
      <div className="flex flex-col gap-2">
        {themes.map((t, i) => (
          <div key={i} className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-xs font-semibold text-lcars-text">{t.theme ?? t.label ?? '—'}</p>
            {(t.description ?? t.detail ?? t.significance) && (
              <p className="text-xs text-lcars-text/70 mt-1 leading-relaxed">
                {t.description ?? t.detail ?? t.significance}
              </p>
            )}
          </div>
        ))}
      </div>
    </LCARSPanel>
  );
}

// ── Forward watch panel ───────────────────────────────────────────────────────

function ForwardWatchPanel({ items }: { items: WatchItem[] }) {
  if (!items.length) return null;
  return (
    <LCARSPanel title="Forward Watch" accent="science" eyebrow="Items requiring monitoring">
      <ol className="flex flex-col gap-2">
        {items.map((w, i) => (
          <li key={i} className="flex gap-3 rounded-lcars border border-edge bg-space/40 p-3">
            <span className="font-lcars text-science shrink-0 mt-0.5">{i + 1}.</span>
            <div>
              <p className="text-xs font-semibold text-lcars-text">{w.item ?? w.label ?? '—'}</p>
              {(w.description ?? w.detail) && (
                <p className="text-xs text-lcars-text/70 mt-0.5 leading-relaxed">
                  {w.description ?? w.detail}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </LCARSPanel>
  );
}

// ── Top events panel ──────────────────────────────────────────────────────────

function TopEventsPanel({ events }: { events: TopEventItem[] }) {
  if (!events.length) return null;
  return (
    <LCARSPanel title="Top Events" accent="science" eyebrow="Highest-signal items from this period">
      <div className="flex flex-col gap-2">
        {events.map((ev, i) => {
          const risk = ev.risk ?? ev.risk_level;
          return (
            <div key={i} className="rounded-lcars border border-edge bg-panel-2/60 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs font-semibold text-lcars-text">{ev.title ?? '—'}</p>
                <div className="flex gap-1.5 shrink-0">
                  {risk && <StatusBadge label={risk.toUpperCase()} tone={riskToTone(risk)} />}
                  {ev.event_type && <StatusBadge label={ev.event_type} tone="neutral" />}
                </div>
              </div>
              {(ev.summary ?? ev.description) && (
                <p className="text-xs text-lcars-text/70 mt-1.5 leading-relaxed">
                  {ev.summary ?? ev.description}
                </p>
              )}
              {ev.geography && (
                <p className="text-[10px] text-lcars-muted mt-1">{ev.geography}</p>
              )}
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

// ── Brief history strip ───────────────────────────────────────────────────────

function BriefHistory({ archive }: { archive: BriefArchiveRow[] }) {
  if (!archive.length) return null;
  return (
    <LCARSPanel title="Brief History" accent="science" eyebrow="Last 5 intelligence briefs">
      <div className="overflow-x-auto">
        <div className="flex gap-3" style={{ minWidth: `${archive.length * 180}px` }}>
          {archive.map((b) => {
            const fresh = getFreshness(b.generated_at);
            return (
              <div key={b.id} className="w-44 shrink-0 rounded-lcars border border-edge bg-space/40 p-3">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{fmtDate(b.generated_at)}</p>
                <p className="text-xs font-semibold text-lcars-text mt-1">{b.period_label ?? '—'}</p>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {b.risk_level && <StatusBadge label={b.risk_level.toUpperCase()} tone={riskToTone(b.risk_level)} />}
                  <StatusBadge label={fresh.label} tone={fresh.tone} />
                </div>
                {b.confidence_score != null && (
                  <p className="text-[10px] text-lcars-muted mt-1.5">
                    {Math.round(b.confidence_score * 100)}% confidence
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IntelligenceBriefPage() {
  const [brief,   setBrief]   = useState<IntelBriefRow | null>(null);
  const [archive, setArchive] = useState<BriefArchiveRow[]>([]);
  const [isLive,  setIsLive]  = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const [briefRes, archiveRes] = await Promise.all([
          supabase
            .from('intelligence_briefs')
            .select('*')
            .order('generated_at', { ascending: false })
            .limit(1)
            .single(),
          supabase
            .from('intelligence_briefs')
            .select('id, generated_at, period_label, risk_level, confidence_score, sources_checked, sources_failed')
            .order('generated_at', { ascending: false })
            .limit(5),
        ]);
        if (briefRes.data) { setBrief(briefRes.data as IntelBriefRow); setIsLive(true); }
        if (archiveRes.data?.length) setArchive(archiveRes.data as BriefArchiveRow[]);
      } catch {
        // fall through
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const freshness     = brief ? getFreshness(brief.generated_at) : null;
  const themes        = toArray<ThemeItem>(brief?.emerging_themes);
  const watch         = toArray<WatchItem>(brief?.forward_watch);
  const events        = toArray<TopEventItem>(brief?.top_events);
  const sourcesFailed = (brief?.sources_failed ?? 0) > 0;

  return (
    <div className="flex flex-col gap-4">

      <LCARSPanel
        title="Intelligence Brief"
        accent="science"
        eyebrow={brief?.period_label ?? (loading ? 'Loading…' : 'No brief available')}
        actions={
          <div className="flex gap-2">
            {brief?.risk_level && (
              <StatusBadge label={brief.risk_level.toUpperCase()} tone={riskToTone(brief.risk_level)} />
            )}
            {freshness && <StatusBadge label={freshness.label} tone={freshness.tone} />}
          </div>
        }
      >
        <p className="text-xs text-lcars-muted mb-2">
          Work intelligence pipeline — OR Intelligence. Sources monitored for work-context signals.
        </p>
        {brief && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 mb-3">
            <StatCell label="Sources checked"  value={brief.sources_checked ?? '—'} />
            <StatCell label="Events evaluated" value={brief.events_evaluated ?? '—'} />
            <StatCell label="Events included"  value={brief.events_included ?? '—'} tone="science" />
            <StatCell
              label="Confidence"
              value={brief.confidence_score != null ? `${Math.round(brief.confidence_score * 100)}%` : '—'}
              tone={brief.confidence_score != null && brief.confidence_score >= 0.7 ? 'status' : 'command'}
            />
          </div>
        )}
        {sourcesFailed && (
          <p className="text-[11px] text-operations mb-1">
            {brief?.sources_failed} source{brief?.sources_failed !== 1 ? 's' : ''} failed this run.
          </p>
        )}
        <p className="text-[10px] uppercase tracking-wider text-lcars-muted">
          {loading ? 'Loading…' : isLive ? `● Live · ${fmtDateTime(brief?.generated_at)}` : '○ No brief available'}
        </p>
      </LCARSPanel>

      {brief?.executive_snapshot && (
        <LCARSPanel title="Executive Snapshot" accent="science" eyebrow="Summary of the period">
          <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.executive_snapshot}</p>
        </LCARSPanel>
      )}

      {brief?.bottom_line && (
        <LCARSPanel title="Bottom Line" accent="command" eyebrow="Key takeaway">
          <div className="rounded-lcars border border-command/40 bg-command/5 p-4">
            <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.bottom_line}</p>
          </div>
        </LCARSPanel>
      )}

      <ThemesPanel themes={themes} />
      <ForwardWatchPanel items={watch} />
      <TopEventsPanel events={events} />
      <BriefHistory archive={archive} />

    </div>
  );
}
