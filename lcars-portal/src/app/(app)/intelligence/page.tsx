'use client';

import { useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { deriveRisk } from '@/lib/intelligenceRisk';

/**
 * Intelligence Centre — MSN-0201 rewire.
 * Queries OR intelligence tables directly via /api/intelligence.
 * Tabs: Latest Brief | Signals | Themes | Sources | Archive | Daily Briefs
 */

type Tab = 'latest' | 'signals' | 'themes' | 'archive' | 'daily_briefs' | 'content_signals';

const TABS: { key: Tab; label: string; glyph: string }[] = [
  { key: 'latest',          label: 'Latest Brief',    glyph: '●' },
  { key: 'signals',         label: 'Signals',         glyph: '◈' },
  { key: 'themes',          label: 'Themes',          glyph: '↗' },
  { key: 'archive',         label: 'ORI Archive',     glyph: '▣' },
  { key: 'daily_briefs',    label: 'Daily Briefs',    glyph: '☀' },
  { key: 'content_signals', label: 'Content',         glyph: '✍' },
];

const RISK_COLOUR: Record<string, string> = {
  HIGH:   'text-red-400',
  MEDIUM: 'text-yellow-400',
  LOW:    'text-green-400',
};
const RISK_ICON: Record<string, string> = { HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢' };

async function fetchIntel(params: Record<string, string>): Promise<unknown> {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`/api/intelligence?${qs}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ?? 'Intelligence query failed');
  return data;
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lcars border border-edge bg-panel/40 p-4">
      <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-lcars-muted">{title}</h2>
      <div className="text-sm text-lcars-text">{children}</div>
    </section>
  );
}

function RiskBadge({ risk }: { risk?: string }) {
  const r = (risk ?? '').toUpperCase();
  return (
    <span className={`font-semibold ${RISK_COLOUR[r] ?? 'text-lcars-muted'}`}>
      {RISK_ICON[r] ?? '⚪'} {r || '—'}
    </span>
  );
}

// ── Tab views ─────────────────────────────────────────────────────────────────

function LatestBrief({ d }: { d: any }) {
  const b = d.brief;
  if (!b) return <p className="text-sm text-lcars-muted">No ORI brief on record.</p>;
  const themes: any[] = b.emerging_themes ?? [];
  const fw = b.forward_watch;
  const cps = b.cps230_implications;
  return (
    <div className="flex flex-col gap-3">
      <Card title={`ORI Brief — ${(b.brief_id ?? '').slice(0, 8)}`}>
        <div className="flex items-center gap-3 mb-2">
          <RiskBadge risk={b.overall_risk} />
          <span className="text-xs text-lcars-muted">
            {(b.period_start ?? '').slice(0, 10)} → {(b.period_end ?? '').slice(0, 10)}
          </span>
          <span className="text-xs text-lcars-muted">Generated {(b.generated_at ?? '').slice(0, 10)}</span>
        </div>
        {b.executive_snapshot && <p className="mb-1">{b.executive_snapshot}</p>}
        {b.bottom_line && <p className="italic text-lcars-muted">{b.bottom_line}</p>}
        <p className="mt-2 text-xs text-lcars-muted">
          {b.events_included ?? 0} events · {b.sources_checked ?? 0} sources · {b.narrative_available ? 'LLM narrative' : 'rule-based'} · {b.provider_used ?? '—'}
        </p>
      </Card>
      {themes.length > 0 && (
        <Card title="Emerging Themes">
          <ul className="list-disc pl-5 space-y-1">
            {themes.slice(0, 8).map((t, i) => {
              const label = typeof t === 'string' ? t : (t.theme ?? t.title ?? JSON.stringify(t));
              return <li key={i}>{label}</li>;
            })}
          </ul>
        </Card>
      )}
      {fw && (
        <Card title="Forward Watch">
          <p>{typeof fw === 'string' ? fw : JSON.stringify(fw)}</p>
        </Card>
      )}
      {cps && (
        <Card title="CPS 230 Implications">
          <p>{typeof cps === 'string' ? cps : JSON.stringify(cps)}</p>
        </Card>
      )}
    </div>
  );
}

// deriveRisk now lives in @/lib/intelligenceRisk so the server-side risk
// filter (api/intelligence/route.ts) and this badge share one definition and
// can never disagree. Kept imported at module top.

// Tooltip text making the badge's provenance explicit — this HIGH/MEDIUM/LOW
// is an assessment computed from impact fields, not a stored, verified rating.
const DERIVED_RISK_TOOLTIP =
  'Derived assessment — computed from customer-impact & banking-relevance. Not a stored risk rating.';

function SignalCard({ s }: { s: any }) {
  const [open, setOpen] = useState(false);
  const risk = deriveRisk(s);
  const themes: string[] = Array.isArray(s.resilience_themes)
    ? s.resilience_themes
    : typeof s.resilience_themes === 'object' && s.resilience_themes
      ? Object.values(s.resilience_themes as Record<string, string>)
      : [];

  return (
    <div className="rounded-lcars border border-edge bg-panel/30">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-start gap-2 p-3 text-left hover:bg-panel/50 transition-colors"
      >
        <span className="mt-0.5 shrink-0">{RISK_ICON[risk] ?? '⚪'}</span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm leading-snug text-lcars-text">{s.raw_title}</p>
          {!open && s.raw_summary && (
            <p className="text-xs text-lcars-muted mt-1 line-clamp-2">{s.raw_summary}</p>
          )}
          <div className="flex gap-3 mt-1 text-xs text-lcars-muted flex-wrap">
            {s.event_type && <span className="capitalize">{s.event_type.replace(/_/g,' ')}</span>}
            {s.organisation && <span>🏢 {s.organisation}</span>}
            {s.geography  && <span>📍 {s.geography}</span>}
            {risk         && (
              <span className={RISK_COLOUR[risk]} title={DERIVED_RISK_TOOLTIP}>
                {risk}
                <span className="ml-0.5 font-normal text-lcars-muted/60">(derived)</span>
              </span>
            )}
            {s.rank_score != null && <span>Score {Number(s.rank_score).toFixed(1)}</span>}
            <span>{(s.collected_at ?? '').slice(0, 10)}</span>
          </div>
        </div>
        <span className="text-[10px] text-lcars-muted shrink-0 mt-1">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="border-t border-edge/50 px-4 py-3 space-y-3 text-sm">
          {s.raw_summary && (
            <p className="text-lcars-text/90 leading-relaxed">{s.raw_summary}</p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
            {s.sector            && <span className="text-lcars-muted">Sector <span className="text-lcars-text ml-1">{s.sector}</span></span>}
            {s.banking_relevance && <span className="text-lcars-muted">Banking rel. <span className="text-lcars-text ml-1 capitalize">{s.banking_relevance}</span></span>}
            {s.customer_impact   && <span className="text-lcars-muted">Customer impact <span className="text-lcars-text ml-1 capitalize">{s.customer_impact}</span></span>}
            {s.executive_relevance && <span className="text-lcars-muted">Exec relevance <span className="text-lcars-text ml-1 capitalize">{s.executive_relevance}</span></span>}
            {s.cps230_relevance  && <span className="text-science">CPS 230 relevant</span>}
            {s.dependency_risk   && <span className="text-operations">Dependency risk</span>}
            {s.source_ref        && <span className="text-lcars-muted col-span-2">Source <span className="text-lcars-text ml-1">{s.source_ref}</span></span>}
          </div>
          {themes.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-1">Resilience Themes</p>
              <div className="flex flex-wrap gap-1.5">
                {themes.map((t, i) => (
                  <span key={i} className="rounded-lcars border border-science/30 bg-science/5 px-2 py-0.5 text-xs text-science">{t}</span>
                ))}
              </div>
            </div>
          )}
          {s.canonical_url && (
            <a href={s.canonical_url} target="_blank" rel="noopener noreferrer"
               className="inline-block text-xs text-science hover:underline">
              View source ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function SignalsView({ d }: { d: any }) {
  const signals: any[] = d.signals ?? [];
  if (!signals.length) return <p className="text-sm text-lcars-muted">No signals found for this period.</p>;
  return (
    <div className="flex flex-col gap-2">
      {/* MSN-0351: make the badge's provenance visible, not silent. */}
      <p className="text-[10px] text-lcars-muted/70" title={DERIVED_RISK_TOOLTIP}>
        Risk is a derived assessment (from customer-impact &amp; banking-relevance), not a stored rating.
      </p>
      {signals.map((s, i) => <SignalCard key={s.event_id ?? i} s={s} />)}
    </div>
  );
}

function ThemesView({ d }: { d: any }) {
  const t = d.themes;
  if (!t) return <p className="text-sm text-lcars-muted">No themes data.</p>;
  const themes: any[] = t.emerging_themes ?? [];
  const fw = t.forward_watch;
  return (
    <div className="flex flex-col gap-3">
      <Card title={`Brief ${(t.brief_id ?? '').slice(0, 8)} — ${(t.generated_at ?? '').slice(0, 10)}`}>
        <div className="flex items-center gap-3 mb-2">
          <RiskBadge risk={t.overall_risk} />
          <span className="text-xs text-lcars-muted">
            {(t.period_start ?? '').slice(0, 10)} → {(t.period_end ?? '').slice(0, 10)}
          </span>
        </div>
        {t.executive_snapshot && <p className="italic text-lcars-muted">{t.executive_snapshot}</p>}
      </Card>
      {themes.length > 0 && (
        <Card title="Emerging Themes">
          <ul className="list-disc pl-5 space-y-1">
            {themes.map((th, i) => {
              const label = typeof th === 'string' ? th : (th.theme ?? th.title ?? JSON.stringify(th));
              const detail = typeof th === 'object' ? (th.detail ?? th.description ?? '') : '';
              return (
                <li key={i}>
                  <strong>{label}</strong>
                  {detail && <p className="text-xs text-lcars-muted">{detail}</p>}
                </li>
              );
            })}
          </ul>
        </Card>
      )}
      {fw && (
        <Card title="Forward Watch">
          <p>{typeof fw === 'string' ? fw : JSON.stringify(fw)}</p>
        </Card>
      )}
    </div>
  );
}


function ArchiveView({ d }: { d: any }) {
  const briefs: any[] = d.briefs ?? [];
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!briefs.length) return <p className="text-sm text-lcars-muted">No briefs in archive.</p>;
  return (
    <div className="flex flex-col gap-2">
      {briefs.map((b, i) => {
        const id = b.brief_id ?? String(i);
        const isOpen = expanded === id;
        return (
          <div key={id} className="rounded-lcars border border-edge bg-panel/30">
            <button
              type="button"
              onClick={() => setExpanded(isOpen ? null : id)}
              className="w-full flex items-center justify-between p-3 text-left hover:bg-panel/50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-lcars-muted text-xs">{isOpen ? '▼' : '▶'}</span>
                <span className="font-mono text-xs text-lcars-muted">{id.slice(0, 8)}</span>
                <span className="text-sm text-lcars-text">
                  {(b.period_start ?? '').slice(0, 10)} → {(b.period_end ?? '').slice(0, 10)}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-lcars-muted">
                <RiskBadge risk={b.overall_risk} />
                <span>{b.events_included ?? 0} events</span>
                <span>{b.narrative_available ? '✍️' : '📊'}</span>
                <span className="text-lcars-muted">{(b.generated_at ?? '').slice(0, 10)}</span>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-edge px-4 py-3 text-sm text-lcars-text space-y-2">
                {b.executive_snapshot && <p>{b.executive_snapshot}</p>}
                {b.bottom_line && <p className="italic text-lcars-muted">{b.bottom_line}</p>}
                {b.emerging_themes && Array.isArray(b.emerging_themes) && b.emerging_themes.length > 0 && (
                  <div>
                    <p className="text-xs uppercase tracking-widest text-lcars-muted mb-1">Emerging Themes</p>
                    <ul className="list-disc pl-5 space-y-0.5 text-xs">
                      {b.emerging_themes.slice(0, 5).map((t: any, ti: number) => (
                        <li key={ti}>{typeof t === 'string' ? t : (t.theme ?? t.title ?? JSON.stringify(t))}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {b.forward_watch && (
                  <div>
                    <p className="text-xs uppercase tracking-widest text-lcars-muted mb-1">Forward Watch</p>
                    <p className="text-xs">{typeof b.forward_watch === 'string' ? b.forward_watch : JSON.stringify(b.forward_watch)}</p>
                  </div>
                )}
                <p className="text-xs text-lcars-muted pt-1">
                  {b.sources_checked ?? 0} sources · {b.provider_used ?? '—'}
                </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DailyBriefsView({ d }: { d: any }) {
  const briefs: any[] = d.briefs ?? [];
  if (!briefs.length) return (
    <div className="text-sm text-lcars-muted">
      <p>No daily briefs stored yet.</p>
      <p className="mt-1 text-xs">Briefs are persisted each time the scheduled brief runs (07:00 / 12:30 / 18:00 AEST). Apply migration 0033 to the VM to enable persistence.</p>
    </div>
  );
  const BRIEF_ICON: Record<string, string> = { morning: '☀️', midday: '🌤', eod: '🌙', weekly: '📊' };
  return (
    <div className="flex flex-col gap-2">
      {briefs.map((b, i) => {
        const h = b.health_snapshot ?? {};
        return (
          <div key={i} className="rounded-lcars border border-edge bg-panel/30 p-3">
            <div className="flex items-center justify-between">
              <span className="font-medium text-sm">
                {BRIEF_ICON[b.brief_type] ?? '📄'} {b.brief_type} — {b.brief_date}
              </span>
              <span className="text-xs text-lcars-muted">{(b.generated_at ?? '').slice(11, 16)} AEST</span>
            </div>
            <div className="flex gap-4 mt-1 text-xs text-lcars-muted">
              {b.signals_count > 0 && <span>📡 {b.signals_count} signals</span>}
              {h.capacity_score != null && <span>⚡ Cap {h.capacity_score}</span>}
              {h.pain_score     != null && <span>Pain {h.pain_score}</span>}
              {h.sleep_hours    != null && <span>Sleep {h.sleep_hours}h</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Content Signals tab (MSN-0202) ────────────────────────────────────────────

const PILLAR_COLOUR: Record<string, string> = {
  operational_resilience:        'text-red-400 border-red-400/30 bg-red-400/5',
  business_continuity:           'text-orange-400 border-orange-400/30 bg-orange-400/5',
  human_performance:             'text-blue-400 border-blue-400/30 bg-blue-400/5',
  wellness_sustainable_performance: 'text-green-400 border-green-400/30 bg-green-400/5',
  ai_augmented_leadership:       'text-purple-400 border-purple-400/30 bg-purple-400/5',
  personal_operating_systems:    'text-lcars-muted border-lcars-muted/30 bg-lcars-muted/5',
  future_of_work:                'text-yellow-400 border-yellow-400/30 bg-yellow-400/5',
  decision_quality_governance:   'text-science border-science/30 bg-science/5',
};

function PillarBadge({ pillarKey, pillarName }: { pillarKey: string; pillarName: string }) {
  const cls = PILLAR_COLOUR[pillarKey] ?? 'text-lcars-muted border-lcars-muted/30 bg-lcars-muted/5';
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {pillarName || pillarKey}
    </span>
  );
}

function RequestDraftButton({ signal }: { signal: any }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [msg, setMsg] = useState('');

  async function handleRequest() {
    setStatus('loading');
    try {
      const res = await fetch('/api/content/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: signal.event_id,
          title: signal.raw_title,
          pillar_key: signal.pillar_key,
          suggested_angle: signal.suggested_angle,
          source_name: signal.source_name,
          canonical_url: signal.canonical_url,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed');
      setStatus('done');
      setMsg('Added to pipeline as opportunity');
    } catch (err) {
      setStatus('error');
      setMsg(err instanceof Error ? err.message : 'Failed');
    }
  }

  if (status === 'done') return <span className="text-xs text-green-400">✓ {msg}</span>;
  if (status === 'error') return <span className="text-xs text-red-400">✗ {msg}</span>;

  return (
    <button
      type="button"
      onClick={handleRequest}
      disabled={status === 'loading'}
      className="text-xs border border-science/40 rounded px-2 py-0.5 text-science hover:bg-science/10 disabled:opacity-50 transition-colors"
    >
      {status === 'loading' ? 'Adding…' : '+ Request draft'}
    </button>
  );
}

function ContentSignalCard({ s }: { s: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lcars border border-edge bg-panel/30">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-start gap-2 p-3 text-left hover:bg-panel/50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm leading-snug text-lcars-text">{s.raw_title}</p>
          <div className="flex flex-wrap gap-2 mt-1.5 items-center">
            {s.pillar_key && <PillarBadge pillarKey={s.pillar_key} pillarName={s.pillar_name} />}
            {s.captain_focus && (
              <span className="text-[10px] font-medium text-amber-400 border border-amber-400/30 bg-amber-400/5 rounded px-1.5 py-0.5">
                ★ Captain Focus
              </span>
            )}
            <span className="text-[10px] text-lcars-muted">
              Score {Number(s.rank_score ?? 0).toFixed(1)}
            </span>
            <span className="text-[10px] text-lcars-muted">
              via {s.source_name}
            </span>
            <span className="text-[10px] text-lcars-muted">
              {(s.collected_at ?? '').slice(0, 10)}
            </span>
          </div>
          {!open && s.suggested_angle && (
            <p className="text-xs text-lcars-muted/70 mt-1 italic line-clamp-1">{s.suggested_angle}</p>
          )}
        </div>
        <span className="text-[10px] text-lcars-muted shrink-0 mt-1">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="border-t border-edge/50 px-4 py-3 space-y-2 text-sm">
          {s.suggested_angle && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-1">Suggested Angle</p>
              <p className="text-xs text-lcars-text italic">{s.suggested_angle}</p>
            </div>
          )}
          {s.raw_summary && (
            <p className="text-xs text-lcars-text/80 leading-relaxed">{s.raw_summary}</p>
          )}
          <div className="flex items-center gap-4 text-xs text-lcars-muted">
            <span>Relevance {(Number(s.content_relevance ?? 0) * 100).toFixed(0)}%</span>
          </div>
          <div className="flex gap-3 items-center flex-wrap">
            {s.canonical_url && (
              <a href={s.canonical_url} target="_blank" rel="noopener noreferrer"
                 className="text-xs text-science hover:underline">
                View source ↗
              </a>
            )}
            <RequestDraftButton signal={s} />
          </div>
        </div>
      )}
    </div>
  );
}

function PillarCard({ p }: { p: any }) {
  return (
    <div className="rounded-lcars border border-edge bg-panel/30 p-3">
      <div className="flex items-center justify-between mb-1">
        <PillarBadge pillarKey={p.pillar_key} pillarName={p.pillar_name} />
        <span className="text-[10px] text-lcars-muted">{p.signal_count} signal{p.signal_count !== 1 ? 's' : ''}</span>
      </div>
      {p.top_signal_title && (
        <p className="text-xs text-lcars-text/80 line-clamp-2 mt-1">{p.top_signal_title}</p>
      )}
      <p className="text-[10px] text-lcars-muted mt-1">
        Avg relevance {(Number(p.avg_relevance ?? 0) * 100).toFixed(0)}%
      </p>
    </div>
  );
}

function ContentSignalsView({ d }: { d: any }) {
  const signals: any[]   = d.signals ?? [];
  const byPillar: any[]  = d.by_pillar ?? [];
  const pipeline: Record<string, number> = d.pipeline ?? {};
  const captainCount: number = d.captain_focus_count ?? 0;

  if (!signals.length && !byPillar.length) {
    return (
      <div className="text-sm text-lcars-muted space-y-2">
        <p>No content signals scored yet.</p>
        <p className="text-xs">
          Run <code className="bg-panel/60 px-1 rounded">content_intelligence_service.score_and_persist()</code> to score recent intelligence events for content relevance.
        </p>
      </div>
    );
  }

  const pipelineStatuses = ['opportunity', 'draft', 'review', 'approved', 'ready_to_publish', 'published'];

  return (
    <div className="flex flex-col gap-4">
      {/* Summary header */}
      <div className="flex gap-4 flex-wrap text-xs text-lcars-muted">
        <span>Top {signals.length} signals</span>
        {captainCount > 0 && <span className="text-amber-400">★ {captainCount} captain-focus</span>}
        <span>{byPillar.length} pillars active</span>
      </div>

      {/* Pipeline snapshot */}
      {Object.keys(pipeline).length > 0 && (
        <div className="rounded-lcars border border-edge bg-panel/20 p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] uppercase tracking-widest text-lcars-muted">Content Pipeline</p>
            <Link href="/comms" className="text-[10px] uppercase tracking-wide text-science-on hover:text-science-on/70 transition-colors">
              Manage pipeline →
            </Link>
          </div>
          <div className="flex flex-wrap gap-3">
            {pipelineStatuses.map(s => pipeline[s] != null ? (
              <span key={s} className="text-xs text-lcars-text">
                <span className="text-lcars-muted capitalize">{s.replace(/_/g, ' ')}</span>
                {' '}{pipeline[s]}
              </span>
            ) : null)}
          </div>
        </div>
      )}

      {/* Pillar breakdown */}
      {byPillar.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-2">By Pillar</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {byPillar.map((p, i) => <PillarCard key={p.pillar_key ?? i} p={p} />)}
          </div>
        </div>
      )}

      {/* Top signals ranked list */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-lcars-muted mb-2">Top Signals This Week</p>
        <div className="flex flex-col gap-2">
          {signals.map((s, i) => <ContentSignalCard key={s.event_id ?? i} s={s} />)}
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IntelligencePage() {
  const [tab, setTab]       = useState<Tab>('latest');
  const [data, setData]     = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState<string | null>(null);

  // Signal filter state
  const [signalDays, setSignalDays] = useState('7');
  const [signalRisk, setSignalRisk] = useState('');
  const [contentDays, setContentDays] = useState('7');
  const [contentPillar, setContentPillar] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    const params: Record<string, string> = { view: tab };
    if (tab === 'signals') {
      params.days = signalDays;
      if (signalRisk) params.risk = signalRisk;
    }
    if (tab === 'daily_briefs') params.days = '14';
    if (tab === 'content_signals') {
      params.days  = contentDays;
      params.limit = '10';
      if (contentPillar) params.pillar = contentPillar;
    }

    fetchIntel(params)
      .then(r => !cancelled && setData(r as Record<string, unknown>))
      .catch(e => !cancelled && setError(e instanceof Error ? e.message : 'Failed.'))
      .finally(() => !cancelled && setLoading(false));

    return () => { cancelled = true; };
  }, [tab, signalDays, signalRisk, contentDays, contentPillar]);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 p-4">
      <header>
        <h1 className="text-xl font-semibold uppercase tracking-wider text-lcars-text">
          Intelligence Centre
        </h1>
        <p className="text-sm text-lcars-muted">
          Operational Resilience Intelligence — {new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' })}
        </p>
      </header>

      <div className="flex border-b border-edge overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-xs uppercase tracking-[0.15em] whitespace-nowrap transition-colors ${
              tab === t.key
                ? 'border-b-2 border-science text-science-on font-semibold -mb-px'
                : 'text-lcars-muted hover:text-lcars-text'
            }`}
          >
            {t.glyph} {t.label}
          </button>
        ))}
      </div>

      {/* Content signals filters */}
      {tab === 'content_signals' && (
        <div className="flex gap-3 flex-wrap">
          <select
            value={contentDays}
            onChange={e => setContentDays(e.target.value)}
            className="rounded-lcars border border-edge bg-panel/40 px-3 py-1 text-sm text-lcars-text"
          >
            <option value="3">Last 3 days</option>
            <option value="7">Last 7 days</option>
            <option value="14">Last 14 days</option>
            <option value="30">Last 30 days</option>
          </select>
          <select
            value={contentPillar}
            onChange={e => setContentPillar(e.target.value)}
            className="rounded-lcars border border-edge bg-panel/40 px-3 py-1 text-sm text-lcars-text"
          >
            <option value="">All pillars</option>
            <option value="operational_resilience">Operational Resilience</option>
            <option value="business_continuity">Business Continuity</option>
            <option value="human_performance">Human Performance</option>
            <option value="wellness_sustainable_performance">Wellness</option>
            <option value="ai_augmented_leadership">AI-Augmented Leadership</option>
            <option value="personal_operating_systems">Personal OS</option>
            <option value="future_of_work">Future of Work</option>
            <option value="decision_quality_governance">Decision Quality</option>
          </select>
        </div>
      )}

      {/* Signal filters */}
      {tab === 'signals' && (
        <div className="flex gap-3 flex-wrap">
          <select
            value={signalDays}
            onChange={e => setSignalDays(e.target.value)}
            className="rounded-lcars border border-edge bg-panel/40 px-3 py-1 text-sm text-lcars-text"
          >
            <option value="1">Last 24h</option>
            <option value="3">Last 3 days</option>
            <option value="7">Last 7 days</option>
            <option value="14">Last 14 days</option>
          </select>
          <select
            value={signalRisk}
            onChange={e => setSignalRisk(e.target.value)}
            className="rounded-lcars border border-edge bg-panel/40 px-3 py-1 text-sm text-lcars-text"
          >
            <option value="">All risk levels</option>
            <option value="HIGH">🔴 High only</option>
            <option value="MEDIUM">🟡 Medium only</option>
            <option value="LOW">🟢 Low only</option>
          </select>
        </div>
      )}

      {loading && <p className="text-sm text-lcars-muted">Loading…</p>}
      {error   && (
        <p className="rounded-lcars border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>
      )}

      {!loading && data && tab === 'latest'          && <LatestBrief       d={data} />}
      {!loading && data && tab === 'signals'         && <SignalsView        d={data} />}
      {!loading && data && tab === 'themes'          && <ThemesView         d={data} />}
      {!loading && data && tab === 'archive'         && <ArchiveView        d={data} />}
      {!loading && data && tab === 'daily_briefs'    && <DailyBriefsView    d={data} />}
      {!loading && data && tab === 'content_signals' && <ContentSignalsView d={data} />}
    </div>
  );
}
