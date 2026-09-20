'use client';

import { useState } from 'react';
import { WorkbenchShell } from '@/components/ui';
import { FocusLane } from '@/components/FocusLane';

const durations = [5, 15, 25, 45];
export default function FocusWorkbench() {
  const [duration, setDuration] = useState(15);
  const [quiet, setQuiet] = useState(false);
  return <WorkbenchShell title="Focus Workbench" eyebrow="ADHD-friendly execution" tagline="One small step. A clear finish line. Return whenever you need." back={{ href: '/captains-chair-workbench', label: "Captain's Chair" }} mode="focus"><div className="space-y-4"><FocusLane item={{ title: 'Choose what deserves your attention', nextStep: 'Name one thing you want to move forward, then take the smallest visible step.', source: "Captain's Chair", energy: 'medium' }} />{!quiet && <div className="grid gap-4 sm:grid-cols-2"><section className="rounded-xl border border-wb-line bg-wb-surface p-4"><h2 className="font-semibold">Time-box it</h2><p className="mt-1 text-sm text-wb-ink2">Pick an ending point so focus does not become endless.</p><div className="mt-3 flex flex-wrap gap-2">{durations.map((n) => <button key={n} type="button" aria-pressed={duration === n} onClick={() => setDuration(n)} className={`rounded-md border px-3 py-2 text-sm ${duration === n ? 'border-wb-sage-deep bg-wb-sage-deep/20 text-wb-ink' : 'border-wb-line text-wb-ink2'}`}>{n} min</button>)}</div><p className="mt-3 text-[12px] text-wb-ink2">Selected focus window: {duration} minutes.</p></section><section className="rounded-xl border border-wb-line bg-wb-surface p-4"><h2 className="font-semibold">If you get stuck</h2><p className="mt-1 text-sm text-wb-ink2">Make the step smaller, park it without guilt, or return to Ready Room for help.</p><div className="mt-3 flex flex-wrap gap-2"><a href="/ready-room?domain=unstick" className="rounded-md bg-wb-sage-deep px-3 py-2 text-[12px] font-semibold text-white">Help me start</a><a href="/ready-room" className="rounded-md border border-wb-line px-3 py-2 text-[12px] text-wb-ink2">Choose another task</a></div></section></div>}<button type="button" onClick={() => setQuiet((v) => !v)} className="rounded-md border border-wb-line px-3 py-2 text-[12px] text-wb-ink2 hover:border-wb-sage">{quiet ? 'Show support panels' : 'Enter low-distraction mode'}</button></div></WorkbenchShell>;
}
