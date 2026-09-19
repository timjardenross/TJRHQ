'use client';

// Domains tab (Briefs/Captain's Brief consolidation Phase 3,
// BRIEFS_CAPTAINS_BRIEF_CONSOLIDATION.md §4.1/§6) — one cross-domain
// picture: OSINT/Operational Intelligence, Health, Emergency, Engineering,
// Missions/Objectives, Learning, Opportunities, from a single merged
// document (`/api/briefs/domains`, backed by
// intelligence/brief/domains_view.py::assemble_domains_document()).
//
// Read-only situational awareness, matching captains-chair-workbench's
// own "display + link out" precedent (NeedsYou.tsx, Intelligence.tsx) —
// no approve/reject/execute affordances here. Each card is a synthesized
// picture (posture, confidence, what changed, what matters, watch
// conditions, evidence count), not a raw event dump — evidence stays one
// click away via a collapsible drill-down, never the primary view.

import Link from 'next/link';
import * as Collapsible from '@radix-ui/react-collapsible';
import { Card, RiskPill } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import type { StateTone } from '@/lib/types';
import { AVAILABILITY_LABEL } from '@/lib/domainsShared';
import type { DomainSummary, DomainsDocument } from '@/lib/domainsShared';

const AVAILABILITY_TONE: Record<DomainSummary['availability'], StateTone> = {
  ok: 'ok',
  no_data: 'unknown',
  degraded: 'warn',
  unavailable: 'crit',
};

const SOURCE_LABEL: Record<DomainSummary['source'], string> = {
  event_bus: 'Platform',
  osint: 'OSINT',
};

function relativeTime(iso: string | null): string {
  if (!iso) return 'unknown';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'unknown';
  const diffMs = Date.now() - d.getTime();
  const hours = Math.round(diffMs / 3_600_000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function DomainCard({ domain }: { domain: DomainSummary }) {
  const availabilityTone = stateToneClasses(AVAILABILITY_TONE[domain.availability]);

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-serif text-base text-wb-ink">{domain.label}</h3>
            <span className="rounded-full border border-wb-line px-2 py-0.5 text-[10px] uppercase tracking-wider text-wb-ink2">
              {SOURCE_LABEL[domain.source]}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-wb-ink2">As of {relativeTime(domain.as_of)}</p>
        </div>
        <div className="flex items-center gap-2">
          {domain.availability !== 'ok' && (
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${availabilityTone.border} ${availabilityTone.bg} ${availabilityTone.text}`}>
              {AVAILABILITY_LABEL[domain.availability]}
            </span>
          )}
          <RiskPill value={domain.posture} />
        </div>
      </div>

      {domain.confidence != null && (
        <p className="text-[12px] text-wb-ink2">Confidence: {Math.round(domain.confidence)}%</p>
      )}

      {domain.what_changed && (
        <div>
          <h4 className="mb-1 text-[11px] uppercase tracking-wider text-wb-ink2">What Changed</h4>
          <p className="text-[13px] text-wb-ink">{domain.what_changed}</p>
        </div>
      )}

      {domain.what_matters.length > 0 && (
        <div>
          <h4 className="mb-1 text-[11px] uppercase tracking-wider text-wb-ink2">What Matters</h4>
          <ul className="list-disc space-y-0.5 pl-5 text-[13px] text-wb-ink">
            {domain.what_matters.map((m, i) => <li key={i}>{m}</li>)}
          </ul>
        </div>
      )}

      {domain.watch_conditions.length > 0 && (
        <div>
          <h4 className="mb-1 text-[11px] uppercase tracking-wider text-wb-ink2">Watch</h4>
          <ul className="list-disc space-y-0.5 pl-5 text-[13px] text-wb-ink2">
            {domain.watch_conditions.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

      {domain.evidence_count === 0 ? (
        <p className="text-[12.5px] text-wb-ink2">No signals in this domain right now.</p>
      ) : (
        <Collapsible.Root>
          <Collapsible.Trigger asChild>
            <button
              type="button"
              className="self-start rounded-md border border-wb-line px-2.5 py-1 text-[11.5px] text-wb-ink2 hover:bg-wb-bg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
            >
              Evidence ({domain.evidence_count})
            </button>
          </Collapsible.Trigger>
          <Collapsible.Content>
            <ul className="mt-2 space-y-1.5 border-t border-wb-line pt-2">
              {domain.evidence.map((e, i) => (
                <li key={i} className="flex items-start justify-between gap-2 text-[12.5px]">
                  <span className="text-wb-ink">
                    {e.title}
                    {e.detail && <span className="text-wb-ink2"> — {e.detail}</span>}
                  </span>
                  {e.risk && <RiskPill value={e.risk} />}
                </li>
              ))}
              {domain.evidence.length < domain.evidence_count && (
                <li className="text-[11.5px] text-wb-ink2">
                  +{domain.evidence_count - domain.evidence.length} more — see full detail.
                </li>
              )}
            </ul>
          </Collapsible.Content>
        </Collapsible.Root>
      )}

      {domain.detail_href && (
        <Link href={domain.detail_href} className="text-[12.5px] text-wb-sage-deep underline">
          View full detail →
        </Link>
      )}
    </Card>
  );
}

function DomainGroup({ title, domains }: { title: string; domains: DomainSummary[] }) {
  if (domains.length === 0) return null;
  return (
    <div>
      <h3 className="mb-2 text-[11px] uppercase tracking-wider text-wb-ink2">{title}</h3>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {domains.map((d) => <DomainCard key={d.key} domain={d} />)}
      </div>
    </div>
  );
}

export function DomainsView({ doc, loading, error }: { doc: DomainsDocument | null; loading: boolean; error: string | null }) {
  if (loading && !doc) return <p className="text-sm text-wb-ink2 animate-pulse">Assembling cross-domain picture…</p>;

  if (error) {
    return (
      <Card title="Domains">
        <p className="text-sm text-wb-crit-on">{error}</p>
      </Card>
    );
  }

  if (!doc) {
    return (
      <Card title="Domains">
        <p className="text-sm text-wb-ink2">No domain data available.</p>
      </Card>
    );
  }

  const eventBusDomains = doc.domains.filter((d) => d.source === 'event_bus');
  const osintDomains = doc.domains.filter((d) => d.source === 'osint');

  return (
    <div className="space-y-5">
      {doc.warnings.length > 0 && (
        <div className="space-y-1.5 rounded-lg border border-wb-crit/30 bg-wb-crit/10 p-3">
          {doc.warnings.map((w, i) => (
            <p key={i} className="text-[12.5px] text-wb-crit-on">⚠️ {w}</p>
          ))}
        </div>
      )}

      <DomainGroup title="OSINT / World Intelligence" domains={osintDomains} />
      <DomainGroup title="Platform Domains" domains={eventBusDomains} />
    </div>
  );
}
