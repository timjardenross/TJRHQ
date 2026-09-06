'use client';

// Weekly Review — TJR HQ's weekly synthesis, learning and adaptation loop
// (redesigned 2026-09-05, mission brief "Weekly Review Redesign"). Was a
// per-workbench metrics dashboard ("here is everything HQ collected"); now
// leads with interpreted synthesis ("HQ reviewed the week for you") and
// demotes the original per-workbench cards to a collapsed Source Detail
// drill-down (brief §22) — nothing deleted, just reordered by significance
// instead of by source workbench.
//
// No new source-of-truth tables: every signal is still computed live from
// each workbench's own existing tables (see api/weekly-review/route.ts).
// The synthesis layer (api/weekly-review/synthesis.ts) is pure
// interpretation of that same data plus Human Systems' existing
// StrategicPosture engine — see that file's header comment. Only
// weekly_reviews (migration 0164) persists, now also carrying a flattened
// signal-count snapshot for next week's What-Changed diff.

import { Suspense, useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { fetchWeeklyReview, type WeeklyReviewData } from '@/lib/weeklyReview';
import { PriorWeekNote } from './_components/PriorWeekNote';
import { WeekInReview } from './_components/WeekInReview';
import { WhatChanged } from './_components/WhatChanged';
import { WhatMattered } from './_components/WhatMattered';
import { WhatLearned } from './_components/WhatLearned';
import { CarryForward } from './_components/CarryForward';
import { YouCanIgnore } from './_components/YouCanIgnore';
import { WatchNextWeek } from './_components/WatchNextWeek';
import { NextWeekPosture } from './_components/NextWeekPosture';
import { SourceDetail } from './_components/SourceDetail';
import { CompletePanel } from './_components/CompletePanel';

function Workbench() {
  const [data, setData] = useState<WeeklyReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [nextWeekAccepted, setNextWeekAccepted] = useState(false);

  useEffect(() => {
    fetchWeeklyReview().then((d) => { setData(d); setLoading(false); });
  }, []);

  return (
    <WorkbenchShell wide
      title="Weekly Review"
      eyebrow="Scan · Synthesise · Learn · Adapt"
      tagline="USS TJR · Weekly Review · What happened, what mattered, what HQ learned — one calm pass."
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      {loading && <div className="h-40 animate-pulse rounded-md bg-wb-line/40" />}

      {!loading && !data && (
        <p className="rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-[13px] text-wb-ink2">
          Couldn&apos;t load this week&apos;s review. Try again shortly.
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-4">
          {data.priorWeek && <PriorWeekNote data={data.priorWeek} />}
          <WeekInReview data={data.synthesis.weekInReview} />
          <WhatChanged items={data.synthesis.whatChanged} />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <WhatMattered items={data.synthesis.whatMattered} />
            <WhatLearned items={data.synthesis.learned} />
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CarryForward items={data.synthesis.carryForward} />
            <YouCanIgnore lines={data.synthesis.youCanIgnore} />
          </div>

          <WatchNextWeek items={data.synthesis.watchNextWeek} />

          <NextWeekPosture
            data={data.synthesis.nextWeek}
            accepted={nextWeekAccepted}
            onAccept={() => setNextWeekAccepted(true)}
          />

          <CompletePanel
            summary={data.summary}
            signalCounts={data.signalCounts}
            nextWeekAccepted={nextWeekAccepted}
            nextWeekPosture={data.synthesis.nextWeek.posture}
            acceptedCarryForward={data.synthesis.carryForward.map((c) => c.detail)}
          />

          <SourceDetail summary={data.summary} sections={data.workbenches} />
        </div>
      )}
    </WorkbenchShell>
  );
}

export default function WeeklyReviewWorkbench() {
  return (
    <Suspense fallback={<div className="min-h-[100dvh] bg-wb-bg" />}>
      <Workbench />
    </Suspense>
  );
}
