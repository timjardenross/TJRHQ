'use client';

// Weekly Review — one calm ritual across every workbench: what happened,
// what slipped, what's coming, what needs attention, what's safe to ignore.
//
// No new source-of-truth tables: every signal is computed live from each
// workbench's own existing tables (see api/weekly-review/route.ts). Only
// weekly_reviews (migration 0164) persists — completion state + a frozen
// summary snapshot, so "review debt" is queryable across visits.

import { Suspense, useEffect, useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { fetchWeeklyReview, type WeeklyReviewData } from '@/lib/weeklyReview';
import { SummaryCards } from './_components/SummaryCards';
import { WorkbenchCard } from './_components/WorkbenchCard';
import { CompletePanel } from './_components/CompletePanel';

function Workbench() {
  const [data, setData] = useState<WeeklyReviewData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchWeeklyReview().then((d) => { setData(d); setLoading(false); });
  }, []);

  return (
    <WorkbenchShell
      title="Weekly Review"
      eyebrow="Scan · Review · Decide · Reset"
      tagline="USS TJR · Weekly Review · What happened, what slipped, what's coming — one calm pass."
      back={{ href: '/workbenches', label: 'Workbenches' }}
    >
      {loading && <div className="h-40 animate-pulse rounded-md bg-wb-line/40" />}

      {!loading && !data && (
        <p className="rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-[13px] text-wb-ink2">
          Couldn&apos;t load this week&apos;s review. Try again shortly.
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-6">
          <SummaryCards summary={data.summary} />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {data.workbenches.map((section) => (
              <WorkbenchCard key={section.key} section={section} />
            ))}
          </div>

          <CompletePanel summary={data.summary} />
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
