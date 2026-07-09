'use client';

import { useState, useEffect } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { MissionCard } from '@/components/MissionCard';
import { useROSData } from '@/lib/useROSData';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { ACTIVE_STATUSES, COMPLETED_STATUSES } from '@/lib/missionStatus';
import type { Mission, RecoveryPostureBand } from '@/lib/types';

// ── Capacity cost per priority ─────────────────────────────────────────────────

const CAPACITY_COST: Record<string, { label: string; postures: RecoveryPostureBand[] }> = {
  P0: { label: 'High cost', postures: ['STRONG', 'STABLE'] },
  P1: { label: 'Moderate cost', postures: ['STRONG', 'STABLE', 'FRAGILE'] },
  P2: { label: 'Low cost', postures: ['STRONG', 'STABLE', 'FRAGILE', 'REST'] },
  P3: { label: 'Minimal cost', postures: ['STRONG', 'STABLE', 'FRAGILE', 'REST', 'UNKNOWN'] },
};

// Suitable for today if current posture is in the allowed list for that priority
function isSuitableToday(priority: string | undefined, posture: RecoveryPostureBand): boolean {
  if (!priority) return true;
  return CAPACITY_COST[priority]?.postures.includes(posture) ?? true;
}

// ── Overcommitment warning ─────────────────────────────────────────────────────

