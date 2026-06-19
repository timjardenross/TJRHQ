'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';

// ── Types ─────────────────────────────────────────────────────────────────────

interface IntelBrief {
  brief_id: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  executive_snapshot: string;
  bottom_line: string;
  overall_risk: string;
  confidence: number;
  sources_checked: number;
  sources_available: number;
  sources_failed: number;
  sources_stale: number;
  events_evaluated: number;
  events_included: number;
  emerging_themes: unknown;
  forward_watch: unknown;
  top_events: unknown;
  cps230_implications: unknown;
  narrative_available: boolean;
  provider_used: string;
}

interface ArchiveBrief {
  brief_id: string;
  generated_at: string;
  period_start: string;
  period_end: string;
  overall_risk: string;
  confidence: number;
  sources_available: number;
  sources_checked: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function dataStatus(generatedAt: string) {
  const age = Date.now() - new Date(generatedAt).getTime();
  if (age < 2 * 60 * 60 * 1000)  return 'LIVE';
  if (age < 24 * 60 * 60 * 1000) return 'CACHED';
  return 'STALE';
}

function statusTone(s: string) {
  if (s === 'LIVE')    return 'status' as const;
  if (s === 'CACHED')  return 'command' as const;
  if (s === 'PARTIAL') return 'command' as const;
  return 'operations' as const;
}

function riskTone(r: string) {
  if (r === 'GREEN')  return 'status' as const;
  if (r === 'AMBER')  return 'command' as const;
  if (r === 'RED')    return 'operations' as const;
  return 'neutral' as const;
}

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' });
}

function fmtTime(d: string) {
  return new Date(d).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function asArray(v: unknown): Record<string, unknown>[] {
  if (!v) return [];
  if (Array.isArray(v)) return v as Record<string, unknown>[];
  return [];
}

function asStringArray(v: unknown): string[] {
  const arr = asArray(v);
  return arr.map((item) =>
    typeof item === 'string' ? item : (item.label ?? item.theme ?? item.title ?? item.name ?? JSON.stringify(item)) as string
  );
}

// ── Components ────────────────────────────────────────────────────────────────

function SourceStats({ brief }: { brief: IntelBrief }) {
  const freshnessLabel = brief.sources_failed > 0 ? 'PARTIAL' : dataStatus(brief.generated_at);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-4 text-xs text-lcars-muted">
        <span>Sources <span className="text-lcars-text font-mono font-bold">{brief.sources_available}/{brief.sources_checked}</span></span>
        <span>Events evaluated <span className="text-lcars-text font-mono font-bold">{brief.events_evaluated}</span></span>
        <span>Included <span className="text-lcars-text font-mono font-bold">{brief.events_included}</span></span>
        <span>Confidence <span className="text-lcars-text font-mono font-bold">{Math.round(brief.confidence * 100)}%</span></span>
        <span>Model <span className="text-lcars-text font-mono">{brief.provider_used ?? '—'}</span></span>
      </div>
      {brief.sources_failed > 0 && (
        <p className="text-xs text-operations">
          ⚠ {brief.sources_failed} source{brief.sources_failed !== 1 ? 's' : ''} failed or stale — brief may be incomplete
        </p>
      )}
      <div className="flex gap-2">
        <StatusBadge label={freshnessLabel} tone={statusTone(freshnessLabel)} />
        <StatusBadge label={`Risk: ${brief.overall_risk}`} tone={riskTone(brief.overall_risk)} />
      </div>
    </div>
  );
}

