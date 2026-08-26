'use client';

// Ready Room — Life Admin Hub + Task Decomposition Engine, one workbench.
//
// Two DomainToggle panes sharing one operating surface (per mission brief:
// "treat Life Admin and Task Decomposition as two halves of the same
// operating surface"), both reading/writing personal_tasks (migration 0090,
// extended 0163). Same WorkbenchShell + DomainToggle architecture as every
// other workbench; see capture-workbench/page.tsx for the sibling pattern.

import { Suspense, useCallback, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { WorkbenchShell, DomainToggle } from '@/components/ui';
import { KpiDashboard } from './_components/KpiDashboard';
import { AttendView } from './_components/AttendView';
import { DecomposeView } from './_components/DecomposeView';
import { EYEBROW, isDomain, type Domain } from './_components/types';
import { countByBucket, type PersonalTask, type TaskCounts } from '@/lib/personalTasks';

function Workbench() {
  const router = useRouter();
  const params = useSearchParams();

  const initialDomain = params.get('domain');
  const [domain, setDomain] = useState<Domain>(isDomain(initialDomain) ? initialDomain : 'attend');
  const [counts, setCounts] = useState<TaskCounts | null>(null);
  const [countsLoading, setCountsLoading] = useState(true);
  const [refreshSignal, setRefreshSignal] = useState(0);

  const handleAttendLoaded = useCallback((tasks: PersonalTask[]) => {
    setCounts(countByBucket(tasks));
    setCountsLoading(false);
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
      ariaLabel="Ready Room domain"
      options={[
        { key: 'attend' as const, label: 'Attend', badge: counts ? counts.now + counts.waiting : undefined },
        { key: 'decompose' as const, label: 'Break It Down' },
      ]}
    />
  );

  return (
    <WorkbenchShell
      title="Ready Room"
      eyebrow={EYEBROW[domain]}
      tagline="USS TJR · Ready Room · Nothing falls through. Nothing has to be figured out alone."
      right={right}
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      {domain === 'attend' && (
        <>
          <KpiDashboard counts={counts} loading={countsLoading} />
          <AttendView refreshSignal={refreshSignal} onLoaded={handleAttendLoaded} />
        </>
      )}
      {domain === 'decompose' && (
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
