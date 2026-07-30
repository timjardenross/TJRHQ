'use client';

import { useEffect, useState } from 'react';
import { LCARSPanel } from '@/components/LCARSPanel';
import { StatusBadge } from '@/components/StatusBadge';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { youtubeSearchUrl, type ExerciseRow } from '@/lib/physical-readiness';

const STATUS_TONE: Record<string, 'status' | 'operations' | 'command'> = {
  active: 'status',
  avoid: 'operations',
  needs_review: 'command',
};

function groupByEquipment(exercises: ExerciseRow[]): [string, ExerciseRow[]][] {
  const groups = new Map<string, ExerciseRow[]>();
  for (const ex of exercises) {
    const list = groups.get(ex.equipment) ?? [];
    list.push(ex);
    groups.set(ex.equipment, list);
  }
  return Array.from(groups.entries());
}

export default function ExerciseLibraryPage() {
  const [exercises, setExercises] = useState<ExerciseRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    (async () => {
      const { data } = await supabase.from('physical_exercises').select('*').order('equipment').order('name');
      setExercises((data as ExerciseRow[]) ?? []);
      setLoading(false);
    })();
  }, []);

  if (loading) return <p className="p-6 text-center text-sm text-lcars-muted">Loading exercise library…</p>;

  const groups = groupByEquipment(exercises);

  return (
    <div className="flex flex-col gap-4">
      <LCARSPanel title="Exercise Library" accent="medical" eyebrow={`${exercises.length} exercises`}>
        <p className="text-xs text-lcars-muted">
          The personal catalogue the generator picks from. &ldquo;Avoid&rdquo; and &ldquo;Needs review&rdquo; exercises are
          never selected automatically.
        </p>
      </LCARSPanel>

      {groups.map(([equipment, group]) => (
        <LCARSPanel key={equipment} title={equipment} accent="medical" eyebrow={`${group.length} exercise${group.length === 1 ? '' : 's'}`}>
          <div className="flex flex-col gap-2">
            {group.map((ex) => {
              const expanded = expandedId === ex.id;
              return (
                <div key={ex.id} className="rounded-lcars border border-edge bg-space/40">
                  <button
                    onClick={() => setExpandedId(expanded ? null : ex.id)}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
                  >
                    <div>
                      <p className="text-sm font-semibold text-lcars-text">{ex.name}</p>
                      <p className="text-[11px] text-lcars-muted capitalize">{ex.movement_pattern} · {ex.difficulty}</p>
                    </div>
                    <StatusBadge label={ex.status.replace('_', ' ')} tone={STATUS_TONE[ex.status]} />
                  </button>
                  {expanded && (
                    <div className="flex flex-col gap-2 border-t border-edge px-3 py-3 text-xs">
                      <p><span className="uppercase tracking-wider text-lcars-muted">Muscles: </span>{ex.primary_muscles_json.join(', ')}</p>
                      <p><span className="uppercase tracking-wider text-lcars-muted">Default: </span>{ex.default_sets} x {ex.default_reps || '—'}{ex.default_duration_minutes ? ` (~${ex.default_duration_minutes} min)` : ''}</p>
                      {Object.keys(ex.pain_cautions_json ?? {}).length > 0 && (
                        <p className="text-operations-on">
                          <span className="uppercase tracking-wider text-lcars-muted">Pain caution: </span>
                          {Object.entries(ex.pain_cautions_json).map(([k, v]) => `${k.replace('_', ' ')} ≥ ${v}/10`).join(', ')}
                        </p>
                      )}
                      {ex.regression && <p><span className="uppercase tracking-wider text-lcars-muted">Regression: </span>{ex.regression}</p>}
                      {ex.progression && <p><span className="uppercase tracking-wider text-lcars-muted">Progression: </span>{ex.progression}</p>}
                      <a
                        href={ex.preferred_video_url || youtubeSearchUrl(ex.video_search_query)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-block w-fit rounded-lcars border border-edge px-3 py-1.5 font-semibold uppercase tracking-wider text-lcars-muted hover:border-medical/60"
                      >
                        Find Guide Video ↗
                      </a>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </LCARSPanel>
      ))}
    </div>
  );
}
