'use client';

import type { PersonalTask } from '@/lib/personalTasks';

/** Mission 4: shared "pick up where you left off" card, extracted from
 * TodayStream so Unstick Me can surface the same paused/restart-cued tasks
 * — a posture-driven default can route the Captain straight into Unstick
 * Me, and a resumable task should never go invisible just because of which
 * domain they landed on (interruption-recovery gap, Stream E). Read-only
 * summary here; "Continue" always happens on the Do side (TaskRow/
 * ActiveTaskView), so this doesn't duplicate that flow. */
export function PickUpBanner({ tasks }: { tasks: PersonalTask[] }) {
  if (tasks.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-wb-sage/40 bg-wb-sage/10 p-3">
      <p className="text-[11px] uppercase tracking-wide text-wb-sage-deep">Pick up where you left off</p>
      {tasks.map((t) => (
        <div key={t.id}>
          <p className="text-[13px] font-medium text-wb-ink">{t.title}</p>
          {t.restart_cue && <p className="text-[12px] text-wb-ink2">{t.restart_cue}</p>}
        </div>
      ))}
      <p className="text-[11px] text-wb-ink2">Switch to Do to continue one of these.</p>
    </div>
  );
}
