'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import type { StatusTone } from '@/lib/types';

// ── Types ─────────────────────────────────────────────────────────────────────

interface IntelBriefRow {
  brief_id: string;
  generated_at: string;
  period_start: string | null;
  period_end: string | null;
  overall_risk: string | null;
  executive_snapshot: string | null;
  bottom_line: string | null;
  sources_checked: number | null;
  sources_available: number | null;
  sources_failed: number | null;
  sources_stale: number | null;
  events_evaluated: number | null;
  events_included: number | null;
  events_suppressed: number | null;
  confidence: number | null;
  provider_used: string | null;
  llm_used: boolean | null;
  narrative_available: boolean | null;
  emerging_themes: unknown;
  forward_watch: unknown;
  cps230_implications: unknown;
  top_events: unknown;
}

interface BriefArchiveRow {
  brief_id: string;
  generated_at: string;
  period_start: string | null;
  period_end: string | null;
  overall_risk: string | null;
  confidence: number | null;
  events_included: number | null;
  provider_used: string | null;
}

interface SourceHealthRow {
  source_name: string;
  category: string;
  status: string;
  items_retrieved: number | null;
  checked_at: string;
}

interface TopEventItem {
  title?: string;
  summary?: string;
  description?: string;
  risk?: string;
  risk_rating?: string;
  risk_level?: string;
  geography?: string;
  location?: string;
  event_type?: string;
  so_what?: string;
  operational_impact?: string;
  canonical_url?: string;
  source_name?: string;
  rank_score?: number;
  status?: string;
}

interface ThemeItem  { theme?: string; label?: string; description?: string; detail?: string; significance?: string }
interface WatchItem  { item?: string; label?: string; description?: string; detail?: string }

// ── Helpers ───────────────────────────────────────────────────────────────────

function toArray<T>(v: unknown): T[] {
  if (Array.isArray(v)) return v as T[];
  return [];
}

function toStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((item) => (typeof item === 'string' ? item : JSON.stringify(item)));
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
    case 'GREEN':
    case 'LOW':      return 'status';
    case 'AMBER':
    case 'MODERATE': return 'command';
    case 'RED':
    case 'HIGH':
    case 'CRITICAL': return 'operations';
    default:         return 'neutral';
  }
}

