'use client';

import { useEffect, useState } from 'react';
import { Button, Textarea } from '@/components/ui';
import { updateTaskState, type PersonalTask, type ReadyRoomPosture } from '@/lib/personalTasks';
import { recordSupportCompletion } from './SupportFeedback';

/** Mission 5 — set only by a caller that knows a Ready Room support
 *  intervention actually led to this task (e.g. DecomposeView after a
 *  real UNSTICK ME suggestion). Reaching Done from here IS the outcome
 *  signal (spec: "task completion after a support action IS the outcome
 *  signal") — no extra UI, the completion write below fires the evidence
 *  event alongside it. Deliberately never fired from "I'm stopping
 *  here"/saveAndStop: pausing to resume later (Pick Up Banner) is a
 *  legitimate pattern, not a failure, and must never write a negative
 *  outcome. */
export interface SupportContext {
  interventionId: string;
  posture?: ReadyRoomPosture;
}

/** The "YOU'RE DOING" experience (spec §12) — starting a task should feel
 * like an immediate action, not another admin screen. No timers, streaks,
 * or scores (spec §32) — just the one next physical action. */
export function ActiveTaskView({
  task,
  onDone,
  onPaused,
  onBack,
  supportContext,
  onOverload,
}: {
  task: PersonalTask;
  onDone: () => void;
  onPaused: () => void;
  onBack: () => void;
  /** Mission 5 (optional, default none) — see SupportContext above. */
  supportContext?: SupportContext | null;
  /** Endeavour 27 Stream B (mission §1.1): "This feels too much" reuses
   * TodayStream's existing OverloadView, not a new intervention — optional
   * so callers that don't have that flow (none currently) degrade gracefully. */
  onOverload?: () => void;
}) {
  const [stopping, setStopping] = useState(false);
  const [note, setNote] = useState(task.restart_cue ?? '');
  const [busy, setBusy] = useState(false);
  // One idempotency key per (task, support intervention) pairing — stable
  // across a double-click on Done, regenerated only if the underlying task
  // changes (a fresh ActiveTaskView instance).
  const [completionKey] = useState(() =>
    (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${task.id}-${Date.now()}`),
  );

  const startHere = task.micro_action?.trim() || task.title;

  async function markStarted() {
    if (task.work_state === 'in_progress' || task.work_state === 'paused') return;
    await updateTaskState(task.id, 'in_progress');
  }

  // Mission 7 §18/§29 continuity fix: whatever task the Captain is actually
  // looking at here becomes the one Number One's ambient "I'm stuck" /
  // "still can't start" / "too much" / "done" resolve "it" against —
  // without this, only asking Number One "what matters?" first (a separate
  // step the Captain shouldn't have to remember) set that. Fire-and-forget,
  // same as this file's other best-effort writes — never blocks the
  // execution UI, never surfaces an error of its own.
  useEffect(() => {
    fetch('/api/number-one/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ object_type: 'personal_task', object_id: task.id, object_title: task.title }),
    }).catch(() => { /* best-effort — see comment above */ });
  }, [task.id, task.title]);

  async function complete() {
    setBusy(true);
    await updateTaskState(task.id, 'completed');
    if (supportContext) {
      // Fire-and-forget alongside the completion write — never blocks
      // Done, never surfaces a separate error state (see
      // recordSupportEvent's own fire-and-forget contract).
      void recordSupportCompletion({
        interventionId: supportContext.interventionId,
        taskRef: task.id,
        posture: supportContext.posture,
        idempotencyKey: completionKey,
      });
    }
    setBusy(false);
    onDone();
  }

  async function saveAndStop() {
    setBusy(true);
    await updateTaskState(task.id, 'paused', {
      restart_cue: note.trim() || null,
      stop_point: note.trim() || null,
    });
    setBusy(false);
    onPaused();
  }

  // Enter in_progress the first time this view opens for a not-yet-started
  // task, without blocking the UI on the round trip.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (task.work_state === 'captured') void markStarted(); }, [task.id]);

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-md border border-wb-line bg-wb-surface p-6">
      <div>
        <p className="text-[11px] uppercase tracking-wide text-wb-ink2">You&apos;re doing</p>
        <h2 className="font-serif text-[18px] text-wb-ink">{task.title}</h2>
      </div>

      {!stopping && (
        <>
          <div className="rounded-md bg-wb-sage/10 p-3">
            <p className="text-[11px] uppercase tracking-wide text-wb-sage-deep">Start here</p>
            <p className="mt-1 text-[14px] text-wb-ink">{startHere}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={complete}>Done</Button>
            <Button variant="secondary" disabled={busy} onClick={() => setStopping(true)}>
              I&apos;m stopping here
            </Button>
            <Button variant="ghost" disabled={busy} onClick={onBack}>Back</Button>
          </div>

          {/* Endeavour 27 Stream B (mission §1.1): mockup's "Feeling stuck?"
              panel — every option here is an existing real capability,
              relabeled/reshelled, not new logic (mission's own guidance:
              maps near 1:1 to Mission 4's decomposition/overload/regulation
              support, already built). */}
          <div className="border-t border-wb-line pt-3">
            <p className="mb-2 text-[11px] uppercase tracking-wide text-wb-ink2">Feeling stuck?</p>
            <div className="flex flex-wrap gap-2">
              {/* Mockup shows "Break it down" and "Help me start" as two
                  separate options; this app has one real capability behind
                  both (DecomposeView's Unstick Me for this same task) — no
                  second distinct engine to route to. Merged into one honest
                  link rather than showing two buttons that do the same
                  thing (mission's own no-fabricated-affordance principle). */}
              <a
                href={`/ready-room?domain=unstick&task=${encodeURIComponent(task.id)}`}
                className="rounded-md border border-wb-line px-2.5 py-1.5 text-[12px] text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                Break it down / Help me start
              </a>
              {onOverload && (
                <button
                  type="button"
                  onClick={onOverload}
                  className="rounded-md border border-wb-line px-2.5 py-1.5 text-[12px] text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
                >
                  This feels too much
                </button>
              )}
              <a
                href="/human-systems-workbench?domain=recovery"
                className="rounded-md border border-wb-line px-2.5 py-1.5 text-[12px] text-wb-ink2 hover:border-wb-sage-deep hover:text-wb-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                Take a breath
              </a>
            </div>
          </div>
        </>
      )}

      {stopping && (
        <div className="flex flex-col gap-3 border-t border-wb-line pt-3">
          <p className="text-[13px] text-wb-ink">Leave future-you a clue. Where did you get to?</p>
          <Textarea
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Rubbish is gone. Next sweep the floor."
          />
          <div className="flex gap-2">
            <Button disabled={busy} onClick={saveAndStop}>Save &amp; stop</Button>
            <Button variant="ghost" disabled={busy} onClick={() => setStopping(false)}>Back</Button>
          </div>
        </div>
      )}
    </div>
  );
}
