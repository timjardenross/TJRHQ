'use client';

import { useEffect, useState } from 'react';
import { Shell } from '@/app/human-systems-workbench/_components/Shell';
import { Card, Badge } from '@/components/ui';
import type { BadgeStatus } from '@/components/ui';
import { createSupabaseBrowserClient } from '@/lib/supabase-browser';
import { SESSION_TYPE_LABELS, type SessionType } from '@/lib/physical-readiness';

interface CheckinSummary {
  energy_state: string;
  back_pain: number;
  knee_pain: number;
  ankle_pain: number;
  neck_shoulder_pain: number;
  general_pain: number;
  time_available_minutes: number;
}

interface SessionRow {
  id: string;
  session_type: SessionType;
  status: string;
  started_at: string;
  duration_minutes: number | null;
  energy_after: string | null;
  pain_after_json: { back_pain?: number; general_pain?: number } | null;
  physical_readiness_checkins: CheckinSummary | null;
}

interface LogRow {
  exercise_id: string;
  skipped: boolean;
  pain_during: number | null;
  physical_exercises: { name: string; movement_pattern: string } | null;
}

const ENERGY_RANK: Record<string, number> = { red: 0, orange: 1, yellow: 2, green: 3 };

/** Map a session status to a wb Badge status (mirrors ReadinessView's idiom). */
function statusBadge(status: string): BadgeStatus {
  if (status === 'completed') return 'success';
  if (status === 'partially_completed') return 'warning';
  if (status === 'stopped') return 'error';
  return 'info';
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' });
}

