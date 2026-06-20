'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { MissionCard } from '@/components/MissionCard';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { useROSData } from '@/lib/useROSData';
import { RecoveryConfidencePanel } from '@/components/RecoveryConfidencePanel';
import type { Mission, StatusTone, RecoveryPostureBand } from '@/lib/types';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Specialist {
  id: string;
  name: string;
  role: string | null;
  tags: string[] | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

interface Decision {
  id: string;
  mission_id: string | null;
  decision_type: string | null;
  outcome: string | null;
  timestamp: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(ts: string | null | undefined): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

function decisionTypeTone(type: string | null): StatusTone {
  switch (type?.toLowerCase()) {
    case 'architecture':    return 'science';
    case 'design':          return 'command';
    case 'implementation':  return 'engineering';
    case 'architectural':   return 'science';
    default:                return 'neutral';
  }
}

// ── Mission Load vs Capacity ──────────────────────────────────────────────────

const LOAD_GUIDANCE: Record<RecoveryPostureBand, { label: string; tone: StatusTone; guidance: string; defer: boolean }> = {
  STRONG:  { label: 'Full load permitted',     tone: 'status',     guidance: 'Capacity is high. Active missions may proceed. New starts permitted with review.', defer: false },
  STABLE:  { label: 'Moderate load — monitor', tone: 'command',    guidance: 'Capacity is moderate. Prioritise active missions. Hold new starts unless critical.', defer: false },
  FRAGILE: { label: 'Reduced load — protect',  tone: 'operations', guidance: 'Capacity is low. Pause non-essential missions. Defer new starts and complex decisions.', defer: true },
  REST:    { label: 'Minimal load — rest day', tone: 'medical',    guidance: 'Rest posture. Only essential, low-effort tasks. Defer all active missions where possible.', defer: true },
  UNKNOWN: { label: 'Load unknown',            tone: 'neutral',    guidance: 'Check in to establish today\'s recovery posture before assigning mission load.', defer: false },
};

function MissionLoadPanel({ posture, missions }: { posture: RecoveryPostureBand; missions: Mission[] }) {
  const cfg = LOAD_GUIDANCE[posture];
  const blocked   = missions.filter(m => m.status === 'BLOCKED');
  const deferrable = cfg.defer ? missions.filter(m => m.status !== 'BLOCKED') : [];

  return (
    <LCARSPanel
      title="Mission Load vs Capacity"
      accent="command"
      eyebrow="D-055 · Number One capacity check"
      actions={<StatusBadge label={cfg.label} tone={cfg.tone} />}
    >
      <p className="text-sm text-lcars-text/90 leading-relaxed mb-4">{cfg.guidance}</p>

      <div className="grid gap-3 sm:grid-cols-3 text-center mb-4">
        <div className="rounded-lcars border border-edge bg-space/40 p-3">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Active</p>
          <p className="font-lcars text-2xl font-bold text-command mt-0.5">
            {missions.filter(m => ['ACTIVE','IN_PROGRESS','ASSIGNED'].includes(m.status)).length}
          </p>
        </div>
        <div className="rounded-lcars border border-operations/40 bg-operations/5 p-3">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Blocked</p>
          <p className="font-lcars text-2xl font-bold text-operations mt-0.5">{blocked.length}</p>
        </div>
        <div className="rounded-lcars border border-edge bg-space/40 p-3">
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted">Today&apos;s posture</p>
          <p className="font-lcars text-lg font-bold text-medical mt-0.5">{posture}</p>
        </div>
      </div>

      {blocked.length > 0 && (
        <div className="mb-4">
          <p className="text-[10px] uppercase tracking-wider text-operations mb-2">Blocked — require action</p>
          <div className="flex flex-col gap-2">
            {blocked.map(m => (
              <div key={m.mission_id} className="flex items-center gap-3 rounded-lcars border border-operations/40 bg-operations/5 px-4 py-2">
                <span className="text-operations text-xs">▲</span>
                <span className="font-mono text-[10px] text-lcars-muted shrink-0">{m.mission_id}</span>
                <span className="text-sm text-lcars-text/90 min-w-0 truncate">{m.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {deferrable.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-2">Consider deferring today</p>
          <div className="flex flex-col gap-1.5">
            {deferrable.slice(0, 5).map(m => (
              <div key={m.mission_id} className="flex items-center gap-3 rounded-lcars border border-edge bg-space/30 px-4 py-2">
                <span className="font-mono text-[10px] text-lcars-muted shrink-0">{m.mission_id}</span>
                <span className="text-sm text-lcars-text/70 min-w-0 truncate">{m.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </LCARSPanel>
  );
}

// ── Specialist Roster ─────────────────────────────────────────────────────────

function SpecialistRoster({ specialists }: { specialists: Specialist[] }) {
  if (!specialists.length) {
    return <p className="text-xs text-lcars-muted italic">No specialists on record.</p>;
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {specialists.map((s) => (
        <div
          key={s.id}
          className="rounded-lcars border border-edge bg-panel-2/60 p-3 flex flex-col gap-2"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-lcars-text">{s.name}</h3>
              {s.role && <p className="text-xs text-lcars-muted mt-0.5">{s.role}</p>}
            </div>
            <StatusBadge label="ON DUTY" tone="status" />
          </div>
          {s.tags && s.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {s.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded border border-edge px-1.5 py-0.5 font-mono text-[10px] text-lcars-muted"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Command Overview (Decisions) ──────────────────────────────────────────────

function CommandOverview({ decisions }: { decisions: Decision[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!decisions.length) return null;

  return (
    <LCARSPanel
      title="Command Overview"
      accent="command"
      eyebrow={`${decisions.length} recent decisions`}
    >
      <div className="flex flex-col gap-2">
        {decisions.map((d) => {
          const isOpen = expanded === d.id;
          return (
            <div key={d.id} className="rounded-lcars border border-edge bg-panel-2/60">
              <div className="flex flex-wrap items-start gap-3 p-3">
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-[10px] text-lcars-muted">{d.mission_id ?? '—'}</p>
                  <p className="text-xs text-lcars-text/80 mt-0.5 line-clamp-2">
                    {d.outcome ?? '—'}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {d.decision_type && (
                    <StatusBadge
                      label={d.decision_type.toUpperCase()}
                      tone={decisionTypeTone(d.decision_type)}
                    />
                  )}
                  {d.outcome && d.outcome.length > 80 && (
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : d.id)}
                      className="rounded-md border border-edge px-2 py-1 text-[10px] uppercase tracking-[0.15em] text-lcars-muted hover:border-command hover:text-command transition-colors"
                    >
                      {isOpen ? 'Less' : 'More'}
                    </button>
                  )}
                </div>
              </div>
              {isOpen && d.outcome && (
                <div className="border-t border-edge px-3 pb-3 pt-2">
                  <p className="text-xs leading-relaxed text-lcars-text/80">{d.outcome}</p>
                  <p className="text-[10px] text-lcars-muted mt-2">{fmt(d.timestamp)}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </LCARSPanel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NumberOnePage() {
  const { posture: livePosture } = useROSData();
  const currentPosture = livePosture.posture ?? 'UNKNOWN';

  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [decisions,   setDecisions]   = useState<Decision[]>([]);
  const [missions,    setMissions]    = useState<Mission[]>([]);
  const [isLive,      setIsLive]      = useState(false);
  const [loading,     setLoading]     = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const [specRes, decRes, msnRes] = await Promise.all([
          supabase
            .from('specialists')
            .select('id, name, role, tags, metadata, created_at')
            .order('name'),
          supabase
            .from('decisions')
            .select('id, mission_id, decision_type, outcome, timestamp')
            .order('timestamp', { ascending: false })
            .limit(8),
          supabase
            .from('missions')
            .select('id, mission_id, title, status, priority, department, owner, specialist')
            .in('status', ['ACTIVE', 'IN_PROGRESS', 'ASSIGNED', 'BLOCKED'])
            .order('priority')
            .limit(9),
        ]);
        if (specRes.data?.length) { setSpecialists(specRes.data as Specialist[]); setIsLive(true); }
        if (decRes.data?.length)  setDecisions(decRes.data as Decision[]);
        if (msnRes.data?.length)  setMissions(msnRes.data as unknown as Mission[]);
      } catch {
        // fall through
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Number One — XO Command"
        accent="command"
        eyebrow="Crew · Decisions · Active Missions"
      >
        <p className="text-xs text-lcars-muted">
          Specialist roster, recent command decisions, and active mission load.
        </p>
        <p className="mt-2 text-[10px] uppercase tracking-wider text-lcars-muted">
          {loading ? 'Loading…' : isLive ? '● Live · Supabase' : '○ No data'}
        </p>
      </LCARSPanel>

      <RecoveryConfidencePanel compact />

      <MissionLoadPanel posture={currentPosture} missions={missions} />

      <LCARSPanel
        title="Specialist Roster"
        accent="command"
        eyebrow={loading ? 'Loading…' : `${specialists.length} specialists`}
        actions={specialists.length > 0 ? <StatusBadge label={`${specialists.length} on duty`} tone="status" /> : undefined}
      >
        <SpecialistRoster specialists={specialists} />
      </LCARSPanel>

      <CommandOverview decisions={decisions} />

      {missions.length > 0 && (
        <LCARSPanel
          title="Active Missions"
          accent="command"
          eyebrow={`${missions.length} in progress`}
          actions={<StatusBadge label={`${missions.length} active`} tone="operations" />}
        >
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {missions.map((m) => <MissionCard key={m.mission_id} mission={m} />)}
          </div>
        </LCARSPanel>
      )}
    </div>
  );
}
