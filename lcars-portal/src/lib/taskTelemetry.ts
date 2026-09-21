export type TaskEvent = 'started' | 'completed' | 'retry' | 'abandoned';

/** Best-effort, privacy-preserving task telemetry for measuring mobile flow completion. */
export function trackTaskEvent(taskId: string, event: TaskEvent, details: Record<string, unknown> = {}) {
  if (typeof window === 'undefined') return;
  void fetch('/api/action-history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    keepalive: true,
    body: JSON.stringify({
      action: `task_${event}`,
      outcome: event === 'completed' ? 'success' : event === 'retry' ? 'retry' : event,
      details: {
        task_id: taskId,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        coarse_pointer: window.matchMedia?.('(pointer: coarse)').matches ?? false,
        ...details,
      },
    }),
  }).catch(() => {});
}
