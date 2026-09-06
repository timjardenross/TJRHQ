'use client';

// Ready Room — the activation and execution layer for TJR HQ. Two modes:
// DO ("what's worth doing now") and UNSTICK ME ("help me start"). Both read/
// write personal_tasks (migration 0090, extended 0163/0165/0184). Same
// WorkbenchShell + DomainToggle architecture as every other workbench.

import { Suspense, useCallback, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { TodayStream } from './_components/TodayStream';
import { DecomposeView } from './_components/DecomposeView';
import { EYEBROW, isDomain, type Domain } from './_components/types';
import { rankToday, type PersonalTask } from '@/lib/personalTasks';

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();

  const initialDomain = params.get('domain');
  const [domain, setDomain] = useState<Domain>(isDomain(initialDomain) ? initialDomain : 'do');
  const [todayBadge, setTodayBadge] = useState<number | undefined>(undefined);
  const [refreshSignal, setRefreshSignal] = useState(0);

  const handleLoaded = useCallback((tasks: PersonalTask[]) => {
    setTodayBadge(rankToday(tasks).length);
  }, []);

  const changeDomain = (d: Domain) => {
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
