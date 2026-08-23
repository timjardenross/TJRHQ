'use client';

import { useEffect, useState } from 'react';
import { Button, Input, Select } from '@/components/ui';
import {
  attendBucket, createTask, fetchTasks, CATEGORIES,
  type PersonalTask, type TaskCategory, type FollowThroughMode,
} from '@/lib/personalTasks';
import { FOLLOW_THROUGH_MODES, autoSwitchModeOnDueDate } from './followThroughMode';
import { TaskRow } from './TaskRow';

/** Seconds-not-minutes capture for a life-admin obligation: title, category,
 * optional due date. No urgency/importance sliders here — those default
 * sensibly and can be adjusted later; asking for them up front is exactly
 * the kind of hidden decision this workbench is meant to remove. */
function QuickAdd({ onAdded }: { onAdded: () => void }) {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<TaskCategory>('bill');
  const [dueDate, setDueDate] = useState('');
  const [followThroughMode, setFollowThroughMode] = useState<FollowThroughMode>('normal');
  const [modeTouched, setModeTouched] = useState(false);
  const [busy, setBusy] = useState(false);

  function handleDueDateChange(value: string) {
    setDueDate(value);
    setFollowThroughMode((prev) => autoSwitchModeOnDueDate(value, prev, modeTouched));
  }

  function handleModeChange(value: FollowThroughMode) {
    setModeTouched(true);
    setFollowThroughMode(value);
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
    setFollowThroughMode('normal');
    setModeTouched(false);
    setBusy(false);
    onAdded();
  }

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); submit(); }}
      className="mb-6 flex flex-col gap-2 rounded-md border border-wb-line bg-wb-surface p-3 sm:flex-row sm:items-end"
    >
      <div className="flex-1">
        <Input
          label="Add a life admin item"
          placeholder="e.g. Renew car rego"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="w-full sm:w-40">
        <Select label="Category" value={category} onChange={(e) => setCategory(e.target.value as TaskCategory)}>
          {CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </Select>
      </div>
      <div className="w-full sm:w-40">
        <Input type="date" label="Due (optional)" value={dueDate} onChange={(e) => handleDueDateChange(e.target.value)} />
      </div>
      <div className="w-full sm:w-40">
        <Select
          label="Follow-through"
          value={followThroughMode}
          onChange={(e) => handleModeChange(e.target.value as FollowThroughMode)}
        >
          {FOLLOW_THROUGH_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </Select>
      </div>
      <Button type="submit" disabled={!title.trim() || busy}>Add</Button>
    </form>
  );
}

function Column({
  title, hint, tasks, onChanged, emptyLabel,
}: {
  title: string;
  hint?: string;
  tasks: PersonalTask[];
  onChanged: () => void;
  emptyLabel: string;
}) {
  return (
    <section className="flex-1 min-w-0">
      <div className="mb-2">
        <h2 className="font-serif text-[15px] text-wb-ink">{title}</h2>
        {hint && <p className="text-[11px] text-wb-ink2">{hint}</p>}
      </div>
      <div className="flex flex-col gap-2">
        {tasks.length === 0 && (
          <p className="rounded-md border border-dashed border-wb-line px-3 py-4 text-center text-[12px] text-wb-ink2">
            {emptyLabel}
          </p>
        )}
        {tasks.map((t) => <TaskRow key={t.id} task={t} onChanged={onChanged} />)}
      </div>
    </section>
  );
}

export function AttendView({ refreshSignal, onLoaded }: { refreshSignal: number; onLoaded: (tasks: PersonalTask[]) => void }) {
  const [openTasks, setOpenTasks] = useState<PersonalTask[]>([]);
  const [doneTasks, setDoneTasks] = useState<PersonalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDone, setShowDone] = useState(false);

  async function load() {
    setLoading(true);
    const [open, done] = await Promise.all([
      fetchTasks({ includeCompleted: false }),
      fetchTasks({ includeCompleted: true, limit: 10 }),
    ]);
    setOpenTasks(open);
    setDoneTasks(done);
    onLoaded(open);
    setLoading(false);
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [refreshSignal]);

  if (loading) {
    return <div className="h-40 animate-pulse rounded-md bg-wb-line/40" />;
  }

  const now = openTasks.filter((t) => attendBucket(t) === 'now');
  const upcoming = openTasks.filter((t) => attendBucket(t) === 'upcoming');
  const waiting = openTasks.filter((t) => attendBucket(t) === 'waiting');

  return (
    <div className="flex flex-col gap-6">
      <QuickAdd onAdded={load} />
      <div className="flex flex-col gap-6 md:flex-row">
        <Column title="Now" hint="Urgent, or due within 2 days" tasks={now} onChanged={load} emptyLabel="Nothing urgent." />
        <Column title="Upcoming" hint="On the radar, not yet pressing" tasks={upcoming} onChanged={load} emptyLabel="Nothing upcoming." />
        <Column title="Waiting" hint="Blocked on someone or something else" tasks={waiting} onChanged={load} emptyLabel="Nothing waiting." />
      </div>

      <section>
        <Button size="sm" variant="ghost" onClick={() => setShowDone((v) => !v)}>
          {showDone ? 'Hide recent' : `Recent (${doneTasks.length})`}
        </Button>
        {showDone && (
          <div className="mt-2 flex flex-col gap-2 opacity-80">
            {doneTasks.length === 0 && (
              <p className="text-[12px] text-wb-ink2">Nothing completed yet.</p>
            )}
            {doneTasks.map((t) => <TaskRow key={t.id} task={t} onChanged={load} />)}
          </div>
        )}
      </section>
    </div>
  );
}
