'use client';

import { useState } from 'react';
import { Button } from '@/components/ui';
import type { ReadyRoomPosture } from '@/lib/personalTasks';

// Mission 5 — Evidence & Adaptive Support. Closes the evidence-loop gap
// discovery found: Ready Room's Mission 4 support surfaces (UNSTICK ME /
// One-Action decomposition, Overload reduction, task completion following
// a support action) had zero feedback hooks — nothing ever told the
// evidence model (capacity_intervention_events, generalised to
// domain='ready_room' by migration 0218) whether a piece of support
// actually helped. This is the one place that writes those events, so
// every attach point (DecomposeView, ActiveTaskView, TodayStream) shares
// exactly the same outcome mapping and idempotency behaviour.

export type SupportFeedback = 'helpful' | 'not_helpful' | 'not_now';

// HELPFUL/NOT HELPFUL/NOT NOW → outcome/would_use_again mapping (spec §12)
// happens server-side in /api/ready-room/support-events/route.ts — the one
// place it needs to be correct, so a client bug here can never write a bad
// outcome directly. NOT NOW must never produce a negative-effectiveness
// signal there — see that route's mapFeedback().

export interface RecordSupportEventParams {
  interventionId: string;
  feedback: SupportFeedback;
  /** personal_tasks id this event relates to, when applicable (null for a
   *  decompose-stage prompt where no task has been saved yet). */
  taskRef?: string | null;
  posture?: ReadyRoomPosture;
  capacityState?: string | null;
  /** One idempotency key per feedback *prompt instance* (or per completion
   *  event) — generate it once when the prompt/opportunity appears and
   *  reuse it across a double-click or a fetch retry, never regenerate it
   *  per click. See /api/ready-room/support-events for the server-side
   *  half of this (spec §31). */
  idempotencyKey: string;
}

export async function recordSupportEvent(params: RecordSupportEventParams): Promise<{ ok: boolean }> {
  try {
    const resp = await fetch('/api/ready-room/support-events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        intervention_id: params.interventionId,
        feedback: params.feedback,
        task_ref: params.taskRef ?? null,
        posture: params.posture ?? 'UNKNOWN',
        capacity_state: params.capacityState ?? null,
        idempotency_key: params.idempotencyKey,
      }),
    });
    return { ok: resp.ok };
  } catch {
    // Fire-and-forget by design (spec: trivially dismissable, never blocks
    // the Captain's flow) — a failed write here loses one evidence point,
    // it never surfaces an error into a screen whose whole point is to be
    // low-friction.
    return { ok: false };
  }
}

/**
 * Inline "Was that helpful?" row (spec §12/§30/§31). Only rendered by a
 * caller that knows a support intervention was actually offered/used —
 * this component itself has no opinion on when that is, so it never
 * causes feedback-fatigue on its own; callers key it per support
 * opportunity (e.g. `key={feedbackNonce}`) so it resets for the next one.
 *
 * Any of the three buttons dismisses the row immediately (optimistic —
 * spec: trivially dismissable) — including "Not now", which still records
 * a non-punitive event. A Captain who ignores the row entirely (navigates
 * away, starts something else) writes nothing at all, which is exactly as
 * neutral as an explicit "Not now".
 */
export function SupportFeedbackPrompt({
  interventionId,
  taskRef,
  posture,
  capacityState,
  label = 'Was that helpful?',
  onRecorded,
}: {
  interventionId: string;
  taskRef?: string | null;
  posture?: ReadyRoomPosture;
  capacityState?: string | null;
  label?: string;
  onRecorded?: (feedback: SupportFeedback) => void;
}) {
  const [dismissed, setDismissed] = useState(false);
  const [idempotencyKey] = useState(() =>
    (typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${interventionId}-${Date.now()}-${Math.random()}`),
  );

  if (dismissed) return null;

  function send(feedback: SupportFeedback) {
    setDismissed(true); // optimistic — never let a slow/failed request keep the prompt visible
    void recordSupportEvent({ interventionId, feedback, taskRef, posture, capacityState, idempotencyKey });
    onRecorded?.(feedback);
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-[12px]">
      <span className="text-wb-ink2">{label}</span>
      <Button size="sm" variant="ghost" onClick={() => send('helpful')}>Helpful</Button>
      <Button size="sm" variant="ghost" onClick={() => send('not_helpful')}>Not helpful</Button>
      <Button size="sm" variant="ghost" onClick={() => send('not_now')}>Not now</Button>
    </div>
  );
}

/** ActiveTaskView completion signal (spec: "task completion after a support
 *  action IS the outcome signal") — no prompt, no UI, fired alongside the
 *  existing completion write. mapFeedback('helpful') is the correct
 *  mapping here: reaching Done via a support-originated task is itself
 *  positive evidence, whereas "I'm stopping here" (paused) is a legitimate
 *  resume-later pattern, never a failure signal, so callers must not call
 *  this from that path. */
export function recordSupportCompletion(params: Omit<RecordSupportEventParams, 'feedback'>): Promise<{ ok: boolean }> {
  return recordSupportEvent({ ...params, feedback: 'helpful' });
}
