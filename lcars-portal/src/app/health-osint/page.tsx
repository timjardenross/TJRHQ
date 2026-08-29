'use client';

// Domain boundary (2026-08-29, docs/UI-Layer-Debt-Handoff-2026-08-29.md
// Finding 3, resolved): Health OSINT is external, population-level research
// intelligence (health_signals/health_signal_corroboration — clinical
// trials, studies, source reliability, safety escalation). It has zero
// overlap with Human Systems Workbench (/human-systems-workbench), which
// is first-party personal recovery/readiness telemetry
// (capacity_checkins et al.) — disjoint tables, disjoint user tasks.
// Kept as separate workbenches by design, not by drift; no merge needed.
import { Suspense, useCallback, useEffect, useState, type ReactNode } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Card, WorkbenchShell, DomainToggle } from '@/components/ui';
import type { StateTone } from '@/lib/types';
import { stateToneClasses } from '@/lib/departments';

type Domain = 'confidence-matrix' | 'intelligence-summary' | 'source-network' | 'threat-assessment';

type Payload = { domain: Domain; [key: string]: any };

const DOMAIN_OPTIONS: { key: Domain; label: string }[] = [
  { key: 'confidence-matrix', label: 'Health Confidence Matrix' },
  { key: 'intelligence-summary', label: 'Intelligence Summary' },
  { key: 'source-network', label: 'Source Trust Network' },
  { key: 'threat-assessment', label: 'Threat Assessment' },
];

// Health category tag on each signal — purely categorical, not a status/
// severity signal, so it deliberately uses the neutral 'unknown' state tone
// for every entry rather than fabricating an ok/warn/crit reading for a
// topic tag (e.g. "vaccine" is not inherently more/less severe than
// "epidemiology"). Replaces the old per-category emoji glyphs.
const DOMAIN_LABEL: Record<string, string> = {
  epidemiology: 'Epidemiology',
  treatment: 'Treatment',
  supplement: 'Supplement',
  performance: 'Performance',
  mental_health: 'Mental Health',
  vaccine: 'Vaccine',
};

// neuro_* (migration 0160 — adhd/autism/audhd/burnout/masking/regulation/
// sensory/work/sleep/executive_function/treatment/australia_policy/
// lived_experience) is derived rather than hand-listed here: 13 fixed
// entries would drift out of sync the next time a neuro_ code is added
// (exactly what happened to DOMAIN_LABEL itself, which never picked up
// the granular epi_*/performance_*/factor_* codes already live before
// this fix — not backfilled here, out of scope for this change, but
// worth noting DOMAIN_LABEL was already incomplete).
function domainLabel(d?: string) {
  if (d && DOMAIN_LABEL[d]) return DOMAIN_LABEL[d];
  if (d?.startsWith('neuro_')) {
    const ACRONYMS: Record<string, string> = { adhd: 'ADHD', audhd: 'AuDHD', ndis: 'NDIS' };
    return d.slice('neuro_'.length).split('_')
      .map((w) => ACRONYMS[w] || w[0].toUpperCase() + w.slice(1))
      .join(' ');
  }
  return 'Health';
}

/** Small filled-dot + text-label tag, replacing decorative emoji glyphs with
 *  the app's state.ok/warn/crit/unknown token family (tailwind.config.ts /
 *  @/lib/departments). */
function StateTag({ tone, label, className = '' }: { tone: StateTone; label: string; className?: string }) {
  const c = stateToneClasses(tone);
  return (
    <span className={`inline-flex items-center gap-1 align-middle ${className}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${c.dot}`} aria-hidden />
      {label}
    </span>
  );
}

/** Card title replacement (Card's `title` prop is string-only) that renders
 *  the same h2 styling Card would, plus a state dot before the label. */
function CardTitleWithDot({ tone, children }: { tone: StateTone; children: ReactNode }) {
  const c = stateToneClasses(tone);
  return (
    <h2 className="mb-3 flex items-center gap-2 border-b border-wb-line pb-3 font-serif text-lg text-wb-ink">
      <span className={`inline-block h-2 w-2 rounded-full ${c.dot}`} aria-hidden />
      {children}
    </h2>
  );
}

