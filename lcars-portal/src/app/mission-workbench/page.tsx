'use client';

/**
 * Mission Workbench — look-and-feel migration of (app)/missions.
 * Standalone Shell (no LCARS app chrome), matching intelligence-workbench
 * and comms-workbench. Data fetching, filter logic, and capacity-cost
 * rules are unchanged from the LCARS original — see
 * (app)/missions/page.tsx for the version this replaces.
 */

import { useEffect, useState } from 'react';
import { Badge, Card } from '@/components/ui';
import { WorkbenchShell } from '@/components/ui';
import { MissionCard } from './_components/MissionCard';
import { useROSData } from '@/lib/useROSData';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { ACTIVE_STATUSES, COMPLETED_STATUSES } from '@/lib/missionStatus';
import type { Mission, RecoveryPostureBand } from '@/lib/types';

const CAPACITY_COST: Record<string, { postures: RecoveryPostureBand[] }> = {
  P0: { postures: ['STRONG', 'STABLE'] },
  P1: { postures: ['STRONG', 'STABLE', 'FRAGILE'] },
  P2: { postures: ['STRONG', 'STABLE', 'FRAGILE', 'REST'] },
  P3: { postures: ['STRONG', 'STABLE', 'FRAGILE', 'REST', 'UNKNOWN'] },
};

function isSuitableToday(priority: string | undefined, posture: RecoveryPostureBand): boolean {
  if (!priority) return true;
  return CAPACITY_COST[priority]?.postures.includes(posture) ?? true;
}

function OvercommitmentWarning({ posture, activeCount }: { posture: RecoveryPostureBand; activeCount: number }) {
  const thresholds: Partial<Record<RecoveryPostureBand, number>> = { FRAGILE: 3, REST: 1 };
  const limit = thresholds[posture];
  if (!limit || activeCount <= limit) return null;

  return (
    <div className="flex items-start gap-3 rounded-lg border border-wb-warn/50 bg-wb-warn/10 px-4 py-3">
      <span className="shrink-0 text-wb-warn-on">▲</span>
      <div>
        <p className="text-[13px] font-semibold text-wb-warn-on">
          Overcommitment risk — {activeCount} active missions on a {posture} posture day
        </p>
        <p className="mt-0.5 text-[12px] text-wb-ink2">
          {posture === 'REST'
            ? 'Rest posture: limit to 1 essential mission maximum. Defer the rest.'
            : 'FRAGILE posture: recommend no more than 3 active missions. Defer lower-priority work.'}
        </p>
      </div>
    </div>
  );
}

export default function MissionWorkbenchPage() {
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
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  const summary = liveSummary ?? { total: 0, active: 0, in_progress: 0, blocked: 0, completed: 0, by_priority: {} };
  const activeMissions = liveMissions.filter(m => ACTIVE_STATUSES.includes(m.status));
  const displayMissions = filter === 'today'
    ? activeMissions.filter(m => isSuitableToday(m.priority, currentPosture))
    : liveMissions;
  const suitableCount = activeMissions.filter(m => isSuitableToday(m.priority, currentPosture)).length;

  const stats = [
    { label: 'Total', value: summary.total },
    { label: 'Active', value: summary.active },
    { label: 'In Progress', value: summary.in_progress },
    { label: 'Blocked', value: summary.blocked },
    { label: 'Completed', value: summary.completed },
  ];

  return (
    <WorkbenchShell title="Mission Workbench" eyebrow="Mission Registry"
      tagline="USS TJR · Mission Workbench · Registry — capacity-aware filtering, governed approve/reject">
      <div className="flex flex-col gap-4">
        <Card>
          {isLoading ? (
            <p className="text-[13px] italic text-wb-ink2">Loading missions…</p>
          ) : loadError ? (
            <div className="rounded-md border border-wb-crit/40 bg-wb-crit/10 px-4 py-3">
              <p className="text-[13px] font-semibold text-wb-crit-on">{loadError}</p>
              <p className="mt-1 text-[12px] text-wb-ink2">
                These counts could not be read from the registry — this is a load failure, not an
                empty registry. Retry shortly.
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                {stats.map(s => (
                  <div key={s.label} className="rounded-md border border-wb-line bg-wb-bg p-3 text-center">
                    <p className="text-2xl font-bold text-wb-ink">{s.value}</p>
                    <p className="text-[10px] uppercase tracking-wider text-wb-ink2">{s.label}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-wb-ink2">
                {(['P0', 'P1', 'P2', 'P3'] as const).map(p => (
                  <span key={p} className="rounded-md border border-wb-line px-2 py-1 font-mono">
                    {p}: {summary.by_priority[p] ?? 0}
                  </span>
                ))}
              </div>
            </>
          )}
        </Card>

        {/* D-055 capacity filter */}
        <div className="flex flex-col justify-between gap-3 rounded-lg border border-wb-line bg-wb-surface px-4 py-3 sm:flex-row sm:items-center">
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-wb-ink2">
              D-055 · Today&apos;s posture: <span className="text-wb-sage-deep">{currentPosture}</span>
            </p>
            <p className="text-[12px] text-wb-ink">
              {suitableCount} of {activeMissions.length} active missions suitable for today&apos;s capacity.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setFilter('all')}
              className={`rounded-md border px-3 py-1.5 text-[12px] font-semibold transition-colors focus-visible:outline
                focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
                filter === 'all' ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:text-wb-ink'
              }`}
            >
              All missions
            </button>
            <button
              type="button"
              onClick={() => setFilter('today')}
              className={`rounded-md border px-3 py-1.5 text-[12px] font-semibold transition-colors focus-visible:outline
                focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${
                filter === 'today' ? 'border-wb-sage-deep bg-wb-sage-deep/10 text-wb-sage-deep' : 'border-wb-line text-wb-ink2 hover:text-wb-ink'
              }`}
            >
              Suitable today ({suitableCount})
            </button>
          </div>
        </div>

        <OvercommitmentWarning posture={currentPosture} activeCount={activeMissions.length} />

        <Card>
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="font-serif text-lg text-wb-ink">{filter === 'today' ? 'Suitable for Today' : 'All Missions'}</h2>
              <p className="text-[11px] uppercase tracking-wide text-wb-ink2">
                {filter === 'today' ? `${currentPosture} posture · capacity-matched` : 'Sorted by priority'}
              </p>
            </div>
            {filter === 'today' && <Badge status="info">Filtered</Badge>}
          </div>

          {isLoading ? (
            <p className="text-[13px] italic text-wb-ink2">Loading missions…</p>
          ) : loadError ? (
            <p className="text-[13px] text-wb-crit-on">{loadError} No list to show — this is a load failure, not an empty registry.</p>
          ) : displayMissions.length === 0 ? (
            <p className="text-[13px] italic text-wb-ink2">No missions match the current filter.</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {displayMissions.map(m => (
                <MissionCard key={m.mission_id} mission={m} />
              ))}
            </div>
          )}
        </Card>
      </div>
    </WorkbenchShell>
  );
}
