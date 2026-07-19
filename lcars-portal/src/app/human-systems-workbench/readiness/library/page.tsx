'use client';

import { useEffect, useState } from 'react';
import { WorkbenchShell, Card, Badge } from '@/components/ui';
import type { BadgeStatus } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { youtubeSearchUrl, type ExerciseRow } from '@/lib/physical-readiness';

const STATUS_STATUS: Record<string, BadgeStatus> = {
  active: 'success',
  avoid: 'error',
  needs_review: 'warning',
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

  const shellProps = {
    title: 'Exercise Library',
    eyebrow: 'Fitness Readiness',
    homeHref: '/human-systems-workbench',
    tagline: 'USS TJR · Human Systems · Recovery · Medical · Readiness · Evidence-informed, non-diagnostic',
    back: { href: '/human-systems-workbench?domain=readiness', label: 'Readiness' },
  } as const;

  if (loading) {
    return (
      <WorkbenchShell {...shellProps}>
        <p className="p-6 text-center text-[13px] text-wb-ink2">Loading exercise library…</p>
      </WorkbenchShell>
    );
  }

  const groups = groupByEquipment(exercises);

  return (
    <WorkbenchShell {...shellProps}>
      <div className="flex flex-col gap-4">
        <Card title="Exercise Library">
          <p className="mb-3 text-[12px] uppercase tracking-wide text-wb-ink2">{exercises.length} exercises</p>
          <p className="text-[13px] text-wb-ink2">
            The personal catalogue the generator picks from. &ldquo;Avoid&rdquo; and &ldquo;Needs review&rdquo; exercises are
            never selected automatically.
          </p>
        </Card>

        {groups.map(([equipment, group]) => (
          <Card key={equipment} title={equipment}>
            <p className="mb-3 text-[12px] uppercase tracking-wide text-wb-ink2">
              {group.length} exercise{group.length === 1 ? '' : 's'}
            </p>
            <div className="flex flex-col gap-2">
              {group.map((ex) => {
                const expanded = expandedId === ex.id;
                return (
                  <div key={ex.id} className="rounded-md border border-wb-line bg-wb-bg">
                    <button
                      type="button"
                      onClick={() => setExpandedId(expanded ? null : ex.id)}
                      aria-expanded={expanded}
                      className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
                    >
                      <div>
                        <p className="text-[14px] font-semibold text-wb-ink">{ex.name}</p>
                        <p className="text-[11px] capitalize text-wb-ink2">{ex.movement_pattern} · {ex.difficulty}</p>
                      </div>
                      <Badge status={STATUS_STATUS[ex.status]}>{ex.status.replace('_', ' ')}</Badge>
                    </button>
                    {expanded && (
                      <div className="flex flex-col gap-2 border-t border-wb-line px-3 py-3 text-[12px] text-wb-ink">
                        <p><span className="uppercase tracking-wider text-wb-ink2">Muscles: </span>{ex.primary_muscles_json.join(', ')}</p>
                        <p><span className="uppercase tracking-wider text-wb-ink2">Default: </span>{ex.default_sets} x {ex.default_reps || '—'}{ex.default_duration_minutes ? ` (~${ex.default_duration_minutes} min)` : ''}</p>
                        {Object.keys(ex.pain_cautions_json ?? {}).length > 0 && (
                          <p className="text-wb-crit-on">
                            <span className="uppercase tracking-wider text-wb-ink2">Pain caution: </span>
                            {Object.entries(ex.pain_cautions_json).map(([k, v]) => `${k.replace('_', ' ')} ≥ ${v}/10`).join(', ')}
                          </p>
                        )}
                        {ex.regression && <p><span className="uppercase tracking-wider text-wb-ink2">Regression: </span>{ex.regression}</p>}
                        {ex.progression && <p><span className="uppercase tracking-wider text-wb-ink2">Progression: </span>{ex.progression}</p>}
                        <a
                          href={ex.preferred_video_url || youtubeSearchUrl(ex.video_search_query)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-1 inline-block w-fit rounded-md border border-wb-line px-3 py-1.5 font-semibold uppercase tracking-wider text-wb-ink2 transition hover:border-wb-sage-deep"
                        >
                          Find Guide Video ↗
                        </a>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        ))}
      </div>
    </WorkbenchShell>
  );
}
