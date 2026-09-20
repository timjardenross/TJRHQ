import { useEffect } from 'react';

const ACTION_HISTORY_KEY = 'tjr-action-history-v1';

export function ActionOutcome({ message, tone = 'neutral' }: { message?: string | null; tone?: 'success' | 'error' | 'neutral' }) {
  useEffect(() => {
    if (!message || typeof window === 'undefined') return;
    try {
      const history = JSON.parse(localStorage.getItem(ACTION_HISTORY_KEY) ?? '[]');
      localStorage.setItem(ACTION_HISTORY_KEY, JSON.stringify([{ action: message, at: new Date().toISOString() }, ...history].slice(0, 20)));
    } catch { /* action history is an enhancement, never a blocker */ }
  }, [message]);
  if (!message) return null;
  const classes = tone === 'success' ? 'border-wb-ok/40 bg-wb-ok/10 text-wb-ok-on' : tone === 'error' ? 'border-wb-crit/40 bg-wb-crit/10 text-wb-crit-on' : 'border-wb-line bg-wb-surface text-wb-ink2';
  return <p className={`rounded-md border px-3 py-2 text-[12px] ${classes}`} role="status" aria-live="polite">{message}</p>;
}
