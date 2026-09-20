'use client';

// Ready Room — the activation and execution layer for TJR HQ. Two modes:
// DO ("what's worth doing now") and UNSTICK ME ("help me start"). Both read/
// write personal_tasks (migration 0090, extended 0163/0165/0184). Same
// WorkbenchShell + DomainToggle architecture as every other workbench.

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { useUrlSync } from '@/lib/useUrlSync';
import { TodayStream } from './_components/TodayStream';
import { DecomposeView } from './_components/DecomposeView';
import { EYEBROW, isDomain, type Domain } from './_components/types';
import { rankToday, taskAnalytics, type PersonalTask, type TaskAnalytics } from '@/lib/personalTasks';
import { useHumanSystemsContext } from '@/lib/captainsChairData';
import type { SystemPostureBand } from '@/app/human-systems-workbench/_components/types';

// Mission 2 (Capacity & Attention Engine): the initial (unstick-vs-do)
// mode defaults to today's Human Systems posture when the Captain hasn't
// already chosen one -- RECOVER/RESET/PROTECT (reduced capacity) start on
// Unstick Me, ENGAGE/STEADY (normal capacity) start on Do. This is Human
// Systems INFORMING a default, never vetoing a choice (assessed-context.ts's
// own "Human Systems informs, never vetoes" boundary, brief §7): an
// explicit ?domain= URL param, or any click on the toggle, always wins and
// is never overridden by a later posture read. UNKNOWN/loading posture
// changes nothing -- Ready Room's pre-existing 'do' default stands.
const REDUCED_CAPACITY_POSTURES: ReadonlySet<SystemPostureBand> = new Set(['RECOVER', 'RESET', 'PROTECT']);

function Workbench() {
  const params = useSearchParams();
  const { writeParams } = useUrlSync('/ready-room');
  const { context: humanSystems } = useHumanSystemsContext();

  // Mission 6B §8.4: Hub's Needs You deep-links a specific personal-task
  // Needs You item straight into Ready Room's execution surface via
  // ?task=<id> — defaults to 'do' mode (the task list this id lives in)
  // when no ?domain= is also present, since a task deep-link is a stronger
  // signal of Captain intent than Ready Room's own default.
  //
  // Mission 7 item 2: an explicit ?domain=unstick alongside ?task=<id> is
  // now respected rather than overridden — this is the "Help me start"
  // path from a Needs You item straight into Unstick Me for that same
  // task (see DecomposeView's initialTaskId handling), not a task-list
  // deep link. Only ?task=<id> with no ?domain= still defaults to 'do'.
  const initialTaskId = params.get('task');
  const explicitDomainParam = params.get('domain');
  const initialDomain = explicitDomainParam ?? (initialTaskId ? 'do' : null);
  const hadExplicitDomain = isDomain(initialDomain);
  const [domain, setDomain] = useState<Domain>(hadExplicitDomain ? initialDomain : 'do');
  const [todayBadge, setTodayBadge] = useState<number | undefined>(undefined);
  const [taskStates, setTaskStates] = useState<Record<string, number>>({});
  const [analytics, setAnalytics] = useState<TaskAnalytics | null>(null);
  const [refreshSignal, setRefreshSignal] = useState(0);
  // Mission 4: true while either sub-view is showing ActiveTaskView (a
  // single task actually underway) — drives WorkbenchShell's `minimal`
  // mode so nav/switcher/tagline stop competing for attention mid-task.
  const [executing, setExecuting] = useState(false);

  // Only a posture-driven default is allowed to move `domain` on its own --
  // once the Captain has explicitly picked (URL param on load, or any
  // toggle click), this effect must never fire again.
  const captainHasChosen = useRef(hadExplicitDomain);
  useEffect(() => {
    if (captainHasChosen.current) return;
    const posture = humanSystems?.posture;
    if (!posture || posture === 'UNKNOWN') return; // no signal -- keep the pre-existing 'do' default
    setDomain(REDUCED_CAPACITY_POSTURES.has(posture) ? 'unstick' : 'do');
  }, [humanSystems?.posture]);

  const handleLoaded = useCallback((tasks: PersonalTask[]) => {
    setTodayBadge(rankToday(tasks).length);
    setTaskStates(tasks.reduce<Record<string, number>>((acc, task) => { acc[task.work_state] = (acc[task.work_state] ?? 0) + 1; return acc; }, {}));
    setAnalytics(taskAnalytics(tasks));
  }, []);

  const changeDomain = (d: Domain) => {
    captainHasChosen.current = true;
    setDomain(d);
    writeParams((sp) => sp.set('domain', d));
  };

  const right = (
    <DomainToggle
      value={domain}
      onChange={changeDomain}
      ariaLabel="Ready Room mode"
      options={[
        { key: 'do' as const, label: 'Do', badge: todayBadge },
        { key: 'unstick' as const, label: 'Unstick Me' },
      ]}
    />
  );

  return (
    <WorkbenchShell
      title="Ready Room"
      eyebrow={EYEBROW[domain]}
      tagline="The place where things become doable. Nothing falls through. Nothing has to be figured out alone."
      right={executing ? undefined : right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      minimal={executing}
      mode="focus"
      wide
    >
      <div className="focus-reference-surface">
        <div className="focus-reference-kicker">Focus mode · one next action</div>
        {domain === 'do' && Object.keys(taskStates).length > 0 && (
          <div aria-label="Task state summary" className="mb-4 flex flex-wrap gap-2 text-[11px]">
            {(['captured', 'in_progress', 'blocked', 'paused', 'completed'] as const).filter((state) => taskStates[state]).map((state) => (
              <span key={state} className="rounded-full border border-wb-line bg-wb-surface px-2.5 py-1 text-wb-ink2"><strong className="text-wb-ink">{taskStates[state]}</strong> {state.replace('_', ' ')}</span>
            ))}
          </div>
        )}
        {domain === 'do' && analytics && (
          <section aria-labelledby="ready-room-analytics" className="mb-4 rounded-lg border border-wb-line bg-wb-surface p-3">
            <h2 id="ready-room-analytics" className="text-[11px] font-bold uppercase tracking-[0.16em] text-wb-ink2">Task flow signals</h2>
            <p className="mt-1 text-[11px] text-wb-ink2">Observed from task records; these indicate friction, not why it happened.</p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
              <span><strong>{analytics.frictionPoints}</strong> friction points</span>
              <span><strong>{analytics.abandoned}</strong> abandoned</span>
              <span><strong>{analytics.retries}</strong> retries / deferrals</span>
              <span><strong>{analytics.completed}</strong> completed</span>
              <span><strong>{analytics.averageCompletionMinutes ?? '—'}</strong>{analytics.averageCompletionMinutes == null ? '' : ' min avg'}</span>
            </div>
          </section>
        )}
        {domain === 'do' && (
          <TodayStream refreshSignal={refreshSignal} onLoaded={handleLoaded} onExecutingChange={setExecuting} initialTaskId={initialTaskId} />
        )}
        {domain === 'unstick' && (
          <DecomposeView
            initialTaskId={initialTaskId}
            onSaved={() => setRefreshSignal((n) => n + 1)}
            onExecutingChange={setExecuting}
          />
        )}
      </div>
    </WorkbenchShell>
  );
}

export default function ReadyRoomWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
