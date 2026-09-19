'use client';

// Ready Room — the activation and execution layer for TJR HQ. Two modes:
// DO ("what's worth doing now") and UNSTICK ME ("help me start"). Both read/
// write personal_tasks (migration 0090, extended 0163/0165/0184). Same
// WorkbenchShell + DomainToggle architecture as every other workbench.

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
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
  const router = useRouter();
  const params = useSearchParams();
  const { context: humanSystems } = useHumanSystemsContext();

  const initialDomain = params.get('domain');
  const hadExplicitDomain = isDomain(initialDomain);
  const [domain, setDomain] = useState<Domain>(hadExplicitDomain ? initialDomain : 'do');
  const [todayBadge, setTodayBadge] = useState<number | undefined>(undefined);
  const [refreshSignal, setRefreshSignal] = useState(0);

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
    const sp = new URLSearchParams(Array.from(params.entries()));
    sp.set('domain', d);
    router.replace(`/ready-room?${sp.toString()}`, { scroll: false });
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
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
      wide
    >
      {domain === 'do' && (
        <TodayStream refreshSignal={refreshSignal} onLoaded={handleLoaded} />
      )}
      {domain === 'unstick' && (
        <DecomposeView onSaved={() => setRefreshSignal((n) => n + 1)} />
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