function ThemesAndWatch({ brief }: { brief: IntelBrief }) {
  const themes = asStringArray(brief.emerging_themes);
  const watch  = asArray(brief.forward_watch);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {themes.length > 0 && (
        <LCARSPanel title="Emerging Themes" accent="science" eyebrow="Pattern signals this period">
          <div className="flex flex-wrap gap-2">
            {themes.map((t, i) => (
              <span
                key={i}
                className="rounded-full border border-science bg-science/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-science"
              >
                {t}
              </span>
            ))}
          </div>
        </LCARSPanel>
      )}

      {watch.length > 0 && (
        <LCARSPanel title="Forward Watch" accent="command" eyebrow="Items to monitor">
          <ol className="flex flex-col gap-2">
            {watch.map((item, i) => {
              const label = (item.label ?? item.title ?? item.watch_item ?? item.description ?? JSON.stringify(item)) as string;
              const detail = (item.detail ?? item.why ?? item.rationale ?? '') as string;
              return (
                <li key={i} className="flex gap-3 rounded-lcars border border-edge bg-space/40 px-3 py-2">
                  <span className="shrink-0 font-lcars text-command">{i + 1}.</span>
                  <div>
                    <p className="text-sm text-lcars-text/90">{label}</p>
                    {detail && <p className="text-xs text-lcars-muted mt-0.5">{detail}</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        </LCARSPanel>
      )}
    </div>
  );
}

function TopEvents({ brief }: { brief: IntelBrief }) {
  const events = asArray(brief.top_events);
  if (!events.length) return null;

  return (
    <LCARSPanel title="Top Events" accent="science" eyebrow={`${events.length} flagged this period`}>
      <div className="flex flex-col gap-3">
        {events.map((ev, i) => {
          const title    = (ev.title ?? ev.event_title ?? ev.headline ?? `Event ${i + 1}`) as string;
          const summary  = (ev.summary ?? ev.description ?? ev.detail ?? '') as string;
          const risk     = (ev.risk ?? ev.risk_level ?? '') as string;
          const geo      = (ev.geography ?? ev.location ?? ev.region ?? '') as string;
          const evType   = (ev.event_type ?? ev.type ?? '') as string;
          const tone     = risk === 'HIGH' ? 'operations' : risk === 'MEDIUM' ? 'command' : 'neutral';

          return (
            <div key={i} className="rounded-lcars border border-edge bg-space/30 p-3">
              <div className="flex items-start justify-between gap-3 mb-1">
                <p className="text-sm font-semibold text-lcars-text">{title}</p>
                {risk && <StatusBadge label={risk} tone={tone as 'operations' | 'command' | 'neutral'} />}
              </div>
              {(geo || evType) && (
                <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">
                  {[evType, geo].filter(Boolean).join(' · ')}
                </p>
              )}
              {summary && <p className="text-xs leading-relaxed text-lcars-text/80">{summary}</p>}
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

function BriefHistory({ archive, currentId }: { archive: ArchiveBrief[]; currentId: string }) {
  if (archive.length < 2) return null;
  return (
    <LCARSPanel title="Brief History" accent="science" eyebrow="Recent runs">
      <div className="-mx-1 overflow-x-auto pb-1">
        <div className="flex gap-2 px-1">
          {archive.map((b) => {
            const isCurrent = b.brief_id === currentId;
            return (
              <div
                key={b.brief_id}
                className={`flex-shrink-0 min-w-[140px] rounded-lcars border p-3 ${
                  isCurrent ? 'border-science bg-science/10' : 'border-edge bg-space/30'
                }`}
              >
                <p className={`text-[10px] uppercase tracking-wider mb-1 ${isCurrent ? 'text-science' : 'text-lcars-muted'}`}>
                  {isCurrent ? 'Current' : fmtDate(b.generated_at)}
                </p>
                <p className="text-[11px] font-mono text-lcars-text">{fmtDate(b.period_start)}</p>
                <p className="text-[9px] text-lcars-muted">→ {fmtDate(b.period_end)}</p>
                <div className="mt-2 flex items-center gap-1.5">
                  <StatusBadge label={b.overall_risk} tone={riskTone(b.overall_risk)} />
                </div>
                <p className="mt-1 text-[10px] text-lcars-muted font-mono">
                  {Math.round(b.confidence * 100)}% · {b.sources_available}/{b.sources_checked} src
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </LCARSPanel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function XOBriefPage() {
  const [brief, setBrief]     = useState<IntelBrief | null>(null);
  const [archive, setArchive] = useState<ArchiveBrief[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const [latestRes, archiveRes] = await Promise.all([
        supabase.from('intelligence_briefs').select('*').order('generated_at', { ascending: false }).limit(1).single(),
        supabase.from('intelligence_briefs')
          .select('brief_id, generated_at, period_start, period_end, overall_risk, confidence, sources_available, sources_checked')
          .order('generated_at', { ascending: false })
          .limit(5),
      ]);

      if (latestRes.data) setBrief(latestRes.data as IntelBrief);
      if (archiveRes.data) setArchive(archiveRes.data as ArchiveBrief[]);
      setLoading(false);
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="py-16 text-center text-lcars-muted text-sm animate-pulse">
        Loading intelligence brief…
      </div>
    );
  }

  if (!brief) {
    return (
      <div className="py-16 text-center text-lcars-muted text-sm">
        No intelligence briefs found. Brief generation may not have run yet.
      </div>
    );
  }

  const freshnessLabel = brief.sources_failed > 0 ? 'PARTIAL' : dataStatus(brief.generated_at);

  return (
    <div className="flex flex-col gap-4">

      {/* Header */}
      <LCARSPanel
        title="OR Intelligence Brief"
        accent="science"
        eyebrow={`Period ${fmtDate(brief.period_start)} – ${fmtDate(brief.period_end)} · Generated ${fmtDate(brief.generated_at)} ${fmtTime(brief.generated_at)}`}
        actions={
          <div className="flex gap-2">
            <StatusBadge label={freshnessLabel} tone={statusTone(freshnessLabel)} />
            <StatusBadge label={`Risk: ${brief.overall_risk}`} tone={riskTone(brief.overall_risk)} />
          </div>
        }
      >
        <SourceStats brief={brief} />
      </LCARSPanel>

      {/* Executive Snapshot */}
      <LCARSPanel title="Executive Snapshot" accent="science" eyebrow="Period summary">
        <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.executive_snapshot}</p>
      </LCARSPanel>

      {/* Bottom Line */}
      <LCARSPanel title="Bottom Line" accent="command" eyebrow="Captain's guidance">
        <div className="rounded-lcars border border-command/40 bg-command/5 p-4">
          <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.bottom_line}</p>
        </div>
      </LCARSPanel>

      {/* Themes + Forward Watch */}
      <ThemesAndWatch brief={brief} />

      {/* Top Events */}
      <TopEvents brief={brief} />

      {/* Brief History */}
      <BriefHistory archive={archive} currentId={brief.brief_id} />

    </div>
  );
}
