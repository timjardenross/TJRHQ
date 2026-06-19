'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { MissionCard } from '@/components/MissionCard';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { missions as mockMissions, missionSummary as mockSummary } from '@/lib/mockData';
import type { Mission, MissionSummary } from '@/lib/types';

const STATUS_FILTERS = ['ALL', 'ACTIVE', 'IN_PROGRESS', 'BLOCKED', 'ASSIGNED', 'REVIEW'] as const;
type StatusFilter = typeof STATUS_FILTERS[number];

function buildSummary(missions: Mission[]): MissionSummary {
  return {
    total: missions.length,
    active: missions.filter((m) => m.status === 'ACTIVE').length,
    in_progress: missions.filter((m) => m.status === 'IN_PROGRESS').length,
    completed: missions.filter((m) => m.status === 'COMPLETE').length,
    blocked: missions.filter((m) => m.status === 'BLOCKED').length,
    by_priority: {
      P0: missions.filter((m) => m.priority === 'P0').length,
      P1: missions.filter((m) => m.priority === 'P1').length,
      P2: missions.filter((m) => m.priority === 'P2').length,
      P3: missions.filter((m) => m.priority === 'P3').length,
    },
    timestamp: new Date().toISOString()
  };
}

export default function MissionsPage() {
  const [missions, setMissions]   = useState<Mission[]>(mockMissions);
  const [summary, setSummary]     = useState<MissionSummary>(mockSummary);
  const [filter, setFilter]       = useState<StatusFilter>('ALL');
  const [isLive, setIsLive]       = useState(false);

  useEffect(() => {
    async function load() {
      const supabase = createSupabaseBrowserClient();
      const { data } = await supabase
        .from('missions')
        .select('*')
        .not('status', 'in', '("COMPLETE","DEFERRED","CANCELLED")')
        .order('priority', { ascending: true });

      if (data && data.length > 0) {
        setMissions(data as Mission[]);
        setSummary(buildSummary(data as Mission[]));
        setIsLive(true);
      }
    }
    load();
  }, []);

  const filtered = filter === 'ALL'
    ? missions
    : missions.filter((m) => m.status === filter);

  const stats: { label: string; value: number; tone: string; filterKey: StatusFilter }[] = [
    { label: 'Total',       value: summary.total,       tone: 'text-command',    filterKey: 'ALL' },
    { label: 'Active',      value: summary.active,      tone: 'text-medical',    filterKey: 'ACTIVE' },
    { label: 'In Progress', value: summary.in_progress, tone: 'text-science',    filterKey: 'IN_PROGRESS' },
    { label: 'Blocked',     value: summary.blocked,     tone: 'text-operations', filterKey: 'BLOCKED' },
  ];

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel
        title="Mission Registry"
        accent="command"
        eyebrow={isLive ? '● Live · Supabase' : '○ Mock data'}
      >
        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map((s) => (
            <button
              key={s.label}
              onClick={() => setFilter(s.filterKey)}
              className={`rounded-lcars border p-3 text-center transition-colors ${
                filter === s.filterKey
                  ? 'border-command/60 bg-command/10'
                  : 'border-edge bg-panel-2/60 hover:border-command/30'
              }`}
            >
              <p className={`font-lcars text-2xl font-bold ${s.tone}`}>{s.value}</p>
              <p className="text-[10px] uppercase tracking-wider text-lcars-muted">{s.label}</p>
            </button>
          ))}
        </div>

        {/* Priority badges */}
        <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-lcars-muted">
          {(['P0', 'P1', 'P2', 'P3'] as const).map((p) => (
            <span key={p} className="rounded-md border border-edge px-2 py-1 font-mono">
              {p}: {summary.by_priority[p]}
            </span>
          ))}
        </div>
      </LCARSPanel>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lcars border px-3 py-1 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
              filter === f
                ? 'border-command bg-command/20 text-command'
                : 'border-edge bg-space/40 text-lcars-muted hover:border-command/40'
            }`}
          >
            {f === 'ALL' ? 'All' : f.replace('_', ' ')}
            {f !== 'ALL' && (
              <span className="ml-1.5 text-[10px] opacity-70">
                {missions.filter((m) => m.status === f).length}
              </span>
            )}
          </button>
        ))}
      </div>

      <LCARSPanel
        title={filter === 'ALL' ? 'Active Missions' : `${filter.replace('_', ' ')} Missions`}
        accent="command"
        eyebrow={`${filtered.length} mission${filtered.length !== 1 ? 's' : ''}`}
      >
        {filtered.length === 0 ? (
          <p className="text-sm text-lcars-muted italic">No missions with this status.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((m) => (
              <MissionCard key={m.mission_id} mission={m} />
            ))}
          </div>
        )}
      </LCARSPanel>
    </div>
  );
}