export default function WorkoutHistoryPage() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createSupabaseBrowserClient();
    (async () => {
      const { data: sessionData } = await supabase
        .from('physical_workout_sessions')
        .select(
          'id, session_type, status, started_at, duration_minutes, energy_after, pain_after_json, physical_readiness_checkins(energy_state, back_pain, knee_pain, ankle_pain, neck_shoulder_pain, general_pain, time_available_minutes)',
        )
        .order('started_at', { ascending: false })
        .limit(30);
      setSessions((sessionData as unknown as SessionRow[]) ?? []);

      const { data: logData } = await supabase
        .from('physical_workout_exercise_logs')
        .select('exercise_id, skipped, pain_during, physical_exercises(name, movement_pattern)')
        .order('created_at', { ascending: false })
        .limit(500);
      setLogs((logData as unknown as LogRow[]) ?? []);

      setLoading(false);
    })();
  }, []);

  const shellProps = {
    title: 'Workout History',
    eyebrow: 'Fitness Readiness',
    back: { href: '/human-systems-workbench?domain=readiness', label: 'Readiness' },
  } as const;

  if (loading) {
    return (
      <Shell {...shellProps}>
        <p className="p-6 text-center text-[13px] text-wb-ink2">Loading history…</p>
      </Shell>
    );
  }

  const completed = sessions.filter((s) => s.status === 'completed' || s.status === 'partially_completed');
  const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const weeklyCompleted = sessions.filter((s) => s.status === 'completed' && new Date(s.started_at).getTime() >= sevenDaysAgo);
  const durations = completed.map((s) => s.duration_minutes).filter((d): d is number => !!d);
  const avgDuration = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null;

  const painBeforeVals = completed.map((s) => s.physical_readiness_checkins?.general_pain).filter((v): v is number => v != null);
  const painAfterVals = completed.map((s) => s.pain_after_json?.general_pain).filter((v): v is number => v != null);
  const avgPainBefore = painBeforeVals.length ? painBeforeVals.reduce((a, b) => a + b, 0) / painBeforeVals.length : null;
  const avgPainAfter = painAfterVals.length ? painAfterVals.reduce((a, b) => a + b, 0) / painAfterVals.length : null;

  let energyImproved = 0, energySame = 0, energyWorse = 0;
  for (const s of completed) {
    const before = s.physical_readiness_checkins?.energy_state;
    const after = s.energy_after;
    if (!before || !after) continue;
    const delta = ENERGY_RANK[after] - ENERGY_RANK[before];
    if (delta > 0) energyImproved++;
    else if (delta < 0) energyWorse++;
    else energySame++;
  }

  const usageCounts = new Map<string, { name: string; count: number }>();
  const skipCounts = new Map<string, { name: string; count: number }>();
  const painByExercise = new Map<string, { name: string; pattern: string; total: number; n: number }>();
  for (const log of logs) {
    const name = log.physical_exercises?.name ?? 'Unknown';
    if (log.skipped) {
      const entry = skipCounts.get(log.exercise_id) ?? { name, count: 0 };
      entry.count += 1;
      skipCounts.set(log.exercise_id, entry);
      continue;
    }
    const usage = usageCounts.get(log.exercise_id) ?? { name, count: 0 };
    usage.count += 1;
    usageCounts.set(log.exercise_id, usage);

    if (log.pain_during != null) {
      const entry = painByExercise.get(log.exercise_id) ?? { name, pattern: log.physical_exercises?.movement_pattern ?? '', total: 0, n: 0 };
      entry.total += log.pain_during;
      entry.n += 1;
      painByExercise.set(log.exercise_id, entry);
    }
  }
  const mostUsed = Array.from(usageCounts.values()).sort((a, b) => b.count - a.count).slice(0, 5);
  const mostSkipped = Array.from(skipCounts.values()).sort((a, b) => b.count - a.count).slice(0, 5);
  const painFlagged = Array.from(painByExercise.values())
    .map((e) => ({ name: e.name, avgPain: e.total / e.n }))
    .filter((e) => e.avgPain >= 5)
    .sort((a, b) => b.avgPain - a.avgPain)
    .slice(0, 5);

  // Cardio tolerance pattern
  const cardioAvg = new Map<string, { total: number; n: number }>();
  for (const log of logs) {
    if (log.skipped || log.pain_during == null) continue;
    if (log.physical_exercises?.movement_pattern !== 'cardio') continue;
    const name = log.physical_exercises.name;
    const entry = cardioAvg.get(name) ?? { total: 0, n: 0 };
    entry.total += log.pain_during;
    entry.n += 1;
    cardioAvg.set(name, entry);
  }
  const cardioRanked = Array.from(cardioAvg.entries())
    .filter(([, v]) => v.n >= 2)
    .map(([name, v]) => ({ name, avg: v.total / v.n }))
    .sort((a, b) => a.avg - b.avg);
  const cardioInsight =
    cardioRanked.length >= 2 && cardioRanked[cardioRanked.length - 1].avg - cardioRanked[0].avg >= 2
      ? `${cardioRanked[0].name} warm-ups appear better tolerated than ${cardioRanked[cardioRanked.length - 1].name} (lower average pain during).`
      : null;

  // Duration consistency pattern
  const durationBuckets = new Map<number, { total: number; completedN: number }>();
  for (const s of sessions) {
    const minutes = s.physical_readiness_checkins?.time_available_minutes;
    if (!minutes) continue;
    const entry = durationBuckets.get(minutes) ?? { total: 0, completedN: 0 };
    entry.total += 1;
    if (s.status === 'completed') entry.completedN += 1;
    durationBuckets.set(minutes, entry);
  }
  const bucketRanked = Array.from(durationBuckets.entries())
    .filter(([, v]) => v.total >= 2)
    .map(([minutes, v]) => ({ minutes, rate: v.completedN / v.total }))
    .sort((a, b) => b.rate - a.rate);
  const durationInsight = bucketRanked.length ? `You are most consistent with ${bucketRanked[0].minutes}-minute sessions (highest completion rate).` : null;

  return (
    <Shell {...shellProps}>
      <div className="flex flex-col gap-4">
        <Card title="Workout History">
          <p className="mb-3 text-[12px] uppercase tracking-wide text-wb-ink2">
            {sessions.length} recent session{sessions.length === 1 ? '' : 's'}
          </p>
          {sessions.length === 0 && <p className="text-[13px] text-wb-ink2">No sessions logged yet.</p>}
        </Card>

        <div className="grid grid-cols-2 gap-3">
          <Card title="This Week">
            <p className="font-serif text-3xl text-wb-ink">{weeklyCompleted.length}</p>
            <p className="text-[11px] text-wb-ink2">completed sessions</p>
          </Card>
          <Card title="Avg Duration">
            <p className="font-serif text-3xl text-wb-ink">{avgDuration ?? '—'}</p>
            <p className="text-[11px] text-wb-ink2">minutes</p>
          </Card>
        </div>

        <Card title="Pain Trend">
          <div className="flex items-center justify-between text-[13px]">
            <span className="text-wb-ink2">Before session (avg)</span>
            <span className="font-serif font-semibold text-wb-ink">{avgPainBefore != null ? avgPainBefore.toFixed(1) : '—'}/10</span>
          </div>
          <div className="mt-1 flex items-center justify-between text-[13px]">
            <span className="text-wb-ink2">After session (avg)</span>
            <span className="font-serif font-semibold text-wb-ink">{avgPainAfter != null ? avgPainAfter.toFixed(1) : '—'}/10</span>
          </div>
        </Card>

        <Card title="Energy: Before vs After">
          <div className="grid grid-cols-3 gap-2 text-center text-[13px]">
            <div><p className="font-serif text-xl text-wb-ok-on">{energyImproved}</p><p className="text-[10px] uppercase text-wb-ink2">Improved</p></div>
            <div><p className="font-serif text-xl text-wb-ink2">{energySame}</p><p className="text-[10px] uppercase text-wb-ink2">Same</p></div>
            <div><p className="font-serif text-xl text-wb-crit-on">{energyWorse}</p><p className="text-[10px] uppercase text-wb-ink2">Lower</p></div>
          </div>
        </Card>

        {(cardioInsight || durationInsight) && (
          <Card title="Patterns">
            <p className="mb-3 text-[12px] uppercase tracking-wide text-wb-ink2">Observed, not prescribed</p>
            <ul className="flex flex-col gap-2 text-[13px] text-wb-ink2">
              {cardioInsight && <li>{cardioInsight}</li>}
              {durationInsight && <li>{durationInsight}</li>}
            </ul>
          </Card>
        )}

        <Card title="Most Used Exercises">
          {mostUsed.length === 0 && <p className="text-[13px] text-wb-ink2">No completed exercises logged yet.</p>}
          <ul className="flex flex-col gap-1.5">
            {mostUsed.map((e) => (
              <li key={e.name} className="flex items-center justify-between text-[13px]">
                <span className="text-wb-ink">{e.name}</span>
                <span className="text-wb-ink2">{e.count}x</span>
              </li>
            ))}
          </ul>
        </Card>

        {mostSkipped.length > 0 && (
          <Card title="Most Skipped">
            <ul className="flex flex-col gap-1.5">
              {mostSkipped.map((e) => (
                <li key={e.name} className="flex items-center justify-between text-[13px]">
                  <span className="text-wb-ink">{e.name}</span>
                  <span className="text-wb-ink2">{e.count}x</span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {painFlagged.length > 0 && (
          <Card title="Exercises Trending Higher Pain">
            <p className="mb-3 text-[12px] uppercase tracking-wide text-wb-ink2">Avg pain during ≥ 5/10</p>
            <ul className="flex flex-col gap-1.5">
              {painFlagged.map((e) => (
                <li key={e.name} className="flex items-center justify-between text-[13px]">
                  <span className="text-wb-ink">{e.name}</span>
                  <Badge status="error">{e.avgPain.toFixed(1)}/10</Badge>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <Card title="Recent Sessions">
          <ul className="flex flex-col gap-2">
            {sessions.map((s) => (
              <li key={s.id} className="flex items-center justify-between rounded-md border border-wb-line bg-wb-bg px-3 py-2 text-[13px]">
                <div>
                  <p className="font-semibold text-wb-ink">{SESSION_TYPE_LABELS[s.session_type] ?? s.session_type}</p>
                  <p className="text-[11px] text-wb-ink2">
                    {fmtDate(s.started_at)}{s.duration_minutes ? ` · ${s.duration_minutes} min` : ''}
                  </p>
                </div>
                <Badge status={statusBadge(s.status)}>{s.status.replace('_', ' ')}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </Shell>
  );
}
