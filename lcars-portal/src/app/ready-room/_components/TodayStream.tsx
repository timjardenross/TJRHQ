'use client';

import { useEffect, useState } from 'react';
import { Button, Input, Select } from '@/components/ui';
import {
  attendBucket, createTask, fetchTasks, getReadyRoomContext, rankToday, pickUpItems,
  buildStatusSentence, deferNotToday, CATEGORIES,
  type PersonalTask, type TaskCategory, type FollowThroughMode, type ReadyRoomContext,
} from '@/lib/personalTasks';
import { FOLLOW_THROUGH_MODES, autoSwitchModeOnDueDate } from './followThroughMode';
import { TaskRow } from './TaskRow';
import { ActiveTaskView } from './ActiveTaskView';

/** Title-first capture (spec §9) — no forced urgency/importance/source
 * decisions. Category/due/follow-through sit behind "Add details ▾". */
function QuickAdd({ onAdded }: { onAdded: () => void }) {
  const [title, setTitle] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [category, setCategory] = useState<TaskCategory>('task');
  const [dueDate, setDueDate] = useState('');
  const [followThroughMode, setFollowThroughMode] = useState<FollowThroughMode>('normal');
  const [modeTouched, setModeTouched] = useState(false);
  const [busy, setBusy] = useState(false);

  function handleDueDateChange(value: string) {
    setDueDate(value);
    setFollowThroughMode((prev) => autoSwitchModeOnDueDate(value, prev, modeTouched));
  }

  async function submit() {
    if (!title.trim() || busy) return;
    setBusy(true);
    await createTask({
      title, category, due_date: dueDate || null, urgency: dueDate ? 4 : 3,
      follow_through_mode: followThroughMode,
    });
    setTitle('');
    setDueDate('');
    setCategory('task');
    setFollowThroughMode('normal');
    setModeTouched(false);
    setExpanded(false);
    setBusy(false);
    onAdded();
  }

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); submit(); }}
      className="flex flex-col gap-2 rounded-md border border-wb-line bg-wb-surface p-3"
    >
      <p className="text-[13px] font-medium text-wb-ink">+ Add something</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Input
            label="What do you need to remember?"
            placeholder="e.g. Book car service"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={!title.trim() || busy}>Add</Button>
      </div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="self-start text-[12px] text-wb-ink2 underline-offset-2 hover:underline"
      >
        {expanded ? 'Hide details' : 'Add details ▾'}
      </button>
      {expanded && (
        <div className="flex flex-col gap-2 border-t border-wb-line pt-2 sm:flex-row">
          <div className="w-full sm:w-40">
            <Select label="Category" value={category} onChange={(e) => setCategory(e.target.value as TaskCategory)}>
              {CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </Select>
          </div>
          <div className="w-full sm:w-40">
            <Input type="date" label="Due (optional)" value={dueDate} onChange={(e) => handleDueDateChange(e.target.value)} />
          </div>
          <div className="w-full sm:w-48">
            <Select
              label="Remind me"
              value={followThroughMode}
              onChange={(e) => { setModeTouched(true); setFollowThroughMode(e.target.value as FollowThroughMode); }}
            >
              {FOLLOW_THROUGH_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </Select>
          </div>
        </div>
      )}
    </form>
  );
}

function CollapsedSection({
  title, count, reassurance, tasks, onChanged, emptyLabel,
}: {
  title: string;
  count: number;
  reassurance: string;
  tasks: PersonalTask[];
  onChanged: () => void;
  emptyLabel: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section>
      <div className="flex items-center justify-between rounded-md border border-wb-line bg-wb-surface px-3 py-2">
        <div>
          <p className="text-[13px] font-medium text-wb-ink">{title} {count}</p>
          <p className="text-[11px] text-wb-ink2">{reassurance}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)}>
          {open ? 'Hide' : 'Show'}
        </Button>
      </div>
      {open && (
        <div className="mt-2 flex flex-col gap-2">
          {tasks.length === 0 && (
            <p className="rounded-md border border-dashed border-wb-line px-3 py-4 text-center text-[12px] text-wb-ink2">
              {emptyLabel}
            </p>
          )}
          {tasks.map((t) => <TaskRow key={t.id} task={t} onChanged={onChanged} showNotToday={false} />)}
        </div>
      )}
    </section>
  );
}

type LoadState = 'loading' | 'clear' | 'unavailable';

