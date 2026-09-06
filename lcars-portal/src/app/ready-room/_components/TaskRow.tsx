'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Badge, Button, Textarea } from '@/components/ui';
import {
  categoryMeta,
  followThroughModeMeta,
  updateTaskState,
  toggleFollowThroughPause,
  deferNotToday,
  setPinnedToday,
  FOLLOW_THROUGH_MODES,
  type PersonalTask,
  type WorkState,
  type FollowThroughMode,
} from '@/lib/personalTasks';

const URL_RE = /(https?:\/\/\S+)/;

/** context often ends with "...From <workbench> · <signal>. <link>" (see
 * Weekly Review's "Send to Ready Room"). Render the link as "Source →"
 * instead of a raw URL on the card (spec §25). */
function renderContext(context: string) {
  const match = context.match(URL_RE);
  if (!match) return <>{context}</>;
  const url = match[1];
  const before = context.slice(0, match.index).trim();
  return (
    <>
      {before && `${before} `}
      <Link href={url} target="_blank" rel="noopener noreferrer" className="text-wb-sage-deep hover:underline">
        Source →
      </Link>
    </>
  );
}

function dueLabel(due: string | null): string | null {
  if (!due) return null;
  const daysOut = Math.round((new Date(due).getTime() - Date.now()) / 86_400_000);
  if (daysOut < 0) return `Overdue · ${new Date(due).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}`;
  if (daysOut === 0) return 'Due today';
  if (daysOut === 1) return 'Due tomorrow';
  return `Due ${new Date(due).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}`;
}

/** One task card. Default surface exposes only what helps action (spec
 * §10) — title, due/context, Start/Done/•••. Category, follow-through
 * mode, waiting-on detail, mute, and "Not today" all live behind •••. */
export function TaskRow({
  task,
  onChanged,
  onStart,
  showNotToday = true,
}: {
  task: PersonalTask;
  onChanged: () => void;
  onStart?: (task: PersonalTask) => void;
  showNotToday?: boolean;
}) {
  const meta = categoryMeta(task.category);
  const ftMeta = followThroughModeMeta(task.follow_through_mode);
  const due = dueLabel(task.due_date);
  const [waitingDraft, setWaitingDraft] = useState(task.waiting_on ?? '');
  const [showWaitingForm, setShowWaitingForm] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
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

  async function notToday() {
    setBusy(true);
    await deferNotToday(task.id);
    setBusy(false);
    onChanged();
  }

  async function togglePinned() {
    setBusy(true);
    await setPinnedToday(task.id, !task.pinned_today);
    setBusy(false);
    onChanged();
  }

  async function changeMode(mode: FollowThroughMode) {
    setBusy(true);
    await updateTaskState(task.id, task.work_state, { follow_through_mode: mode });
    setBusy(false);
    onChanged();
  }

  return (
    <div className="rounded-md border border-wb-line bg-wb-surface p-3">
      <div className="flex flex-col gap-2">
        <div className="min-w-0">
          <div className="flex items-start gap-2">
            <span aria-hidden className="shrink-0 text-wb-ink2">{meta.glyph}</span>
            <span className="break-words text-[14px] font-medium text-wb-ink">{task.title}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-wb-ink2">
            {due && <span>{due}</span>}
            {task.work_state === 'blocked' && <span>Waiting on: {task.waiting_on || 'not noted yet'}</span>}
          </div>
          {task.context && (
            <p className="mt-1.5 break-words text-[12px] text-wb-ink2">{renderContext(task.context)}</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {task.work_state !== 'completed' && task.work_state !== 'blocked' && onStart && (
            <Button size="sm" variant="primary" disabled={busy} onClick={() => onStart(task)}>
              Start
            </Button>
          )}
          {task.work_state !== 'completed' && (
            <Button size="sm" variant={onStart ? 'secondary' : 'primary'} disabled={busy} onClick={() => setState('completed')}>
              Done
            </Button>
          )}
          {showNotToday && task.work_state !== 'completed' && task.work_state !== 'blocked' && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={notToday}>
              Not today
            </Button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => setShowDetails((v) => !v)}
            aria-expanded={showDetails}
            aria-label="More options"
            className="ml-auto rounded px-2 py-1 text-[13px] text-wb-ink2 opacity-70 hover:opacity-100 disabled:opacity-30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
          >
            •••
          </button>
        </div>

        {showDetails && (
          <div className="mt-1 flex flex-col gap-2 border-t border-wb-line pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge status="neutral">{meta.label}</Badge>
              <span title={ftMeta.hint}>
                <Badge status="neutral">🔔 HQ will remind you — {ftMeta.label.toLowerCase()}</Badge>
              </span>
            </div>
            {task.micro_action && task.work_state !== 'completed' && (
              <p className="text-[12px] text-wb-ink2">First step: {task.micro_action}</p>
            )}
            {task.mvp_note && (
              <p className="text-[12px] text-wb-ink2">Good enough: {task.mvp_note}</p>
            )}
            <div className="flex flex-wrap items-center gap-1.5">
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
              <label className="ml-1 flex items-center gap-1 text-[12px] text-wb-ink2">
                Remind me:
                <select
                  className="rounded border border-wb-line bg-wb-surface px-1 py-0.5 text-[12px]"
                  value={task.follow_through_mode}
                  disabled={busy}
                  onChange={(e) => changeMode(e.target.value as FollowThroughMode)}
                >
                  {FOLLOW_THROUGH_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
              </label>
              <button
                type="button"
                disabled={busy}
                onClick={togglePause}
                title={task.follow_through_paused ? 'Reminders muted — click to unmute' : 'Mute reminders for this item'}
                aria-label={task.follow_through_paused ? 'Reminders muted — click to unmute' : 'Mute reminders for this item'}
                className="text-[13px] text-wb-ink2 opacity-60 hover:opacity-100 disabled:opacity-30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep"
              >
                {task.follow_through_paused ? '🔕' : '🔔'}
              </button>
              {task.work_state !== 'completed' && task.work_state !== 'blocked' && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={togglePinned}
                  title={task.pinned_today ? 'Keeping this in Today regardless of capacity — click to unpin' : 'Keep this in Today even on a constrained day'}
                  aria-label={task.pinned_today ? 'Unpin from Today' : 'Pin to Today'}
                  aria-pressed={task.pinned_today}
                  className={`text-[13px] opacity-60 hover:opacity-100 disabled:opacity-30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${task.pinned_today ? 'text-wb-sage-deep opacity-100' : 'text-wb-ink2'}`}
                >
                  {task.pinned_today ? '📌 Pinned' : '📌 Keep in Today'}
                </button>
              )}
            </div>
          </div>
        )}
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