function srcDotClass(status: string): string {
  switch (status) {
    case 'ok':       return 'bg-status';
    case 'failed':   return 'bg-operations';
    case 'stale':
    case 'degraded': return 'bg-command';
    case 'skipped':  return 'bg-edge';
    default:         return 'bg-lcars-muted';
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

// ── Top events panel ──────────────────────────────────────────────────────────

function TopEventsPanel({ events }: { events: TopEventItem[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  if (!events.length) return null;

  return (
    <LCARSPanel title="Top Events" accent="science" eyebrow="Highest-signal items from this period">
      <div className="flex flex-col gap-2">
        {events.map((ev, i) => {
          const risk = ev.risk_rating ?? ev.risk ?? ev.risk_level;
          const isOpen = expanded === i;
          const hasDetail = !!(ev.so_what || ev.operational_impact);
          return (
            <div key={i} className="rounded-lcars border border-edge bg-panel-2/60">
              <div className="p-3">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-lcars-text leading-snug">
                      {ev.canonical_url
                        ? <a href={ev.canonical_url} target="_blank" rel="noreferrer" className="text-science hover:underline">{ev.title ?? '—'}</a>
                        : (ev.title ?? '—')
                      }
                    </p>
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    {risk && <StatusBadge label={risk.toUpperCase()} tone={riskToTone(risk)} />}
                    {ev.event_type && <StatusBadge label={ev.event_type.replace(/_/g, ' ')} tone="neutral" />}
                  </div>
                </div>
                <div className="flex flex-wrap gap-3 text-[10px] text-lcars-muted mb-1.5">
                  {(ev.geography ?? ev.location) && <span>{ev.geography ?? ev.location}</span>}
                  {ev.source_name && <span>· {ev.source_name}</span>}
                  {ev.rank_score != null && <span>· Score {ev.rank_score.toFixed(1)}</span>}
                </div>
                {(ev.summary ?? ev.description) && (
                  <p className="text-xs text-lcars-text/70 leading-relaxed">{ev.summary ?? ev.description}</p>
                )}
                {hasDetail && (
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : i)}
                    className="mt-2 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:text-science transition-colors"
                  >
                    {isOpen ? 'Less ↑' : 'So what ↓'}
                  </button>
                )}
              </div>
              {isOpen && hasDetail && (
                <div className="border-t border-edge px-3 pb-3 pt-2 flex flex-col gap-2">
                  {ev.so_what && (
                    <div className="rounded border-l-2 border-command bg-command/5 pl-3 pr-2 py-2">
                      <p className="text-[10px] uppercase tracking-wider text-command mb-0.5">So what</p>
                      <p className="text-xs text-lcars-text/80 leading-relaxed">{ev.so_what}</p>
                    </div>
                  )}
                  {ev.operational_impact && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-0.5">Impact</p>
                      <p className="text-xs text-lcars-text/70 leading-relaxed italic">{ev.operational_impact}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

// ── Themes + Forward Watch + CPS 230 ─────────────────────────────────────────

function NarrativeRow({
  themes,
  watch,
  cps230,
}: {
  themes: ThemeItem[];
  watch: WatchItem[];
  cps230: string[];
}) {
  const hasAny = themes.length || watch.length || cps230.length;
  if (!hasAny) return null;

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {/* Themes */}
      <LCARSPanel title="Emerging Themes" accent="science" eyebrow="Pattern recognition">
        {themes.length ? (
          <ul className="flex flex-col gap-1.5">
            {themes.map((t, i) => (
              <li key={i} className="flex gap-2 text-xs text-lcars-text/80 leading-relaxed">
                <span className="text-command shrink-0 mt-0.5">▸</span>
                <span>{t.theme ?? t.label ?? JSON.stringify(t)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-lcars-muted italic">Narrative unavailable</p>
        )}
      </LCARSPanel>

      {/* Forward Watch */}
      <LCARSPanel title="Forward Watch" accent="science" eyebrow="Items requiring monitoring">
        {watch.length ? (
          <ul className="flex flex-col gap-1.5">
            {watch.map((w, i) => (
              <li key={i} className="flex gap-2 text-xs text-lcars-text/80 leading-relaxed">
                <span className="text-science shrink-0 mt-0.5">▸</span>
                <span>{w.item ?? w.label ?? JSON.stringify(w)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-lcars-muted italic">Narrative unavailable</p>
        )}
      </LCARSPanel>

      {/* CPS 230 / Banking Implications */}
      <LCARSPanel title="CPS 230 / Banking" accent="science" eyebrow="Regulatory & banking implications">
        {cps230.length ? (
          <ul className="flex flex-col gap-1.5">
            {cps230.map((c, i) => (
              <li key={i} className="flex gap-2 text-xs text-lcars-text/80 leading-relaxed">
                <span className="text-medical shrink-0 mt-0.5">◆</span>
                <span>{c}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-lcars-muted italic">Narrative unavailable</p>
        )}
      </LCARSPanel>
    </div>
  );
}

// ── Source health ─────────────────────────────────────────────────────────────

function SourceHealthPanel({ sources }: { sources: SourceHealthRow[] }) {
  if (!sources.length) return null;

  const byStatus = {
    ok:      sources.filter((s) => s.status === 'ok').length,
    failed:  sources.filter((s) => s.status === 'failed').length,
    stale:   sources.filter((s) => ['stale', 'degraded'].includes(s.status)).length,
  };

  const categories = [...new Set(sources.map((s) => s.category))].sort();

  return (
    <LCARSPanel title="Source Health" accent="science" eyebrow="Intelligence pipeline — source status">
      <div className="grid grid-cols-3 gap-3 mb-4">
        <StatCell label="Available" value={byStatus.ok}     tone="status" />
        <StatCell label="Failed"    value={byStatus.failed}  tone={byStatus.failed > 0 ? 'operations' : 'neutral'} />
        <StatCell label="Stale"     value={byStatus.stale}   tone={byStatus.stale > 0 ? 'command' : 'neutral'} />
      </div>

      <div className="flex flex-col gap-4">
        {categories.map((cat) => {
          const catSources = sources.filter((s) => s.category === cat);
          return (
            <div key={cat}>
              <p className="text-[10px] uppercase tracking-[0.2em] text-science mb-2">
                {cat.replace(/_/g, ' ')}
              </p>
              <div className="flex flex-col divide-y divide-edge/40">
                {catSources.map((s, i) => (
                  <div key={i} className="flex items-center gap-3 py-1.5">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${srcDotClass(s.status)}`} />
                    <span className="flex-1 text-xs text-lcars-text/80">{s.source_name}</span>
                    <span className="text-[10px] text-lcars-muted shrink-0">
                      {s.items_retrieved != null ? `${s.items_retrieved} items` : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-lcars-muted mt-3">
        Last checked: {fmtDateTime(sources[0]?.checked_at)}
      </p>
    </LCARSPanel>
  );
}

// ── Brief archive strip ───────────────────────────────────────────────────────

function BriefArchive({ archive }: { archive: BriefArchiveRow[] }) {
  if (!archive.length) return null;
  return (
    <LCARSPanel title="Brief Archive" accent="science" eyebrow={`${archive.length} recent briefs`}>
      <div className="overflow-x-auto">
        <div className="flex gap-3" style={{ minWidth: `${archive.length * 200}px` }}>
          {archive.map((b) => {
            const fresh = getFreshness(b.generated_at);
            return (
              <div key={b.brief_id} className="w-48 shrink-0 rounded-lcars border border-edge bg-space/40 p-3">
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{fmtDateTime(b.generated_at)}</p>
                {(b.period_start || b.period_end) && (
                  <p className="text-[10px] text-lcars-muted/60 mt-0.5">
                    {fmtDate(b.period_start)} – {fmtDate(b.period_end)}
                  </p>
                )}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {b.overall_risk && <StatusBadge label={b.overall_risk.toUpperCase()} tone={riskToTone(b.overall_risk)} />}
                  <StatusBadge label={fresh.label} tone={fresh.tone} />
                </div>
                <div className="mt-2 flex gap-3 text-[10px] text-lcars-muted">
                  {b.events_included != null && <span>{b.events_included} events</span>}
                  {b.confidence != null && <span>{Math.round(b.confidence * 100)}%</span>}
                </div>
                {b.provider_used && (
                  <p className="text-[10px] text-lcars-muted/50 mt-1 truncate">{b.provider_used}</p>
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
  const [sources, setSources] = useState<SourceHealthRow[]>([]);
  const [isLive,  setIsLive]  = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const [briefRes, archiveRes, srcRes] = await Promise.all([
          supabase
            .from('intelligence_briefs')
            .select('*')
            .order('generated_at', { ascending: false })
            .limit(1)
            .single(),
          supabase
            .from('intelligence_briefs')
            .select('brief_id, generated_at, period_start, period_end, overall_risk, confidence, events_included, provider_used')
            .order('generated_at', { ascending: false })
            .limit(10),
          supabase
            .from('intelligence_source_health')
            .select('status, items_retrieved, checked_at, intelligence_source_registry!inner(source_name, category)')
            .order('checked_at', { ascending: false })
            .limit(200),
        ]);
        if (briefRes.data) { setBrief(briefRes.data as IntelBriefRow); setIsLive(true); }
        if (archiveRes.data?.length) setArchive(archiveRes.data as BriefArchiveRow[]);
        if (srcRes.data?.length) {
          // Deduplicate by source_name — keep most recent check per source
          const seen = new Set<string>();
          const deduped: SourceHealthRow[] = [];
          for (const row of srcRes.data) {
            const reg = (row as Record<string, unknown>).intelligence_source_registry as { source_name: string; category: string } | null;
            const name = reg?.source_name ?? '—';
            if (!seen.has(name)) {
              seen.add(name);
              deduped.push({
                source_name: name,
                category: reg?.category ?? 'unknown',
                status: (row as Record<string, unknown>).status as string,
                items_retrieved: (row as Record<string, unknown>).items_retrieved as number | null,
                checked_at: (row as Record<string, unknown>).checked_at as string,
              });
            }
          }
          setSources(deduped);
        }
      } catch {
        // fall through
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const freshness    = brief ? getFreshness(brief.generated_at) : null;
  const themes       = toArray<ThemeItem>(brief?.emerging_themes);
  const watch        = toArray<WatchItem>(brief?.forward_watch);
  const cps230       = toStringArray(brief?.cps230_implications);
  const events       = toArray<TopEventItem>(brief?.top_events);
  const sourcesFailed = (brief?.sources_failed ?? 0) > 0;

  const period = (brief?.period_start || brief?.period_end)
    ? `${fmtDate(brief?.period_start)} – ${fmtDate(brief?.period_end)}`
    : null;

  return (
    <div className="flex flex-col gap-4">

      {/* Header */}
      <LCARSPanel
        title="Intelligence Brief"
        accent="science"
        eyebrow={period ?? (loading ? 'Loading…' : 'No brief available')}
        actions={
          <div className="flex gap-2">
            {brief?.overall_risk && (
              <StatusBadge label={brief.overall_risk.toUpperCase()} tone={riskToTone(brief.overall_risk)} />
            )}
            {freshness && <StatusBadge label={freshness.label} tone={freshness.tone} />}
          </div>
        }
      >
        <p className="text-xs text-lcars-muted mb-2">
          Work intelligence pipeline — OR Intelligence. Banking &amp; critical infrastructure context.
        </p>
        {brief && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 mb-3">
            <StatCell label="Sources checked"    value={brief.sources_checked ?? '—'} />
            <StatCell label="Sources available"  value={brief.sources_available ?? '—'} tone="status" />
            <StatCell label="Events included"    value={brief.events_included ?? '—'}  tone="science" />
            <StatCell
              label="Confidence"
              value={brief.confidence != null ? `${Math.round(brief.confidence * 100)}%` : '—'}
              tone={brief.confidence != null && brief.confidence >= 0.7 ? 'status' : 'command'}
            />
          </div>
        )}
        {sourcesFailed && (
          <p className="text-[11px] text-operations mb-1">
            ⚠ {brief?.sources_failed} source{brief?.sources_failed !== 1 ? 's' : ''} failed this run.
          </p>
        )}
        {brief?.provider_used && (
          <p className="text-[10px] text-lcars-muted/60 mb-1">Model: {brief.provider_used}</p>
        )}
        <p className="text-[10px] uppercase tracking-wider text-lcars-muted">
          {loading ? 'Loading…' : isLive ? `● Live · ${fmtDateTime(brief?.generated_at)}` : '○ No brief available'}
        </p>
      </LCARSPanel>

      {/* Executive Snapshot */}
      {brief?.executive_snapshot && (
        <LCARSPanel title="Executive Snapshot" accent="science" eyebrow="Summary of the period">
          <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.executive_snapshot}</p>
          <div className="mt-3 flex flex-wrap gap-4 text-[10px] text-lcars-muted pt-3 border-t border-edge/40">
            {period && <span>Period: {period}</span>}
            {brief.sources_available != null && brief.sources_checked != null && (
              <span>Sources: {brief.sources_available}/{brief.sources_checked} available</span>
            )}
            {brief.events_included != null && brief.events_suppressed != null && (
              <span>Events: {brief.events_included} included, {brief.events_suppressed} suppressed</span>
            )}
          </div>
        </LCARSPanel>
      )}

      {/* Bottom Line */}
      {brief?.bottom_line && (
        <LCARSPanel title="Bottom Line" accent="command" eyebrow="Key takeaway">
          <div className="rounded-lcars border border-command/40 bg-command/5 p-4">
            <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.bottom_line}</p>
          </div>
        </LCARSPanel>
      )}

      {/* Narrative row: Themes + Forward Watch + CPS 230 */}
      <NarrativeRow themes={themes} watch={watch} cps230={cps230} />

      {/* Top Events */}
      <TopEventsPanel events={events} />

      {/* Brief Archive */}
      <BriefArchive archive={archive} />

      {/* Source Health */}
      <SourceHealthPanel sources={sources} />

    </div>
  );
}
