'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { recoveryBrief as mockBrief } from '@/lib/mockData';
import { useROSData } from '@/lib/useROSData';
import { toneClasses } from '@/lib/departments';
import { RecoveryConfidencePanel } from '@/components/RecoveryConfidencePanel';
import { WellnessInsightPanel } from '@/components/WellnessInsightPanel';
import type { RecoveryPostureBand, StatusTone } from '@/lib/types';

// ── Tone helpers ──────────────────────────────────────────────────────────────

const POSTURE_TONE: Record<RecoveryPostureBand, StatusTone> = {
  STRONG:  'status',
  STABLE:  'command',
  FRAGILE: 'operations',
  REST:    'medical',
  UNKNOWN: 'neutral'
};

// ── Section divider ───────────────────────────────────────────────────────────

function SectionRule({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="h-px flex-1 bg-edge/60" />
      <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.3em] text-lcars-muted">
        {label}
      </span>
      <div className="h-px flex-1 bg-edge/60" />
    </div>
  );
}

// ── Recovery Brief ────────────────────────────────────────────────────────────

export default function RecoveryBriefPage() {
  const { posture: livePosture, bodyContext, isLive, isLoading } = useROSData();

  // MSN-0351: this brief carries only fields with a genuine live source. The
  // previous version spread a mock template (mockBrief) and rendered several
  // never-replaced mock fields (guidance, afternoon_note, load_summary, the
  // mission/decision/fleet notes) under a "● Live" badge — those blocks have
  // been removed rather than presented as live. `stardate` is a decorative
  // constant (not health/mission data); `sleep_summary` falls back to the mock
  // string only when bodyContext itself carries no live sleep figure.
  const brief = {
    stardate:         mockBrief.stardate,
    posture:          livePosture.posture,
    posture_message:  livePosture.posture_message,
    capacity_message: livePosture.capacity_message,
    best_window:      livePosture.best_window,
    sleep_summary:    bodyContext.sleep_hours
      ? `${bodyContext.sleep_hours}h · ${bodyContext.sleep_quality}${bodyContext.cpap_compliant ? ' · CPAP compliant' : ''}`
      : mockBrief.sleep_summary,
    nervous_system:   bodyContext.nervous_system_state,
    energy:           bodyContext.energy
  };

  const postureTone = POSTURE_TONE[brief.posture];
  const pc = toneClasses(postureTone);

  // Real generation time — set client-side only, after mount, so the SSR
  // pass and the first client render never disagree (a `new Date()` read
  // directly in render body mismatches whenever the clock crosses a minute
  // boundary between the two passes).
  const [generated, setGenerated] = useState<string | null>(null);
  useEffect(() => {
    setGenerated(
      new Date().toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })
    );
  }, []);

  return (
    <div className="flex flex-col gap-4">

      {/* Header */}
      <LCARSPanel
        title="Recovery Brief"
        accent="medical"
        eyebrow={`Stardate ${brief.stardate}${generated ? ` · Generated ${generated}` : ''}`}
        actions={<StatusBadge label={brief.posture} tone={postureTone} />}
      >
        <p className="text-xs text-lcars-muted mb-2">
          The Recovery Brief leads with what the nervous system needs today.
          Mission detail follows when capacity supports it.
        </p>
        <p className="text-[10px] uppercase tracking-wider text-lcars-muted">
          {isLoading ? 'Loading live data…' : isLive ? '● Live · Supabase' : '○ Mock data — no check-in today'}
        </p>
      </LCARSPanel>

      {/* ── Recovery Confidence ── */}
      <RecoveryConfidencePanel />

      {/* ── Recovery Posture ── */}
      <LCARSPanel title="Recovery Posture" accent="medical" eyebrow="What does my system need today?">
        <div className={`rounded-lcars border ${pc.border} ${pc.bg} p-5`}>
          <p className={`font-sans text-3xl font-bold ${pc.text}`}>{brief.posture}</p>
          <p className="mt-2 text-sm text-lcars-text/90 leading-relaxed">{brief.posture_message}</p>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Sleep last night</p>
            <p className="mt-1 text-sm text-lcars-text/90">{brief.sleep_summary}</p>
          </div>
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Nervous system</p>
            <p className="mt-1 text-sm text-lcars-text/90 capitalize">{brief.nervous_system}</p>
          </div>
          <div className="rounded-lcars border border-edge bg-space/40 p-3">
            <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Energy</p>
            <p className="mt-1 text-sm text-lcars-text/90">{brief.energy}</p>
          </div>
        </div>
      </LCARSPanel>

      {/* ── Capacity Today ── */}
      <LCARSPanel title="Capacity Today" accent="medical" eyebrow="What capacity is available?">
        <div className="rounded-lcars border border-command/40 bg-command/5 p-4">
          <p className="text-sm text-lcars-text/90 leading-relaxed">{brief.capacity_message}</p>
          <div className="mt-3 flex flex-wrap gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Best window</p>
              <p className="font-sans text-lg font-semibold text-command-on">{brief.best_window}</p>
            </div>
          </div>
        </div>
      </LCARSPanel>

      {/* ── Wellness Intelligence — live from health_insights ── */}
      <WellnessInsightPanel />

      {/*
        MSN-0351: the "Recovery Guidance", "Today's Sustainable Load", and the
        Fleet summary blocks previously rendered fixed mock content (standing
        orders, a fabricated MSN-0062 note, "No blockers. Crew nominal.") under
        a "● Live" badge with no live source behind them. Those blocks have been
        removed. Live wellness guidance is above (WellnessInsightPanel); real
        mission load and fleet status live on the Captain's Chair.
      */}

      {/* ── Fleet & mission detail (pointer — no fabricated status) ── */}
      <LCARSPanel title="Mission &amp; Fleet" accent="medical" eyebrow="Context — available when needed">
        <p className="text-sm text-lcars-text/80">
          Live mission load and fleet status are maintained on the Captain&apos;s Chair.
        </p>
        <Link
          href="/captains-chair-workbench"
          className="mt-2 block text-xs text-command-on hover:opacity-70"
        >
          Full mission detail and fleet status → Captain&apos;s Chair
        </Link>
      </LCARSPanel>

      {/* ── D-055: Complete the loop — log today's entry ── */}
      <div className="rounded-lcars border border-edge bg-panel/40 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.25em] text-lcars-muted mb-1">End of day</p>
          <p className="text-sm text-lcars-text/90">
            Complete today&apos;s Captain&apos;s Log entry to close the recovery loop.
          </p>
        </div>
        <Link
          href="/captains-log"
          className="shrink-0 rounded-lcars bg-medical px-4 py-2 font-sans text-xs font-bold uppercase tracking-[0.2em] text-white hover:opacity-80 transition-opacity"
        >
          Log Today →
        </Link>
      </div>

    </div>
  );
}