export function TodayStream({ refreshSignal, onLoaded }: { refreshSignal: number; onLoaded: (tasks: PersonalTask[]) => void }) {
  const [openTasks, setOpenTasks] = useState<PersonalTask[]>([]);
  const [doneTasks, setDoneTasks] = useState<PersonalTask[]>([]);
  const [state, setState] = useState<LoadState>('loading');
  const [context, setContext] = useState<ReadyRoomContext>({
    posture: 'UNKNOWN', capacityLimit: 3, hasCheckinToday: false, freshnessStatus: 'none',
  });
  const [activeTask, setActiveTask] = useState<PersonalTask | null>(null);
  const [internalRefresh, setInternalRefresh] = useState(0);
  const [doneOpen, setDoneOpen] = useState(false);
  // HQ V1 Integration QA §21 fix: surfaces a genuine Google Tasks sync
  // failure in-page, distinct from "no tasks" — the backend already makes
  // this distinction (google-tasks/sync/route.ts), Ready Room's own page
  // previously didn't show it. 'ok'/'unknown' render nothing (no wall of
  // green); only a confirmed 'failed' shows a caveat.
  const [syncStatus, setSyncStatus] = useState<'ok' | 'failed' | 'unknown'>('unknown');

  useEffect(() => {
    let cancelled = false;
    fetch('/api/ready-room/sync-status')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (!cancelled && data?.status) setSyncStatus(data.status); })
      .catch(() => { /* stays 'unknown' — never claim ok on a fetch failure */ });
    return () => { cancelled = true; };
  }, []);

  async function load() {
    setState('loading');
    try {
      const [open, done, readyRoomContext] = await Promise.all([
        fetchTasks({ includeCompleted: false }),
        fetchTasks({ includeCompleted: true, limit: 10 }),
        getReadyRoomContext(),
      ]);
      setOpenTasks(open);
      setDoneTasks(done);
      setContext(readyRoomContext);
      onLoaded(open);
      setState('clear');
    } catch {
      setState('unavailable');
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [refreshSignal, internalRefresh]);

  // Keep the active-task overlay's data in sync with the latest fetch, so a
  // "Not today"/state change elsewhere doesn't leave it showing stale info.
  useEffect(() => {
    if (!activeTask) return;
    const fresh = openTasks.find((t) => t.id === activeTask.id);
    if (fresh) setActiveTask(fresh);
    else if (doneTasks.find((t) => t.id === activeTask.id)) setActiveTask(null);
  }, [openTasks, doneTasks, activeTask]);

  const refresh = () => setInternalRefresh((n) => n + 1);

  if (state === 'unavailable') {
    return (
      <p className="rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-[13px] text-wb-warn-on">
        Ready Room could not load your task state. Try reloading.
      </p>
    );
  }

  if (state === 'loading') {
    return <div className="h-40 animate-pulse rounded-md bg-wb-line/40" />;
  }

  if (activeTask) {
    return (
      <ActiveTaskView
        task={activeTask}
        onDone={() => { setActiveTask(null); refresh(); }}
        onPaused={() => { setActiveTask(null); refresh(); }}
        onBack={() => setActiveTask(null)}
      />
    );
  }

  const capacityLow = context.posture === 'PROTECT' || context.posture === 'RESET' || context.posture === 'RECOVER';
  const pickUp = pickUpItems(openTasks);
  const todayCandidates = openTasks.filter((t) => !pickUp.some((p) => p.id === t.id));
  const today = rankToday(todayCandidates, { capacityLimit: context.capacityLimit });
  const shownIds = new Set([...today, ...pickUp].map((t) => t.id));
  const waiting = openTasks.filter((t) => attendBucket(t) === 'waiting');
  const radar = openTasks.filter((t) => !shownIds.has(t.id) && t.work_state !== 'blocked');

  const statusSentence = buildStatusSentence({
    todayCount: today.length, waitingCount: waiting.length, capacityLow, hasCheckinToday: context.hasCheckinToday,
  });

  return (
    <div className="flex flex-col gap-6">
      <p className="rounded-md border border-wb-line bg-wb-surface px-4 py-3 text-[13px] text-wb-ink">
        {statusSentence}
      </p>
      {syncStatus === 'failed' && (
        <p className="rounded-md border border-wb-warn/40 bg-wb-warn/10 px-4 py-2 text-[12px] text-wb-warn-on">
          Google Tasks sync is currently failing — tasks added or completed on your phone may not appear here yet.
        </p>
      )}

      <section>
        <h2 className="mb-2 font-serif text-[15px] text-wb-ink">Today</h2>
        <div className="flex flex-col gap-2">
          {today.length === 0 && (
            <p className="rounded-md border border-dashed border-wb-line px-3 py-4 text-center text-[12px] text-wb-ink2">
              Nothing urgent. ✓
            </p>
          )}
          {today.map((t) => <TaskRow key={t.id} task={t} onChanged={refresh} onStart={setActiveTask} />)}
        </div>
      </section>

      {pickUp.length > 0 && (
        <section>
          <h2 className="mb-2 font-serif text-[15px] text-wb-ink">Pick up where you left off</h2>
          <div className="flex flex-col gap-2">
            {pickUp.map((t) => (
              <div key={t.id} className="rounded-md border border-wb-sage/40 bg-wb-sage/10 p-3">
                <p className="text-[14px] font-medium text-wb-ink">{t.title}</p>
                <p className="mt-1 text-[11px] uppercase tracking-wide text-wb-sage-deep">You left off here</p>
                <p className="text-[13px] text-wb-ink">{t.restart_cue}</p>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" onClick={() => setActiveTask(t)}>Continue</Button>
                  <Button size="sm" variant="ghost" onClick={async () => { await deferNotToday(t.id); refresh(); }}>
                    Not today
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <CollapsedSection
        title="On the Radar"
        count={radar.length}
        reassurance="Nothing needs your attention yet."
        tasks={radar}
        onChanged={refresh}
        emptyLabel="Nothing else captured."
      />

      <CollapsedSection
        title="Waiting"
        count={waiting.length}
        reassurance="HQ is keeping track of these. Nothing required from you."
        tasks={waiting}
        onChanged={refresh}
        emptyLabel="Nothing waiting."
      />

      <section>
        <Button size="sm" variant="ghost" onClick={() => setDoneOpen((v) => !v)}>
          {doneOpen ? 'Hide recently done' : `Recently done (${doneTasks.length})`}
        </Button>
        {doneOpen && (
          <div className="mt-2 flex flex-col gap-2 opacity-80">
            {doneTasks.length === 0 && <p className="text-[12px] text-wb-ink2">Nothing completed yet.</p>}
            {doneTasks.map((t) => <TaskRow key={t.id} task={t} onChanged={refresh} showNotToday={false} />)}
          </div>
        )}
      </section>

      <QuickAdd onAdded={refresh} />
    </div>
  );
}
