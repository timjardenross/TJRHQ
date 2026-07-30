'use client';

/**
 * Personal Tasks Panel — Issue 24
 *
 * Displays high-priority personal tasks on the Captain's Chair dashboard.
 * Integrated into the "Needs Attention Today" synthesis.
 */

import { useEffect, useState } from 'react';
import { Card } from '@/components/ui';

interface PersonalTask {
  id: string;
  title: string;
  context: string | null;
  urgency: number;
  importance: number;
  effort_minutes: number;
  work_state: string;
  created_at: string;
  priority_score: number;
}

interface NeedsAttentionResponse {
  tasks: PersonalTask[];
  count: number;
  total_available: number;
}

function workStateColor(state: string): string {
  const colors: Record<string, string> = {
    captured: 'text-wb-ink2',
    in_progress: 'text-wb-ok-on',
    blocked: 'text-wb-crit-on',
    paused: 'text-wb-warn-on',
  };
  return colors[state] ?? 'text-wb-ink2';
}

function workStateIcon(state: string): string {
  const icons: Record<string, string> = {
    captured: '◇',
    in_progress: '▶',
    blocked: '⬛',
    paused: '⏸',
  };
  return icons[state] ?? '○';
}

function urgencyLabel(u: number): string {
  const labels = ['', '⭐', '★', '★★', '★★★', '★★★★'];
  return labels[Math.min(5, u)] || '★';
}

export function PersonalTasksPanel() {
  const [tasks, setTasks] = useState<PersonalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const resp = await fetch('/api/personal-tasks/needs-attention');
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const data: NeedsAttentionResponse = await resp.json();
        if (!cancelled) {
          setTasks(data.tasks || []);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[PersonalTasksPanel] Load failed:', err);
          setError('Could not load personal tasks');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <Card>
        <p className="text-xs text-wb-ink2 animate-pulse">Loading personal tasks…</p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <p className="text-xs text-wb-crit-on">{error}</p>
      </Card>
    );
  }

  if (tasks.length === 0) {
    return (
      <Card>
        <p className="text-xs text-wb-ink2">No urgent personal tasks right now. Nice.</p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-[0.1em] text-wb-ink">Personal Tasks — Next Actions</h3>
        <span className="text-[10px] text-wb-ink2">{tasks.length} item{tasks.length !== 1 ? 's' : ''}</span>
      </div>
      <ul className="flex flex-col gap-2">
        {tasks.map((task) => (
          <li key={task.id} className="rounded-md border border-wb-line/60 bg-wb-bg/50 px-3 py-2 text-sm leading-relaxed">
            <div className="mb-1 flex items-start justify-between gap-2">
              <span className="flex-1 font-semibold text-wb-ink">{task.title}</span>
              <span className={`shrink-0 text-[10px] ${workStateColor(task.work_state)} uppercase tracking-wide`}>
                {workStateIcon(task.work_state)} {task.work_state}
              </span>
            </div>
            {task.context && <p className="mb-1.5 text-[11px] text-wb-ink2 line-clamp-2">{task.context}</p>}
            <div className="flex items-center gap-2 text-[10px] text-wb-ink2">
              <span title="Urgency">
                {urgencyLabel(task.urgency)}
              </span>
              <span title="Effort">⏱ {task.effort_minutes}m</span>
              <span className="ml-auto text-[10px] text-wb-sage-deep">Score: {task.priority_score.toFixed(1)}</span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