function OvercommitmentWarning({ posture, activeCount }: { posture: RecoveryPostureBand; activeCount: number }) {
  const thresholds: Partial<Record<RecoveryPostureBand, number>> = {
    FRAGILE: 3,
    REST:    1,
  };
  const limit = thresholds[posture];
  if (!limit || activeCount <= limit) return null;

  return (
    <div className="rounded-lcars border border-operations/50 bg-operations/10 px-4 py-3 flex gap-3 items-start">
      <span className="text-operations-on shrink-0">▲</span>
      <div>
        <p className="text-sm font-semibold text-operations-on">
          Overcommitment risk — {activeCount} active missions on a {posture} posture day
        </p>
        <p className="text-xs text-lcars-muted mt-0.5">
          {posture === 'REST'
            ? 'Rest posture: limit to 1 essential mission maximum. Defer the rest.'
            : 'FRAGILE posture: recommend no more than 3 active missions. Defer lower-priority work.'}
        </p>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MissionsPage() {
  const { posture: livePosture } = useROSData();
  const currentPosture = livePosture.posture ?? 'UNKNOWN';

  const [filter, setFilter] = useState<'all' | 'today'>('all');
  const [liveMissions, setLiveMissions] = useState<Mission[]>([]);
  const [liveSummary, setLiveSummary] = useState<{
    total: number; active: number; in_progress: number;
    blocked: number; completed: number; by_priority: Record<string, number>;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data, error } = await supabase
          .from('missions')
          .select('id, mission_id, title, status, priority')
          .order('priority', { ascending: true });
        if (error) throw error;
        if (data) {
          setLiveMissions(data as Mission[]);
          const byPriority: Record<string, number> = {};
          data.forEach(m => { if (m.priority) byPriority[m.priority] = (byPriority[m.priority] ?? 0) + 1; });
          setLiveSummary({
            total: data.length,
            active: data.filter(m => ACTIVE_STATUSES.includes(m.status)).length,
            in_progress: data.filter(m => m.status === 'Implemented' || m.status === 'Tested').length,
            blocked: data.filter(m => m.status === 'Blocked').length,
            completed: data.filter(m => COMPLETED_STATUSES.includes(m.status)).length,
            by_priority: byPriority,
          });
        }
      } catch (e) {
        // A genuine fetch failure must not collapse into the all-zero summary,
        // which is indistinguishable from "genuinely no missions". Surface it.
        console.error('missions fetch failed', e);
        setLoadError('Couldn’t load mission data right now.');
      }
      finally { setIsLoading(false); }
    }
    load();
  }, []);

  const summary = liveSummary ?? { total: 0, active: 0, in_progress: 0, blocked: 0, completed: 0, by_priority: {} };
  const activeMissions = liveMissions.filter(m => ACTIVE_STATUSES.includes(m.status));
  const displayMissions = filter === 'today'
    ? activeMissions.filter(m => isSuitableToday(m.priority, currentPosture))
    : liveMissions;

  const stats = [
    { label: 'Total',       value: summary.total,       tone: 'text-command-on' },
    { label: 'Active',      value: summary.active,      tone: 'text-medical-on' },
    { label: 'In Progress', value: summary.in_progress, tone: 'text-science-on' },
    { label: 'Blocked',     value: summary.blocked,     tone: 'text-operations-on' },
    { label: 'Completed',   value: summary.completed,   tone: 'text-status-on' }
  ];

  const suitableCount = activeMissions.filter(m => isSuitableToday(m.priority, currentPosture)).length;

  return (
    <div className="flex flex-col gap-4">

      <LCARSPanel title="Mission Registry" accent="command" eyebrow="Mission Control">
        {isLoading ? (
          <p className="text-sm text-lcars-muted italic">Loading missions…</p>
        ) : loadError ? (
          <div className="rounded-lcars border border-operations/50 bg-operations/10 px-4 py-3">
            <p className="text-sm font-semibold text-operations-on">{loadError}</p>
            <p className="text-xs text-lcars-muted mt-1">
              These counts could not be read from the registry — this is a load failure, not an
              empty registry. Retry shortly.
            </p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {stats.map((s) => (
                <div key={s.label} className="rounded-lcars border border-edge bg-panel-2/60 p-3 text-center">
                  <p className={`font-lcars text-2xl font-bold ${s.tone}`}>{s.value}</p>
                  <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{s.label}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-lcars-muted">
              {(['P0', 'P1', 'P2', 'P3'] as const).map((p) => (
                <span key={p} className="rounded-md border border-edge px-2 py-1 font-mono">
                  {p}: {summary.by_priority[p] ?? 0}
                </span>
              ))}
            </div>
          </>
        )}
      </LCARSPanel>

      {/* D-055 capacity filter */}
      <div className="rounded-lcars border border-edge bg-panel/40 px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-lcars-muted mb-1">D-055 · Today&apos;s posture: <span className="text-medical-on">{currentPosture}</span></p>
          <p className="text-xs text-lcars-text/80">
            {suitableCount} of {activeMissions.length} active missions suitable for today&apos;s capacity.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`rounded-lcars border px-3 py-1.5 text-xs font-semibold transition-colors ${
              filter === 'all' ? 'border-command bg-command/20 text-command-on' : 'border-edge text-lcars-muted hover:border-edge/80'
            }`}
          >
            All missions
          </button>
          <button
            onClick={() => setFilter('today')}
            className={`rounded-lcars border px-3 py-1.5 text-xs font-semibold transition-colors ${
              filter === 'today' ? 'border-medical bg-medical/20 text-medical-on' : 'border-edge text-lcars-muted hover:border-edge/80'
            }`}
          >
            Suitable today ({suitableCount})
          </button>
        </div>
      </div>

      <OvercommitmentWarning posture={currentPosture} activeCount={activeMissions.length} />

      <LCARSPanel
        title={filter === 'today' ? 'Suitable for Today' : 'All Missions'}
        accent="command"
        eyebrow={filter === 'today' ? `${currentPosture} posture · capacity-matched` : 'Sorted by priority'}
        actions={filter === 'today' ? <StatusBadge label="Filtered" tone="medical" /> : undefined}
      >
        {isLoading ? (
          <p className="text-sm text-lcars-muted italic">Loading missions…</p>
        ) : loadError ? (
          <p className="text-sm text-operations-on">{loadError} No list to show — this is a load failure, not an empty registry.</p>
        ) : displayMissions.length === 0 ? (
          <p className="text-sm text-lcars-muted italic">No missions match the current filter.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {displayMissions.map((m) => (
              <MissionCard key={m.mission_id} mission={m} />
            ))}
          </div>
        )}
      </LCARSPanel>

    </div>
  );
}