function isDomain(v: string | null): v is Domain {
  return DOMAIN_OPTIONS.some((o) => o.key === v);
}

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get('domain');
  const [domain, setDomainState] = useState<Domain>(isDomain(initial) ? initial : 'intelligence-summary');
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);

  useEffect(() => {
    fetch('/api/health-osint-curation/pending')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setPendingCount(d?.signals?.length ?? null))
      .catch(() => setPendingCount(null));
  }, []);

  const load = useCallback((withSpinner: boolean) => {
    if (withSpinner) setLoading(true);
    const endpoints: Record<Domain, string> = {
      'confidence-matrix': '/api/health-osint/confidence-matrix',
      'intelligence-summary': '/api/health-osint/intelligence-summary',
      'source-network': '/api/health-osint/source-network',
      'threat-assessment': '/api/health-osint/threat-assessment',
    };
    return fetch(endpoints[domain])
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d?.error || 'Failed');
        setError(null);
        setData(d);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed');
        setData({ domain } as Payload);
      })
      .finally(() => { if (withSpinner) setLoading(false); });
  }, [domain]);

  useEffect(() => { load(true); }, [load]);

  const setDomain = (d: Domain) => {
    setDomainState(d);
    // Keep the URL shareable/bookmarkable without a full navigation —
    // matches human-systems-workbench's pattern. Previously a refresh on
    // a non-default tab silently dropped back to Confidence Matrix.
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('domain', d);
    router.replace(`/health-osint?${sp.toString()}`, { scroll: false });
  };

  const renderSignal = (s: any) => {
    // 2026-08-09 gap-closure: a study/trial's published_at can be years old
    // even when collected_at (when we first found it) is recent — e.g.
    // ClinicalTrials.gov registrations. Previously only published_at was
    // shown, so a 2012 trial read as indistinguishable from a genuinely new
    // one. Surface both so "old study, newly discovered" is legible instead
    // of just looking like stale data.
    let discoveredNote: string | null = null;
    if (s.published_at && s.collected_at) {
      const publishedMs = new Date(s.published_at).getTime();
      const collectedMs = new Date(s.collected_at).getTime();
      const gapDays = Math.round((collectedMs - publishedMs) / 86_400_000);
      if (gapDays >= 30) {
        discoveredNote = `new to us ${new Date(s.collected_at).toLocaleDateString()}`;
      }
    }
    return (
      <div key={s.signal_id} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
        {s.source_url ? (
          <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-wb-ink underline decoration-dotted hover:text-wb-sage-deep">
            <StateTag tone="unknown" label={domainLabel(s.health_domain)} className="mr-1.5 text-[10px] font-medium uppercase tracking-wide text-wb-ink2 no-underline" /> {s.title}
          </a>
        ) : (
          <div className="font-semibold text-wb-ink">
            <StateTag tone="unknown" label={domainLabel(s.health_domain)} className="mr-1.5 text-[10px] font-medium uppercase tracking-wide text-wb-ink2" /> {s.title}
          </div>
        )}
        <div>
          {s.source_name}
          {(s.study_design || s.signal_type) && <> • {s.study_design || s.signal_type}</>}
          {s.sample_size ? <> • n={s.sample_size}</> : null}
          {s.p_value != null && <> • p={s.p_value}</>}
          {typeof s.rank_score === 'number' && <> • Score: {s.rank_score.toFixed(1)}</>}
          {s.published_at && <> • Published {new Date(s.published_at).toLocaleDateString()}</>}
          {discoveredNote && (
            <span className="ml-1 rounded-full bg-wb-warn/15 px-1.5 py-0.5 text-[10px] font-medium text-wb-warn-on">{discoveredNote}</span>
          )}
        </div>
        {s.summary && <div className="mt-1 max-w-[70ch] text-wb-ink2">{s.summary}{s.summary.length >= 220 ? '…' : ''}</div>}
        {s.actionable_recommendation && <div className="mt-1 max-w-[70ch] italic">→ {s.actionable_recommendation}</div>}
      </div>
    );
  };

  return (
    <WorkbenchShell
      title="Health OSINT Workbench"
      eyebrow="Medical & Clinical Intelligence"
      tagline="USS TJR · Study Confidence, Source Trust, Safety Escalation"
      tabs={<DomainToggle value={domain} onChange={setDomain} options={DOMAIN_OPTIONS} ariaLabel="Health OSINT view" />}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      right={
        <Link href="/health-osint-curation" className="text-wb-sage-deep hover:underline">
          Curation Queue{pendingCount != null && pendingCount > 0 ? ` (${pendingCount})` : ''} →
        </Link>
      }
    >
      {loading && !data && <div className="py-16 text-center text-[13px] text-wb-ink2">Loading Health OSINT…</div>}
      <div className="mb-4 min-h-[1lh]">
        {error && <p className="rounded-lg border border-wb-crit/40 bg-wb-crit/10 p-3 text-sm text-wb-crit-on">Error: {error}</p>}
      </div>

      {domain === 'confidence-matrix' && data && (
        <div className="space-y-6">
          <Card title="Signal Distribution by Health Category & Confidence">
            {/* 2026-08-09 mobile/iPad review (P2): fixed grid-cols-2 gave
                each category ~170px on a 375px phone for a name + 4
                stacked confidence counts — tight but the real fix is just
                not forcing 2 columns below sm. */}
            <div className="grid grid-cols-1 gap-4 text-[12px] text-wb-ink2 sm:grid-cols-2">
              {Object.entries(data.matrix || {}).map(([cat, conf]: any) => (
                <div key={cat}>
                  <div className="font-semibold text-wb-ink mb-1">{cat}</div>
                  <div>HIGH: {conf.high}</div>
                  <div>MEDIUM: {conf.medium}</div>
                  <div>LOW: {conf.low}</div>
                  <div>UNKNOWN: {conf.unknown}</div>
                </div>
              ))}
            </div>
          </Card>
          <Card title="Coverage Assessment">
            <p className="text-[12px] text-wb-ink2">Total signals: {data.signals?.length || 0}</p>
            <div className="mt-3 space-y-2">
              {data.signals?.slice(0, 10).map((s: any) => (
                <div key={s.signal_id} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                  {s.source_url ? (
                    <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-wb-ink underline decoration-dotted hover:text-wb-sage-deep">
                      <StateTag tone="unknown" label={domainLabel(s.health_domain)} className="mr-1.5 text-[10px] font-medium uppercase tracking-wide text-wb-ink2 no-underline" /> {s.title}
                    </a>
                  ) : (
                    <div className="font-semibold text-wb-ink">
                      <StateTag tone="unknown" label={domainLabel(s.health_domain)} className="mr-1.5 text-[10px] font-medium uppercase tracking-wide text-wb-ink2" /> {s.title}
                    </div>
                  )}
                  <div>{s.category} • {s.confidence_level.toUpperCase()} • {s.source_name} • Score: {s.rank_score?.toFixed?.(1) ?? s.rank_score}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {domain === 'intelligence-summary' && data && (
        <div className="space-y-4">
          {data.high?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="ok">HIGH CONFIDENCE</CardTitleWithDot>
              <div className="space-y-2">{data.high.map(renderSignal)}</div>
            </Card>
          )}
          {data.medium?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="warn">MEDIUM CONFIDENCE</CardTitleWithDot>
              <div className="space-y-2">{data.medium.map(renderSignal)}</div>
            </Card>
          )}
          {data.low?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="crit">LOW CONFIDENCE</CardTitleWithDot>
              <div className="space-y-2">{data.low.map(renderSignal)}</div>
            </Card>
          )}
          {data.unknowns?.length > 0 && (
            <Card>
              <CardTitleWithDot tone="unknown">KNOWN UNKNOWNS</CardTitleWithDot>
              <div className="space-y-2">
                {data.unknowns.map((u: any) => (
                  <div key={u.title} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                    <div className="font-semibold text-wb-ink">{u.title}</div>
                    <div>{u.impact}</div>
                    <div className="italic">Need: {u.need}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {domain === 'source-network' && data && (
        <div className="space-y-6">
          <Card title="Cross-Source Corroboration">
            <div className="text-[12px] text-wb-ink2 space-y-1">
              {Object.entries(data.correlations || {})
                .sort((a: any, b: any) => b[1].signal_count - a[1].signal_count)
                .slice(0, 10)
                .map(([name, info]: any) => (
                  <div key={name}>
                    {name} • {info.signal_count} signals • {info.corroborating_signals} corroborated • agreement {info.agreement_strength}
                  </div>
                ))}
            </div>
          </Card>
          <Card title="Source Reliability (current snapshot)">
            <div className="text-[12px] text-wb-ink2 space-y-1">
              {data.trending?.map((t: any) => (
                <div key={t.source}>{t.source} → SRS {t.srs_to}</div>
              ))}
            </div>
            {data.note && <p className="mt-2 max-w-[70ch] text-[11px] italic text-wb-ink2">{data.note}</p>}
          </Card>
        </div>
      )}

      {domain === 'threat-assessment' && data && (
        <div className="space-y-6">
          <Card title="Safety Escalation Matrix">
            <div className="space-y-2">
              {data.threats?.map((t: any) => (
                <div key={t.threat} className="text-[12px] text-wb-ink2 pb-2 border-b border-wb-line last:border-0">
                  <div className="font-semibold text-wb-ink">
                    {t.threat}
                    {t.fda_flagged && <StateTag tone="crit" label="FDA-flagged" className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide text-state-crit" />}
                  </div>
                  <div>{t.probability}/{t.impact}/{t.confidence} → {t.escalation.toUpperCase()} {t.frequency_reported ? `• ${t.frequency_reported} reports` : ''}</div>
                  <div className="max-w-[70ch] italic">{t.recommendation}</div>
                </div>
              ))}
              {!data.threats?.length && <p>No adverse-event or safety-alert signals in window.</p>}
            </div>
          </Card>
          {data.gaps?.length > 0 && (
            <Card title="Evidence Gaps">
              <div className="text-[12px] text-wb-ink2 space-y-1">
                {data.gaps.map((g: any) => (
                  <div key={g.area} className="max-w-[70ch]">{g.area}: {g.risk} — {g.evidence_gap}</div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </WorkbenchShell>
  );
}

export default function HealthOSINTWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
