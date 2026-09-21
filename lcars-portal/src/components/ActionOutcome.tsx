import { useEffect } from 'react';
import { trackFriction, trackTaskEvent } from '@/lib/taskTelemetry';

export function ActionOutcome({ message, tone = 'neutral', retry, undo, recoveryHref, recoveryLabel = 'Open recovery', taskId, startedAt }: {
  message?: string | null;
  tone?: 'success' | 'error' | 'neutral';
  retry?: () => void;
  undo?: () => void;
  recoveryHref?: string;
  recoveryLabel?: string;
  taskId?: string;
  startedAt?: number;
}) {
  useEffect(() => {
    if (!message || typeof window === 'undefined') return;
    void fetch('/api/action-history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'ui_action_outcome', outcome: tone, details: { message } }),
      keepalive: true,
    }).catch(() => {});
  }, [message, tone]);
  useEffect(() => {
    if (tone === 'success' && taskId && message) {
      trackTaskEvent(taskId, 'completed', startedAt ? { duration_ms: Date.now() - startedAt } : undefined);
    }
    if (tone === 'error' && taskId && message) trackFriction(taskId, 'unknown', { message });
  }, [message, startedAt, taskId, tone]);
  if (!message) return null;
  const classes = tone === 'success' ? 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' : tone === 'error' ? 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on' : 'border-wb-line bg-wb-surface text-wb-ink2';
  return (
    <div className={`flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-[12px] ${classes}`} role="status" aria-live="polite">
      <span>{message}</span>
      {tone === 'error' && retry && <button type="button" onClick={() => { if (taskId) trackTaskEvent(taskId, 'retry'); retry(); }} className="font-semibold underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">Try again</button>}
      {tone === 'success' && undo && <button type="button" onClick={undo} className="font-semibold underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">Undo</button>}
      {recoveryHref && <a href={recoveryHref} className="font-semibold underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-wb-sage-deep">{recoveryLabel}</a>}
    </div>
  );
}
