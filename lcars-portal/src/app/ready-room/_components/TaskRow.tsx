'use client';

import { useState } from 'react';
import { Badge, Button, Textarea } from '@/components/ui';
import {
  categoryMeta,
  followThroughModeMeta,
  updateTaskState,
  toggleFollowThroughPause,
  type PersonalTask,
  type WorkState,
} from '@/lib/personalTasks';

function dueLabel(due: string | null): string | null {
  if (!due) return null;
  const daysOut = Math.round((new Date(due).getTime() - Date.now()) / 86_400_000);
  if (daysOut < 0) return `Overdue · ${new Date(due).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}`;
  if (daysOut === 0) return 'Due today';
  if (daysOut === 1) return 'Due tomorrow';
  return `Due ${new Date(due).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}`;
}

/** One task/life-admin item row. Always shows what a "waiting" item is
 * waiting on, and — when re-opening a paused/blocked item — its restart
 * cue, so resuming after an interruption never starts from a blank page. */
export function TaskRow({ task, onChanged }: { task: PersonalTask; onChanged: () => void }) {
  const meta = categoryMeta(task.category);
  const ftMeta = followThroughModeMeta(task.follow_through_mode);
  const due = dueLabel(task.due_date);
  const [waitingDraft, setWaitingDraft] = useState(task.waiting_on ?? '');
  const [showWaitingForm, setShowWaitingForm] = useState(false);
  const [busy, setBusy] = useState(false);

  async function setState(work_state: WorkState, extra?: Parameters<typeof updateTaskState>[2]) {
    setBusy(true);
    await updateTaskState(task.id, work_state, extra);
    setBusy(false);
    onChanged();
  }

  async function togglePause() {
    setBusy(true);
    await toggleFollowThroughPause(task.id, !task.follow_through_paused);
    setBusy(false);
    onChanged();
  }

  const showRestartCue = (task.work_state === 'blocked' || task.work_state === 'paused') && task.restart_cue;

  return (
    <div className="rounded-md border border-wb-line bg-wb-surface p-3">
      <div className="flex flex-col gap-2">
        <div className="min-w-0">
          <div className="flex items-start gap-2">
            <span aria-hidden className="shrink-0 text-wb-ink2">{meta.glyph}</span>
            <span className="break-words text-[14px] font-medium text-wb-ink">{task.title}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Badge status="neutral">{meta.label}</Badge>
            <span title={ftMeta.hint}>
              <Badge status="neutral">{ftMeta.label}</Badge>
            </span>
            {due && <span className="text-[11px] text-wb-ink2">{due}</span>}
          </div>
          {task.context && (
            <p className="mt-1.5 break-words text-[12px] text-wb-ink2">{task.context}</p>
          )}
          {task.work_state === 'blocked' && (
            <p className="mt-1.5 text-[12px] text-wb-warn-on">
              Waiting on: {task.waiting_on || 'not noted yet'}
            </p>
          )}
          {task.micro_action && task.work_state !== 'completed' && (
            <p className="mt-1.5 text-[12px] text-wb-ink2">First step: {task.micro_action}</p>
          )}
          {showRestartCue && (
            <p className="mt-1.5 rounded bg-wb-sage/10 px-2 py-1 text-[12px] text-wb-sage-deep">
              Restart here: {task.restart_cue}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {task.work_state !== 'completed' && (
            <Button size="sm" variant="primary" disabled={busy} onClick={() => setState('completed')}>
              Done
            </Button>
          )}
          {task.work_state !== 'blocked' && task.work_state !== 'completed' && (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setShowWaitingForm(true)}>
              Waiting on…
            </Button>
          )}
          {task.work_state === 'blocked' && (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setState('captured')}>
              No longer waiting
            </Button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={togglePause}
            title={task.follow_through_paused ? 'Follow-through muted — click to unmute' : 'Mute follow-through nudges for this item'}
            className="ml-auto text-[13px] text-wb-ink2 opacity-60 hover:opacity-100 disabled:opacity-30"
          >
            {task.follow_through_paused ? '🔕' : '🔔'}
          </button>
        </div>
      </div>

      {showWaitingForm && (
        <div className="mt-3 flex items-end gap-2 border-t border-wb-line pt-3">
          <div className="flex-1">
            <Textarea
              label="What / who is this waiting on?"
              rows={1}
              value={waitingDraft}
              onChange={(e) => setWaitingDraft(e.target.value)}
              placeholder="e.g. accountant's reply"
            />
          </div>
          <Button
            size="sm"
            disabled={busy || !waitingDraft.trim()}
            onClick={() => { setState('blocked', { waiting_on: waitingDraft.trim(), follow_through_mode: 'waiting' }); setShowWaitingForm(false); }}
          >
            Mark waiting
          </Button>
        </div>
      )}
    </div>
  );
}
