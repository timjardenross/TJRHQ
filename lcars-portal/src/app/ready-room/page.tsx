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
import { rankToday, type PersonalTask } from '@/lib/personalTasks';
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
      wide
    >
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
