'use client';

// Migrated onto WorkbenchShell 2026-09-05 — see ../page.tsx header comment.

import { useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { stateToneClasses } from '@/lib/departments';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { youtubeSearchUrl, type ExerciseRow } from '@/lib/physical-readiness';
import type { StateTone } from '@/lib/types';

const STATUS_TONE: Record<string, StateTone> = {
  active: 'ok',
  avoid: 'crit',
  needs_review: 'warn',
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

  const groups = groupByEquipment(exercises);

  return (
    <WorkbenchShell title="Exercise Library" eyebrow={`${exercises.length} exercises`} tagline="USS TJR · Physical Readiness · Library" back={{ href: '/physical-readiness', label: 'Physical Readiness' }} wide>
      {loading ? (
        <p className="text-xs text-wb-ink2 animate-pulse">Loading exercise library…</p>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border border-wb-line bg-white p-4">
            <p className="text-xs text-wb-ink2">
              The personal catalogue the generator picks from. &ldquo;Avoid&rdquo; and &ldquo;Needs review&rdquo; exercises are
              never selected automatically.
            </p>
          </div>

          {groups.map(([equipment, group]) => (
            <div key={equipment} className="rounded-lg border border-wb-line bg-white p-4">
              <h2 className="mb-1 text-sm font-semibold text-wb-ink">{equipment}</h2>
              <p className="mb-3 text-[11px] text-wb-ink2">{group.length} exercise{group.length === 1 ? '' : 's'}</p>
              <div className="space-y-2">
                {group.map((ex) => {
                  const expanded = expandedId === ex.id;
                  const tone = STATUS_TONE[ex.status] ?? 'unknown';
                  const c = stateToneClasses(tone);
                  return (
                    <div key={ex.id} className="rounded-lg border border-wb-line bg-wb-bg">
                      <button
                        onClick={() => setExpandedId(expanded ? null : ex.id)}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                      >
                        <div>
                          <p className="text-sm font-semibold text-wb-ink">{ex.name}</p>
                          <p className="text-[11px] capitalize text-wb-ink2">{ex.movement_pattern} · {ex.difficulty}</p>
                        </div>
                        <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${c.border} ${c.bg} ${c.text}`}>
                          {ex.status.replace('_', ' ')}
                        </span>
                      </button>
                      {expanded && (
                        <div className="space-y-2 border-t border-wb-line px-3 py-3 text-xs">
                          <p><span className="uppercase tracking-wider text-wb-ink2">Muscles: </span>{ex.primary_muscles_json.join(', ')}</p>
                          <p><span className="uppercase tracking-wider text-wb-ink2">Default: </span>{ex.default_sets} x {ex.default_reps || '—'}{ex.default_duration_minutes ? ` (~${ex.default_duration_minutes} min)` : ''}</p>
                          {Object.keys(ex.pain_cautions_json ?? {}).length > 0 && (
                            <p className="text-wb-warn-on">
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
                            className="mt-1 inline-block w-fit rounded-lg border border-wb-line px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-wb-ink2 hover:border-wb-sage-deep/60"
                          >
                            Find Guide Video ↗
                          </a>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </WorkbenchShell>
  );
}
