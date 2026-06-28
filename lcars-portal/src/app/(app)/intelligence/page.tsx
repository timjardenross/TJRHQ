'use client';

import { useEffect, useState, type ReactNode } from 'react';

/**
 * Intelligence Centre — MSN-0201 rewire.
 * Queries OR intelligence tables directly via /api/intelligence.
 * Tabs: Latest Brief | Signals | Themes | Sources | Archive | Daily Briefs
 */

type Tab = 'latest' | 'signals' | 'themes' | 'sources' | 'archive' | 'daily_briefs';

const TABS: { key: Tab; label: string }[] = [
  { key: 'latest',       label: 'Latest Brief' },
  { key: 'signals',      label: 'Signals' },
  { key: 'themes',       label: 'Themes' },
  { key: 'sources',      label: 'Sources' },
  { key: 'archive',      label: 'ORI Archive' },
  { key: 'daily_briefs', label: 'Daily Briefs' },
];

const RISK_COLOUR: Record<string, string> = {
  HIGH:   'text-red-400',
  MEDIUM: 'text-yellow-400',
  LOW:    'text-green-400',
};
const RISK_ICON: Record<string, string> = { HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢' };
const STATUS_ICON: Record<string, string> = { ok: '✅', stale: '🟡', failed: '❌', degraded: '⚠️', skipped: '⏭' };

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

function deriveRisk(s: any): string {
  const ci = s.customer_impact ?? '';
  const br = s.banking_relevance ?? '';
  if (ci === 'high' || br === 'high') return 'HIGH';
  if (ci === 'medium' || br === 'medium') return 'MEDIUM';
  if (ci === 'low' || br === 'low') return 'LOW';
  return '';
}

function SignalsView({ d }: { d: any }) {
  const signals: any[] = d.signals ?? [];
  if (!signals.length) return <p className="text-sm text-lcars-muted">No signals found for this period.</p>;
  return (
    <div className="flex flex-col gap-2">
      {signals.map((s, i) => {
        const risk = deriveRisk(s);
        return (
          <div key={i} className="rounded-lcars border border-edge bg-panel/30 p-3">
            <div className="flex items-start gap-2">
              <span>{RISK_ICON[risk] ?? '⚪'}</span>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm leading-snug">
                  {s.canonical_url ? (
                    <a href={s.canonical_url} target="_blank" rel="noopener noreferrer"
                       className="hover:underline text-lcars-text">
                      {s.raw_title}
                    </a>
                  ) : s.raw_title}
                </p>
                {s.raw_summary && (
                  <p className="text-xs text-lcars-muted mt-1 line-clamp-2">{s.raw_summary}</p>
                )}
                <div className="flex gap-3 mt-1 text-xs text-lcars-muted flex-wrap">
                  {s.event_type && <span>{s.event_type}</span>}
                  {s.geography  && <span>📍 {s.geography}</span>}
                  {risk         && <span className={RISK_COLOUR[risk]}>{risk}</span>}
                  {s.rank_score != null && <span>Score {s.rank_score}</span>}
                  <span>{(s.collected_at ?? '').slice(0, 10)}</span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
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

function SourcesView({ d }: { d: any }) {
  const sources: any[] = d.sources ?? [];
  const sum = d.summary ?? {};

  if (!sources.length) {
    return (
      <Card title="Sources">
        <p className="text-lcars-muted">No intelligence sources registered yet.</p>
        <p className="text-xs text-lcars-muted mt-1">Sources are populated automatically when the intelligence collector runs. Check <code>intelligence/collectors/</code> and ensure the source registry is seeded.</p>
      </Card>
    );
  }

  const failed = sources.filter(s => s.health?.status === 'failed');
  const stale  = sources.filter(s => s.health?.status === 'stale');
  const ok     = sources.filter(s => s.health?.status === 'ok');
  const other  = sources.filter(s => !['ok','failed','stale'].includes(s.health?.status ?? ''));

  return (
    <div className="flex flex-col gap-3">
      <Card title="Summary">
        <div className="flex gap-6 text-sm">
          <span>✅ {sum.ok ?? 0} ok</span>
          <span>🟡 {sum.stale ?? 0} stale</span>
          <span>❌ {sum.failed ?? 0} failed</span>
          <span className="text-lcars-muted">{sum.total ?? 0} total</span>
        </div>
      </Card>
      {failed.length > 0 && (
        <Card title="Failed Sources">
          <ul className="space-y-1">
            {failed.map((s, i) => (
              <li key={i} className="text-red-400">
                ❌ <strong>{s.source_name}</strong>
                {s.health?.error_message && <span className="text-xs ml-2 text-lcars-muted">{s.health.error_message.slice(0, 80)}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
      {stale.length > 0 && (
        <Card title="Stale Sources">
          <ul className="space-y-1">
            {stale.map((s, i) => (
              <li key={i} className="text-yellow-400">
                🟡 <strong>{s.source_name}</strong>
                <span className="text-xs ml-2 text-lcars-muted">{(s.health?.checked_at ?? '').slice(0, 10)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title={`All Sources (${sources.length})`}>
        <div className="grid gap-1 sm:grid-cols-2">
          {[...ok, ...other].map((s, i) => {
            const st = s.health?.status ?? 'unknown';
            const icon = STATUS_ICON[st] ?? '❓';
            const items = s.health?.items_retrieved;
            return (
              <div key={i} className="text-xs flex items-center gap-1">
                <span>{icon}</span>
                <span className="truncate">{s.source_name}</span>
                {items != null && <span className="text-lcars-muted shrink-0">({items})</span>}
              </div>
            );
          })}
        </div>
      </Card>
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IntelligencePage() {
  const [tab, setTab]       = useState<Tab>('latest');
  const [data, setData]     = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState<string | null>(null);

  // Signal filter state
  const [signalDays, setSignalDays] = useState('7');
  const [signalRisk, setSignalRisk] = useState('');

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

    fetchIntel(params)
      .then(r => !cancelled && setData(r as Record<string, unknown>))
      .catch(e => !cancelled && setError(e instanceof Error ? e.message : 'Failed.'))
      .finally(() => !cancelled && setLoading(false));

    return () => { cancelled = true; };
  }, [tab, signalDays, signalRisk]);

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
            {t.label}
          </button>
        ))}
      </div>

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

      {!loading && data && tab === 'latest'       && <LatestBrief   d={data} />}
      {!loading && data && tab === 'signals'      && <SignalsView    d={data} />}
      {!loading && data && tab === 'themes'       && <ThemesView     d={data} />}
      {!loading && data && tab === 'sources'      && <SourcesView    d={data} />}
      {!loading && data && tab === 'archive'      && <ArchiveView    d={data} />}
      {!loading && data && tab === 'daily_briefs' && <DailyBriefsView d={data} />}
    </div>
  );
}
