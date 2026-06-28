'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { StatusBadge } from '@/components/StatusBadge';
import { ROSPanels } from '@/components/ROSPanels';
import { MobileOperatingPicture } from '@/components/MobileOperatingPicture';
import { MobileAlertDrawer } from '@/components/MobileAlertDrawer';
import { CaptainApprovalQueue } from '@/components/CaptainApprovalQueue';
import ProactiveSignals from '@/components/ProactiveSignals';
import { useROSData } from '@/lib/useROSData';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { toneClasses } from '@/lib/departments';
import { alerts, decisionsAwaitingApproval } from '@/lib/mockData';
import type { RecoveryPostureBand } from '@/lib/types';

// Suppress unused import warning — toneClasses kept per spec
void toneClasses;

// ── Shared micro-components ───────────────────────────────────────────────────

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.25em] text-lcars-muted">{title}</h2>
      {action}
    </div>
  );
}

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lcars border border-edge bg-panel/60 p-3 ${className}`}>
      {children}
    </div>
  );
}

// ── Posture tone map ──────────────────────────────────────────────────────────

const POSTURE_TONE: Record<RecoveryPostureBand, { text: string; border: string; bg: string }> = {
  STRONG:  { text: 'text-status',      border: 'border-status',     bg: 'bg-status/10' },
  STABLE:  { text: 'text-command',     border: 'border-command',    bg: 'bg-command/10' },
  FRAGILE: { text: 'text-operations',  border: 'border-operations', bg: 'bg-operations/10' },
  REST:    { text: 'text-medical',     border: 'border-medical',    bg: 'bg-medical/10' },
  UNKNOWN: { text: 'text-lcars-muted', border: 'border-edge',       bg: 'bg-edge/10' },
};

// ── Captain Capacity Headline ─────────────────────────────────────────────────

function CapacityHeadline({
  posture,
  postureMessage,
  capacityMessage,
}: {
  posture: RecoveryPostureBand;
  postureMessage: string;
  capacityMessage: string;
}) {
  const c = POSTURE_TONE[posture];
  const capacityLabel: Record<RecoveryPostureBand, string> = {
    STRONG:  'High',
    STABLE:  'Moderate',
    FRAGILE: 'Low',
    REST:    'Minimal — rest priority',
    UNKNOWN: 'Unknown',
  };
  return (
    <div className={`rounded-lcars border ${c.border} ${c.bg} p-4`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted mb-1">
            Captain Capacity — D-055
          </p>
          <div className="flex items-baseline gap-3">
            <p className={`font-lcars text-3xl font-bold ${c.text}`}>{capacityLabel[posture]}</p>
            <StatusBadge label={posture} tone={
              posture === 'STRONG'  ? 'status'     :
              posture === 'STABLE'  ? 'command'    :
              posture === 'FRAGILE' ? 'operations' :
              posture === 'REST'    ? 'medical'    : 'neutral'
            } />
          </div>
          <p className="text-xs text-lcars-text/80 mt-2 leading-relaxed max-w-prose">
            {postureMessage || capacityMessage}
          </p>
        </div>
        <div className="flex flex-col gap-2 shrink-0">
          <Link
            href="/recovery-brief"
            className="rounded-lcars border border-medical/40 bg-medical/5 px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-medical hover:border-medical/70 transition-colors text-center"
          >
            Recovery Brief →
          </Link>
          <Link
            href="/captains-log"
            className="rounded-lcars border border-edge px-3 py-2 text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:border-command hover:text-command transition-colors text-center"
          >
            Log Today →
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Fleet Status Conditional ──────────────────────────────────────────────────

function FleetStatusConditional({
  posture,
  children,
}: {
  posture: RecoveryPostureBand;
  children: React.ReactNode;
}) {
  const isProtected = posture === 'FRAGILE' || posture === 'REST';
  const c = POSTURE_TONE[posture];

  if (!isProtected) {
    return <>{children}</>;
  }

  return (
    <Panel>
      <SectionHeader title="Mission Detail" />
      <p className="mb-3 text-[11px] leading-relaxed text-lcars-text/80">
        Recovery posture is{' '}
        <span className={`font-semibold ${c.text}`}>{posture}</span>{' '}
        today. The nervous system benefits from reduced ambient load.
        Mission detail is available when you need it.
      </p>
      <details className="group">
        <summary className="w-full cursor-pointer rounded border border-edge bg-panel-2/60 py-1.5 text-center text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-lcars-text">
          View Active Missions
        </summary>
        <div className="mt-3 flex flex-col gap-4">
          {children}
        </div>
      </details>
    </Panel>
  );
}

// ── Priority Overview ─────────────────────────────────────────────────────────

function PriorityOverview() {
  const alertCount    = alerts.filter((a) => a.level !== 'nominal').length;
  const decisionCount = decisionsAwaitingApproval.length;
  return (
    <Panel>
      <SectionHeader title="Priority Overview" />
      <ul className="flex flex-col gap-2">
        <li className="flex items-center justify-between gap-3 rounded-md border border-edge bg-panel-2/60 p-2">
          <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Decisions awaiting approval</span>
          <span className="font-lcars text-xl font-bold text-command">{decisionCount}</span>
        </li>
        <li className="flex items-center justify-between gap-3 rounded-md border border-edge bg-panel-2/60 p-2">
          <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Alerts requiring attention</span>
          <span className="font-lcars text-xl font-bold text-operations">{alertCount}</span>
        </li>
      </ul>
    </Panel>
  );
}

// ── Requires Attention ────────────────────────────────────────────────────────

function RequiresAttention() {
  const activeAlerts = alerts.filter((a) => a.level !== 'nominal');
  const LEVEL: Record<string, { dot: string; text: string }> = {
    critical: { dot: 'bg-operations', text: 'text-operations' },
    warning:  { dot: 'bg-command',    text: 'text-command' },
    info:     { dot: 'bg-medical',    text: 'text-medical' },
    nominal:  { dot: 'bg-status',     text: 'text-status' },
  };

  const isEmpty = activeAlerts.length === 0 && decisionsAwaitingApproval.length === 0;

  return (
    <Panel>
      <SectionHeader
        title="Requires Attention"
        action={activeAlerts.length > 0
          ? <span className="h-3 w-3 animate-pulse rounded-full bg-operations" />
          : undefined}
      />
      {isEmpty ? (
        <p className="text-[11px] text-lcars-muted">No attention items — all clear.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {activeAlerts.length > 0 && (
            <ul className="flex flex-col gap-2">
              {activeAlerts.map((a) => {
                const s = LEVEL[a.level] ?? LEVEL['info'];
                return (
                  <li key={a.id} className="rounded-md border border-edge bg-panel-2/60 p-2">
                    <Link
                      href={(a as { href?: string }).href ?? '/alerts'}
                      className="flex items-start gap-2 hover:opacity-80 transition-opacity"
                    >
                      <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
                      <div>
                        <p className={`text-[11px] font-bold uppercase ${s.text}`}>{a.title}</p>
                        <p className="text-[10px] text-lcars-muted">{(a as { detail?: string }).detail ?? ''}</p>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          {decisionsAwaitingApproval.length > 0 && (
            <ol className="flex flex-col gap-2">
              {decisionsAwaitingApproval.map((d) => (
                <li key={d.id}>
                  <Link
                    href="/advisory"
                    className="flex gap-2 rounded-md border border-edge bg-panel-2/60 p-2 hover:border-command/60 transition-colors"
                  >
                    <span className="shrink-0 font-mono text-xs font-bold text-command">{d.id}</span>
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold text-lcars-text">{d.title}</p>
                      <p className="text-[10px] text-lcars-muted">{d.detail}</p>
                    </div>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Panel>
  );
}

// ── CoS Brief Snippet ─────────────────────────────────────────────────────────

function CoSBriefSnippet() {
  const alertCount    = alerts.filter((a) => a.level !== 'nominal').length;
  const decisionCount = decisionsAwaitingApproval.length;
  return (
    <Panel className="border-command/30">
      <p className="text-[9px] uppercase tracking-[0.3em] text-lcars-muted mb-0.5">Chief of Staff</p>
      <SectionHeader title="Ask a question or get your daily brief" />
      <p className="text-[11px] text-lcars-text/80 mb-3">
        {decisionCount} decision{decisionCount !== 1 ? 's' : ''} awaiting approval
        {alertCount > 0 ? ` · ${alertCount} active alert${alertCount !== 1 ? 's' : ''}` : ''}.
      </p>
      <Link
        href="/chief-of-staff"
        className="block w-full rounded-lcars border border-command/40 bg-command/10 py-2 text-center text-[10px] uppercase tracking-[0.2em] text-command hover:border-command/70 hover:bg-command/20 transition-colors"
      >
        Open Chief of Staff →
      </Link>
    </Panel>
  );
}

// ── Live Missions ─────────────────────────────────────────────────────────────

interface Mission {
  id: string;
  title: string;
  status: string;
  priority: number | null;
}

function LiveMissions() {
  const [missions, setMissions] = useState<Mission[] | null>(null);
  const [error, setError]       = useState(false);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    supabase
      .from('missions')
      .select('id, title, status, priority')
      .in('status', [
        'Idea', 'Designed', 'Approved for Engineering', 'Implemented',
        'Tested', 'Awaiting Number One Review', 'Validated', 'Requires Rework', 'Blocked',
      ])
      .order('priority', { ascending: true })
      .limit(3)
      .then(({ data, error: err }) => {
        if (err || !data) { setError(true); return; }
        setMissions(data as Mission[]);
      });
  }, []);

  return (
    <Panel>
      <SectionHeader
        title="Live Missions"
        action={
          <Link href="/missions" className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
            View All →
          </Link>
        }
      />
      {missions === null && !error ? (
        <p className="text-[10px] text-lcars-muted">Loading…</p>
      ) : error || (missions ?? []).length === 0 ? (
        <div>
          <p className="text-[11px] text-lcars-muted mb-2">No active missions.</p>
          <Link href="/missions" className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
            View All Missions →
          </Link>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {(missions ?? []).map((m) => (
            <li key={m.id}>
              <Link
                href={`/missions/${m.id}`}
                className="flex items-center justify-between gap-2 rounded-md border border-edge bg-panel-2/60 p-2 hover:border-command/50 transition-colors"
              >
                <p className="text-[11px] font-medium text-lcars-text truncate">{m.title}</p>
                <span className="shrink-0 text-[9px] uppercase tracking-wide text-lcars-muted">{m.status}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

// ── Notebook Widget ───────────────────────────────────────────────────────────

interface NbNote {
  id: string;
  title: string | null;
  raw_content: string;
  status: string;
  created_at: string;
  recommended_route: string | null;
  strategic_alignment_score: number | null;
  routed_entity_type: string | null;
  routed_to_id: string | null;
}

function NotebookWidget() {
  const [readyCount, setReadyCount]         = useState<number | null>(null);
  const [capturedCount, setCapturedCount]   = useState<number | null>(null);
  const [topOpportunity, setTopOpportunity] = useState<NbNote | null>(null);
  const [recentRouted, setRecentRouted]     = useState<NbNote[]>([]);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    supabase
      .from('intelligence_notes')
      .select('id, title, raw_content, status, created_at, recommended_route, strategic_alignment_score, routed_entity_type, routed_to_id')
      .in('status', ['CAPTURED', 'OFFICER_REVIEW', 'NUMBER_ONE_REVIEW', 'READY_FOR_ROUTING', 'ROUTED'])
      .order('created_at', { ascending: false })
      .limit(100)
      .then(({ data }) => {
        if (!data) return;
        const ready    = data.filter((n) => n.status === 'READY_FOR_ROUTING');
        const captured = data.filter((n) => n.status === 'CAPTURED');
        const routed   = data.filter((n) => n.status === 'ROUTED' && n.routed_to_id);
        setReadyCount(ready.length);
        setCapturedCount(captured.length);
        const top = ready.sort((a, b) =>
          (b.strategic_alignment_score ?? 0) - (a.strategic_alignment_score ?? 0)
        )[0] ?? null;
        setTopOpportunity(top as NbNote | null);
        setRecentRouted(routed.slice(0, 3) as NbNote[]);
      });
  }, []);

  const hasAction = (readyCount ?? 0) > 0;

  function noteTitle(n: NbNote) {
    return n.title || n.raw_content.slice(0, 48) + (n.raw_content.length > 48 ? '…' : '');
  }

  return (
    <Panel className={hasAction ? 'border-command/40' : ''}>
      <SectionHeader
        title="Captain's Notebook"
        action={
          <Link href="/captains-notebook" className="text-[10px] uppercase tracking-[0.15em] text-command hover:text-command/70">
            Open →
          </Link>
        }
      />
      {readyCount === null ? (
        <p className="text-[10px] text-lcars-muted">Loading…</p>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${hasAction ? 'bg-command animate-pulse' : 'bg-edge'}`} />
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Ready for routing</span>
            </div>
            <span className={`font-mono text-sm font-bold ${hasAction ? 'text-command' : 'text-lcars-muted'}`}>{readyCount}</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full bg-edge" />
              <span className="text-[10px] uppercase tracking-wide text-lcars-muted">Pending triage</span>
            </div>
            <span className="font-mono text-sm font-bold text-lcars-muted">{capturedCount}</span>
          </div>
          {topOpportunity && (
            <div className="mt-1 rounded border border-command/20 bg-command/5 px-2 py-1.5">
              <p className="text-[9px] uppercase tracking-[0.2em] text-command mb-0.5">Top opportunity</p>
              <p className="text-[10px] text-lcars-text truncate">{noteTitle(topOpportunity)}</p>
              {topOpportunity.recommended_route && (
                <p className="text-[9px] text-lcars-muted">→ {topOpportunity.recommended_route}</p>
              )}
            </div>
          )}
          {recentRouted.length > 0 && (
            <div className="mt-1">
              <p className="text-[9px] uppercase tracking-[0.2em] text-status mb-1">Recent conversions</p>
              {recentRouted.map((n) => (
                <p key={n.id} className="text-[9px] text-lcars-muted/80 truncate">
                  ✓ {noteTitle(n)}{n.routed_entity_type ? ` → ${n.routed_entity_type.replace(/_/g, ' ')}` : ''}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CaptainsChairPage() {
  const { posture, isLoading } = useROSData();
  const currentPosture: RecoveryPostureBand = posture.posture ?? 'UNKNOWN';

  return (
    <div className="flex flex-col gap-4">
      {/* Mobile-only panels */}
      <MobileOperatingPicture />
      <MobileAlertDrawer />

      {/* D-055: Capacity leads the page */}
      {!isLoading && (
        <CapacityHeadline
          posture={currentPosture}
          postureMessage={posture.posture_message ?? ''}
          capacityMessage={posture.capacity_message ?? ''}
        />
      )}

      {/* Fleet section — collapses on FRAGILE/REST */}
      <FleetStatusConditional posture={currentPosture}>
        <ROSPanels />
        <CaptainApprovalQueue />
        <ProactiveSignals />
        <PriorityOverview />
        <RequiresAttention />
        <CoSBriefSnippet />
        <div className="grid gap-4 lg:grid-cols-2">
          <LiveMissions />
          <NotebookWidget />
        </div>
      </FleetStatusConditional>
    </div>
  );
}
